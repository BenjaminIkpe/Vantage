"""Skills — reusable, named capabilities packaged as data, run by the agent engine.

A Skill is the same idea as an Anthropic Agent Skill (a named capability = description +
instructions), authored for this app as a small JSON file instead of a SKILL.md the Claude
runtime loads. It bundles a recurring multi-step flow into one call: instructions (what to do),
the parameters it needs each time, and the subset of tools it may use.

Running a Skill reuses the normal agent loop (agent.run_agent) — the skill's instructions
become the system prompt and its `allowed_tools` restrict the toolset (least privilege on top
of the per-tool RBAC, which is still enforced at the MCP boundary). So a Skill is *just a
prompt + a tool whitelist*: it can never exceed the caller's permissions — the payoff of
keeping RBAC in the tools, not the prompt (ADR-002). The Customer Escalation Summary (story
S2) is the first seeded skill; users will be able to author their own later.
"""
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from agent import run_agent
from llm import MODEL, aclient
from security import Principal

# Seeded skills ship read-only in the image; authored skills are written at runtime to a
# writable dir on a Docker volume (so they survive a rebuild). Authored skills override seeded.
SKILLS_DIR = Path(os.getenv("SKILLS_DIR", str(Path(__file__).parent / "skills_library")))
AUTHORED_SKILLS_DIR = Path(os.getenv("AUTHORED_SKILLS_DIR", str(Path(__file__).parent / "skills_authored")))

_RUNNER_SYSTEM = (
    "You are Vantage executing a saved skill for an Acme Operations staff member whose role is: "
    "{roles}. Follow the task instructions below exactly, using ONLY the tools provided. Ground "
    "every statement in tool results — never invent customers, issues, or facts. If a tool "
    "returns a denial, relay it plainly; do not retry. If a customer is not found or ambiguous, "
    "say so.\n\n--- SKILL INSTRUCTIONS ---\n{instructions}"
)


@dataclass
class Skill:
    name: str
    description: str
    instructions: str
    parameters: list[dict]      # [{name, description, required}]
    allowed_tools: list[str]

    def required_params(self) -> list[str]:
        return [p["name"] for p in self.parameters if p.get("required", True)]

    def render_instructions(self, params: dict) -> str:
        """Fill {param} placeholders with the supplied values (safe literal replace)."""
        text = self.instructions
        for key, value in params.items():
            text = text.replace("{" + key + "}", str(value))
        return text


def _skill_from_data(data: dict) -> Skill:
    return Skill(
        name=data["name"],
        description=data.get("description", ""),
        instructions=data["instructions"],
        parameters=data.get("parameters", []),
        allowed_tools=data.get("allowed_tools", []),
    )


def load_skills() -> dict[str, Skill]:
    """Load skill JSONs from the seeded dir then the authored dir (authored overrides)."""
    skills: dict[str, Skill] = {}
    for directory in (SKILLS_DIR, AUTHORED_SKILLS_DIR):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            data = json.loads(path.read_text())
            skills[data["name"]] = _skill_from_data(data)
    return skills


def get_skill(name: str) -> Skill | None:
    return load_skills().get(name)


def _slug(name: str) -> str:
    """A safe skill name / filename: lowercase kebab-case, alnum + dashes."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug[:48]


def save_skill(data: dict) -> Skill:
    """Validate and persist an authored skill to the writable dir; return the saved Skill."""
    name = _slug(data.get("name", ""))
    if not name:
        raise ValueError("skill needs a name")
    if not data.get("instructions"):
        raise ValueError("skill needs instructions")
    skill = Skill(
        name=name,
        description=data.get("description", ""),
        instructions=data["instructions"],
        parameters=data.get("parameters", []),
        allowed_tools=data.get("allowed_tools", []),
    )
    AUTHORED_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    (AUTHORED_SKILLS_DIR / f"{name}.json").write_text(json.dumps({
        "name": skill.name, "description": skill.description, "instructions": skill.instructions,
        "parameters": skill.parameters, "allowed_tools": skill.allowed_tools,
    }, indent=2))
    return skill


async def run_skill(skill: Skill, params: dict, token: str, principal: Principal) -> dict:
    """Run a skill: render its instructions with `params`, then drive the agent loop restricted
    to the skill's tools. Returns {"skill", "answer", "trace"}."""
    missing = [p for p in skill.required_params() if not params.get(p)]
    if missing:
        return {"status": "error", "reason": f"missing required parameter(s): {missing}"}

    system = _RUNNER_SYSTEM.format(
        roles=", ".join(principal.roles) or "unknown",
        instructions=skill.render_instructions(params),
    )
    result = await run_agent(
        "Carry out the skill instructions now.",
        token=token, principal=principal,
        system=system, allowed_tools=skill.allowed_tools,
    )
    return {"skill": skill.name, **result}


# --- authoring: turn a finished session into a reusable skill draft (Flow 1) -------------

_DRAFTER_SYSTEM = (
    "You turn a finished conversation between an Acme Operations staff member and the Vantage "
    "assistant into a reusable SKILL that reproduces what was done, for future inputs. Read the "
    "conversation, then call propose_skill with: a short kebab-case name; a one-line description "
    "of when to use it; generalised step-by-step instructions that **replace the specific values "
    "the user supplied (e.g. a customer name) with {placeholder} tokens**; and the list of those "
    "placeholders as parameters. Be faithful — capture only what was actually done, don't add "
    "steps. Keep parameters minimal (usually just the one or two obvious inputs)."
)

_PROPOSE_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_skill",
        "description": "Propose a reusable skill that generalises the conversation.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Short kebab-case skill name."},
                "description": {"type": "string", "description": "One line: when to use this skill."},
                "instructions": {"type": "string", "description": "Generalised steps; specific inputs replaced with {placeholder} tokens."},
                "parameters": {
                    "type": "array",
                    "items": {"type": "object", "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "required": {"type": "boolean"},
                    }, "required": ["name", "description"]},
                },
            },
            "required": ["name", "description", "instructions", "parameters"],
        },
    },
}


def _render_conversation(history: list[dict]) -> str:
    return "\n".join(f"{m['role'].capitalize()}: {m['content']}" for m in history)


async def draft_from_session(history: list[dict], tools_used: list[str], name: str | None = None) -> dict:
    """Generalise a session into a skill DRAFT (not saved). allowed_tools is the set of tools the
    session actually used (deterministic); the LLM writes the name/description/parameterised
    instructions/parameters. The caller reviews, then POSTs it to save."""
    if not history:
        return {"status": "error", "reason": "no conversation in this session to turn into a skill"}

    prompt = "Conversation to turn into a reusable skill:\n\n" + _render_conversation(history)
    if name:
        prompt += f"\n\nUse this skill name: {name}"

    resp = await aclient().chat.completions.create(
        model=MODEL, max_tokens=1024,
        messages=[
            {"role": "system", "content": _DRAFTER_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        tools=[_PROPOSE_TOOL],
        tool_choice={"type": "function", "function": {"name": "propose_skill"}},
    )
    tool_calls = resp.choices[0].message.tool_calls or []
    draft = json.loads(tool_calls[0].function.arguments) if tool_calls else None
    if draft is None:
        return {"status": "error", "reason": "could not draft a skill from this session"}

    draft["name"] = _slug(name or draft.get("name", "skill"))
    draft["allowed_tools"] = tools_used  # the skill may use exactly the tools the session used
    return {"status": "draft", "skill": draft}
