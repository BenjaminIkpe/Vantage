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
from dataclasses import dataclass
from pathlib import Path

from agent import run_agent
from security import Principal

SKILLS_DIR = Path(os.getenv("SKILLS_DIR", str(Path(__file__).parent / "skills_library")))

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


def load_skills() -> dict[str, Skill]:
    """Load every skill JSON from SKILLS_DIR, keyed by name."""
    skills: dict[str, Skill] = {}
    if not SKILLS_DIR.is_dir():
        return skills
    for path in sorted(SKILLS_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        skills[data["name"]] = Skill(
            name=data["name"],
            description=data.get("description", ""),
            instructions=data["instructions"],
            parameters=data.get("parameters", []),
            allowed_tools=data.get("allowed_tools", []),
        )
    return skills


def get_skill(name: str) -> Skill | None:
    return load_skills().get(name)


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
