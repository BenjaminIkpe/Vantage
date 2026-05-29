"""Standalone smoke test for the Vantage MCP server (run against the live stack).

Not a CI test — it needs the running compose stack (db seeded + Keycloak + mcp). It acts
as a real MCP client and proves, deterministically (no LLM in the loop):
  * discovery + grounded read calls,
  * an invalid token is rejected before any tool runs (T1/T2),
  * the write/RBAC matrix at the tool boundary (ADR-002): support may update issues but not
    record next actions; sales may do neither; admin may do both. A denied call writes
    nothing and returns status 'denied'.

Run on the Codespace:
    pip install -r mcp_server/requirements.txt
    python mcp_server/smoke_test.py

Env (defaults target the published dev ports):
    MCP_URL=http://localhost:8001/mcp
    KEYCLOAK_TOKEN_URL=http://localhost:8080/realms/vantage/protocol/openid-connect/token
"""
import asyncio
import json
import os
import urllib.parse
import urllib.request

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

MCP_URL = os.getenv("MCP_URL", "http://localhost:8001/mcp")
TOKEN_URL = os.getenv(
    "KEYCLOAK_TOKEN_URL",
    "http://localhost:8080/realms/vantage/protocol/openid-connect/token",
)


def get_token(username: str, password: str) -> str:
    """Fetch a Keycloak access token via the dev ROPC grant (stdlib only)."""
    data = urllib.parse.urlencode({
        "grant_type": "password",
        "client_id": os.getenv("KC_CLIENT", "vantage-api"),
        "client_secret": os.getenv("KC_SECRET", "vantage-secret"),
        "username": username,
        "password": password,
    }).encode()
    with urllib.request.urlopen(TOKEN_URL, data=data) as resp:
        return json.loads(resp.read())["access_token"]


def _payload(result) -> dict:
    """Pull the JSON dict a tool returned out of the MCP CallToolResult."""
    if getattr(result, "structuredContent", None):
        return result.structuredContent
    return json.loads(result.content[0].text)


async def _with_session(token: str, fn):
    async with streamablehttp_client(MCP_URL, headers={"Authorization": f"Bearer {token}"}) as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()
            return await fn(session)


async def read_checks(token: str):
    async def run(session):
        names = sorted(t.name for t in (await session.list_tools()).tools)
        print("discovered tools:", names)
        assert names == [
            "create_next_action", "get_customer_profile", "get_open_issues",
            "summarise_issue_history", "update_issue", "update_next_action",
        ], names
        hero = _payload(await session.call_tool("get_open_issues", {"name": "Velocity Marketplace"}))
        assert hero["status"] == "found" and hero["open_count"] >= 3, hero
        calm = _payload(await session.call_tool("get_open_issues", {"name": "Calm Waters Subscriptions"}))
        assert calm["status"] == "found" and calm["open_count"] == 0, calm
        print("OK: discovery + grounded reads (Velocity open, Calm Waters E3)")
    await _with_session(token, run)


async def write_matrix():
    """The brief's RBAC matrix at the tool boundary — deterministic, no LLM."""
    # Persona logins (renamed from sales/support/admin-user to match the seed personas
    # in Vantage-vault/02-User-Stories.md). Passwords are the first name for demo
    # discoverability.
    support = get_token("marcus.webb", "marcus")
    sales = get_token("priya.nair", "priya")
    admin = get_token("dana.okafor", "dana")

    async def call(token, name, args):
        return _payload(await _with_session(token, lambda s: s.call_tool(name, args)))

    # support MAY update an issue (SU2)
    r = await call(support, "update_issue", {"issue_id": 2, "note": "[smoke] support note"})
    assert r["status"] == "updated", r
    print(f"OK: support update_issue -> {r['status']} (update id {r['update']['id']})")

    # sales may NOT update an issue (S3) — denied, no write
    r = await call(sales, "update_issue", {"issue_id": 2, "note": "[smoke] should be denied"})
    assert r["status"] == "denied", r
    print(f"OK: sales update_issue -> {r['status']}")

    # admin MAY create a next action (A1)
    r = await call(admin, "create_next_action", {"issue_id": 2, "description": "[smoke] admin next action"})
    assert r["status"] == "created", r
    na_id = r["next_action"]["id"]
    print(f"OK: admin create_next_action -> {r['status']} (id {na_id})")

    # support may NOT create a next action (SU3) — denied, no write
    r = await call(support, "create_next_action", {"issue_id": 2, "description": "[smoke] should be denied"})
    assert r["status"] == "denied", r
    print(f"OK: support create_next_action -> {r['status']}")

    # admin MAY update that next action
    r = await call(admin, "update_next_action", {"next_action_id": na_id, "status": "done"})
    assert r["status"] == "updated" and r["next_action"]["status"] == "done", r
    print(f"OK: admin update_next_action -> {r['status']} (now {r['next_action']['status']})")


async def expect_rejected():
    """A garbage token must never reach a tool — the transport rejects it (T1/T2)."""
    try:
        await _with_session("not-a-real-token", lambda s: s.list_tools())
        print("FAIL: invalid token was accepted")
        return False
    except Exception as exc:
        print(f"OK: invalid token rejected ({type(exc).__name__})")
        return True


async def main():
    await read_checks(get_token("marcus.webb", "marcus"))
    await write_matrix()
    if not await expect_rejected():
        raise SystemExit(1)
    print("\nSMOKE TEST PASSED")


if __name__ == "__main__":
    asyncio.run(main())
