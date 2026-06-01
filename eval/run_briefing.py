"""Vantage BRIEFING eval — the proactive admin briefing (ADR-008), end-to-end.

Validates the LangGraph briefing's externally-observable contract against the live stack, using
deterministic signals only (HTTP status, response shape, tool-grounded ids, the created
next_action) — never LLM phrasing:

  * RBAC — the briefing is admin-only (sales and support are refused at the entry, and the
    fleet-aggregate tools are admin-only at the MCP boundary too).
  * Grounding — every drafted next action is tied to a real issue_id that the run actually
    fetched (no proposals against invented issues).
  * Human-in-the-loop — the run pauses for approval (`pending_approval`), and only approved
    drafts are written; the rest are skipped.
  * Resume + write — approving a draft writes a next_action; an unknown briefing id is 404.

Not a unit test (needs the running stack + an API key). Run on the Codespace:

    python eval/run_briefing.py          # exits non-zero on any failure

Env (defaults target the published dev ports):
    API_URL=http://localhost:8000   KEYCLOAK_TOKEN_URL=http://localhost:8080/.../token
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = os.getenv("API_URL", "http://localhost:8000")
TOKEN_URL = os.getenv(
    "KEYCLOAK_TOKEN_URL",
    "http://localhost:8080/realms/vantage/protocol/openid-connect/token",
)
# role → (keycloak_username, password); same personas as the other suites.
USERS = {
    "sales": ("priya.nair", "priya"),
    "support": ("marcus.webb", "marcus"),
    "admin": ("dana.okafor", "dana"),
}


def token(role: str) -> str:
    user, pwd = USERS[role]
    data = urllib.parse.urlencode({
        "grant_type": "password",
        "client_id": os.getenv("KC_CLIENT", "vantage-api"),
        "client_secret": os.getenv("KC_SECRET", "vantage-secret"),
        "username": user, "password": pwd,
    }).encode()
    with urllib.request.urlopen(TOKEN_URL, data=data) as resp:
        return json.loads(resp.read())["access_token"]


def call(method: str, path: str, tok: str, body: dict | None = None):
    """Return (status, json). Reads the body even on 4xx so assertions can inspect it."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read() or "{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or "{}")
        except Exception:
            return exc.code, {}


_results: list[tuple[str, bool]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    _results.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL"), "-", name, ("" if cond else f"  :: {detail}"))


def main() -> int:
    # B1 / B2 — RBAC: non-admins are refused at the entry.
    st, _ = call("GET", "/briefing", token("sales"))
    check("sales GET /briefing -> 403", st == 403, f"got {st}")
    st, _ = call("GET", "/briefing", token("support"))
    check("support GET /briefing -> 403", st == 403, f"got {st}")

    # B3 — admin runs the briefing: shape + grounded drafts + the HITL gate.
    admin = token("admin")
    st, body = call("GET", "/briefing", admin)
    check("admin GET /briefing -> 200", st == 200, f"got {st}")
    summaries = body.get("summaries", [])
    drafts = body.get("drafts", [])
    bid = body.get("briefing_id")
    valid_ids = {(s.get("top_issue") or {}).get("id") for s in summaries}
    check("briefing returns a briefing_id", bool(bid))
    check("briefing summarised the high-risk fleet (>=1 account)", len(summaries) >= 1,
          f"summaries={len(summaries)}")
    check("paused at the approval gate (pending_approval)", body.get("pending_approval") is True,
          f"pending_approval={body.get('pending_approval')}, drafts={len(drafts)}")
    check("every draft is grounded in a fetched issue_id",
          all(d.get("issue_id") in valid_ids for d in drafts),
          f"draft ids={[d.get('issue_id') for d in drafts]} valid={valid_ids}")

    # B4 — approve one draft: it writes a next_action; the rest are skipped.
    if drafts and bid:
        did = drafts[0]["draft_id"]
        st, ab = call("POST", f"/briefing/{bid}/approve", admin, {"approved_ids": [did]})
        check("approve -> 200", st == 200, f"got {st}")
        res = ab.get("results", [])
        created = [r for r in res if r.get("draft_id") == did and r.get("status") == "created"]
        check("approved draft writes a next_action", len(created) == 1, f"results={res}")
        check("unapproved drafts are skipped",
              all(r.get("status") == "skipped" for r in res if r.get("draft_id") != did),
              f"results={res}")
    else:
        check("approve path (drafts were produced to approve)", False, "no drafts returned")

    # B5 — an unknown briefing id is a clean 404 (not a 500).
    st, _ = call("POST", "/briefing/nonexistent-briefing-id/approve", admin, {"approved_ids": [0]})
    check("approve unknown briefing -> 404", st == 404, f"got {st}")

    passed = sum(1 for _, ok in _results if ok)
    print(f"\n{passed}/{len(_results)} checks passed")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
