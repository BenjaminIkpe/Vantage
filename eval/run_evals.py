"""Vantage evaluation harness (run against the live stack).

Thirteen cases that prove the assistant works on the core dimensions: the right
tool(s) are selected, answers are grounded in the data (never invented), RBAC is respected
(allowed *and* denied), multi-turn context resolves, and the reusable Skill works. Cases are
derived from the acceptance criteria in 02-User-Stories.md / 07-Evals.md.

Assertions target the **deterministic** signals — the tool `trace` (which tool ran and the
tool's `result.status`/fields, which are data-driven) and the HTTP status — plus loose,
case-insensitive substring checks on the answer text where they're reliable. This keeps the
suite stable against LLM phrasing while still proving grounding.

Not a unit test (needs the running stack + an API key). Run on the Codespace:

    python eval/run_evals.py            # exits non-zero if any case fails

Env (defaults target the published dev ports):
    API_URL=http://localhost:8000   KEYCLOAK_TOKEN_URL=http://localhost:8080/.../token
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = os.getenv("API_URL", "http://localhost:8000")
TOKEN_URL = os.getenv(
    "KEYCLOAK_TOKEN_URL",
    "http://localhost:8080/realms/vantage/protocol/openid-connect/token",
)
# role → (keycloak_username, password). Personas match the seed stories — the username
# changes shape (`sales` → `priya.nair`), but the role-key in this script stays the same so
# the scenarios below don't need to know about the rename.
USERS = {
    "sales":   ("priya.nair",  "priya"),
    "support": ("marcus.webb", "marcus"),
    "admin":   ("dana.okafor", "dana"),
}


# --- HTTP helpers ------------------------------------------------------------

def token(role: str) -> str:
    username, password = USERS[role]
    data = urllib.parse.urlencode({
        "grant_type": "password", "client_id": "vantage-api", "client_secret": "vantage-secret",
        "username": username, "password": password,
    }).encode()
    with urllib.request.urlopen(TOKEN_URL, data=data) as r:
        return json.loads(r.read())["access_token"]


def _post(path: str, body: dict, tok: str | None):
    headers = {"Content-Type": "application/json"}
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}


# --- the cases ---------------------------------------------------------------
# Each case: id, measures, role, and either `ask`/`turns`/`skill`/`no_auth`, plus `expect`.
CASES = [
    {
        "id": "1-grounded-profile", "measures": "right tool + grounded read", "role": "support",
        "ask": "Give me the customer profile for Velocity Marketplace.",
        "expect": {"tools": ["get_customer_profile"], "status": {"get_customer_profile": "found"},
                   "answer_any": ["ACME-76085", "velocity"]},
    },
    {
        "id": "2-not-found-E1", "measures": "grounded — no invented customer", "role": "support",
        "ask": "Show me the open issues for Zzzz Holdings.",
        "expect": {"status_any": {"get_open_issues": ["not_found"], "get_customer_profile": ["not_found"]},
                   "answer_any": ["not found", "no customer", "couldn't find", "could not find", "no matching"]},
    },
    {
        "id": "3-ambiguous-E2", "measures": "disambiguates, doesn't guess", "role": "support",
        "ask": "What open issues does Lumen have?",
        "expect": {"status_any": {"get_open_issues": ["ambiguous"], "get_customer_profile": ["ambiguous"]},
                   "answer_any": ["which", "ambiguous", "two", "group", "clarify", "more than one"]},
    },
    {
        "id": "4-no-open-E3", "measures": "no fabrication when nothing open", "role": "support",
        "ask": "What open issues does Calm Waters Subscriptions have?",
        "expect": {"tools": ["get_open_issues"], "status": {"get_open_issues": "found"},
                   "result_field": {"get_open_issues": {"open_count": 0}},
                   "answer_any": ["no open", "zero open", "none"]},
    },
    {
        "id": "5-multi-tool-hero", "measures": "dynamic multi-tool selection", "role": "support",
        "ask": "Show the open issues for Velocity Marketplace, summarise the most urgent one, and recommend a next action.",
        "expect": {"tools": ["get_open_issues", "summarise_issue_history"]},
    },
    {
        "id": "6-rbac-deny", "measures": "RBAC denied (negative)", "role": "sales",
        "ask": "Add a note to issue 3 saying 'checked with the customer'.",
        "expect": {"tools": ["update_issue"], "status": {"update_issue": "denied"},
                   "answer_any": ["denied", "permission", "role", "not allowed", "support or admin", "can't", "cannot", "unable"]},
    },
    {
        "id": "7-rbac-allow", "measures": "RBAC allowed write", "role": "support",
        "ask": "Add a note to issue 3 saying 'eval: following up with the customer'.",
        "expect": {"tools": ["update_issue"], "status": {"update_issue": "updated"},
                   "answer_any": ["added", "updated", "noted", "recorded", "done"]},
    },
    {
        "id": "8-multi-turn-X1", "measures": "multi-turn session memory", "role": "support",
        "turns": ["What open issues does Velocity Marketplace have?", "Summarise the second one."],
        "expect": {"tools": ["summarise_issue_history"]},  # asserted on the 2nd turn's trace
    },
    {
        "id": "9-skill-escalation", "measures": "reusable Skill (S2)", "role": "sales",
        "skill": ("escalation-summary", {"customer": "Velocity Marketplace"}),
        "expect": {"tools": ["get_open_issues"], "answer_any": ["critical", "high", "risk"]},
    },
    {
        "id": "10-auth-401", "measures": "auth required", "role": "support", "no_auth": True,
        "ask": "Anything.", "expect": {"http": 401},
    },
    # --- browse / list tools (PR feat/browse-tools) ---
    {
        "id": "11-list-customers", "measures": "browse: list_customers for exploration",
        "role": "sales", "ask": "Who are our customers? Show me a few.",
        "expect": {"tools": ["list_customers"], "status": {"list_customers": "ok"},
                   "answer_any": ["velocity", "calm waters", "lumen"]},
    },
    {
        "id": "12-list-issues-critical", "measures": "browse: cross-customer triage by filter",
        "role": "support", "ask": "Show me all critical open issues across customers.",
        "expect": {"tools": ["list_issues"], "status": {"list_issues": "ok"},
                   "answer_any": ["critical"]},
    },
    {
        "id": "13-list-next-actions-overdue", "measures": "admin oversight: overdue directives",
        "role": "admin", "ask": "What next actions are overdue?",
        "expect": {"tools": ["list_next_actions"], "status": {"list_next_actions": "ok"}},
    },
]


# --- assertions --------------------------------------------------------------

def _trace_index(trace):
    """tool_name -> list of result dicts, in call order."""
    idx: dict[str, list] = {}
    for t in trace:
        idx.setdefault(t["tool"], []).append(t.get("result", {}))
    return idx


def check(expect: dict, http: int, answer: str, trace: list) -> list[str]:
    """Return a list of failure messages (empty == pass)."""
    fails = []
    idx = _trace_index(trace)
    ans = (answer or "").lower()

    if "http" in expect and http != expect["http"]:
        fails.append(f"http {http} != {expect['http']}")
    for tool in expect.get("tools", []):
        if tool not in idx:
            fails.append(f"tool '{tool}' not called (called: {list(idx)})")
    for tool, status in expect.get("status", {}).items():
        got = [r.get("status") for r in idx.get(tool, [])]
        if status not in got:
            fails.append(f"{tool} status {got} != '{status}'")
    for tool, allowed in expect.get("status_any", {}).items():
        got = [r.get("status") for r in idx.get(tool, [])]
        if idx.get(tool) and not any(s in allowed for s in got):
            fails.append(f"{tool} status {got} not in {allowed}")
    # status_any with NO tool called at all is a fail only if none of the listed tools ran
    if "status_any" in expect and not any(t in idx for t in expect["status_any"]):
        fails.append(f"none of {list(expect['status_any'])} were called (called: {list(idx)})")
    for tool, fields in expect.get("result_field", {}).items():
        results = idx.get(tool, [{}])
        for k, v in fields.items():
            if not any(r.get(k) == v for r in results):
                fails.append(f"{tool}.{k} != {v} (got {[r.get(k) for r in results]})")
    if "answer_any" in expect and not any(s.lower() in ans for s in expect["answer_any"]):
        fails.append(f"answer missing any of {expect['answer_any']}")
    return fails


# --- runner ------------------------------------------------------------------

def run_case(c: dict):
    expect = c["expect"]
    if c.get("no_auth"):
        http, body = _post("/ask", {"query": c["ask"]}, None)
        return check(expect, http, "", []), http, ""

    tok = token(c["role"])
    if "skill" in c:
        name, params = c["skill"]
        http, body = _post(f"/skills/{name}/run", {"params": params}, tok)
        return check(expect, http, body.get("answer", ""), body.get("trace", [])), http, body.get("answer", "")
    if "turns" in c:
        sid = f"eval-{c['id']}-{int(time.time())}"
        http = body = None
        for q in c["turns"]:
            http, body = _post("/ask", {"session_id": sid, "query": q}, tok)  # last turn checked
        return check(expect, http, body.get("answer", ""), body.get("trace", [])), http, body.get("answer", "")
    http, body = _post("/ask", {"query": c["ask"]}, tok)
    return check(expect, http, body.get("answer", ""), body.get("trace", [])), http, body.get("answer", "")


def main():
    passed = 0
    print(f"Running {len(CASES)} eval cases against {API}\n")
    for c in CASES:
        try:
            fails, http, answer = run_case(c)
        except Exception as exc:
            fails, answer = [f"exception: {exc}"], ""
        ok = not fails
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {c['id']:22} — {c['measures']}")
        if not ok:
            for f in fails:
                print(f"        ✗ {f}")
            if answer:
                print(f"        answer: {answer[:160]}")
    print(f"\n{passed}/{len(CASES)} passed")
    sys.exit(0 if passed == len(CASES) else 1)


if __name__ == "__main__":
    main()
