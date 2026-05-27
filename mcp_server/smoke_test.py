"""Standalone smoke test for the Vantage MCP server (run against the live stack).

Not a CI test — it needs the running compose stack (db seeded + Keycloak + mcp). It acts
as a real MCP client: fetches a Keycloak token, connects over Streamable HTTP forwarding
that token, discovers the tools, calls one, and proves an invalid token is rejected
(ADR-003 boundary + 09-Security T1/T2). Run on the Codespace:

    pip install -r mcp_server/requirements.txt
    python mcp_server/smoke_test.py

Env (defaults target the published dev ports):
    MCP_URL=http://localhost:8001/mcp
    KEYCLOAK_TOKEN_URL=http://localhost:8080/realms/vantage/protocol/openid-connect/token
    KC_USER=support  KC_PASS=support  KC_CLIENT=vantage-api  KC_SECRET=vantage-secret
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


def get_token() -> str:
    """Fetch a Keycloak access token via the dev ROPC grant (stdlib only)."""
    data = urllib.parse.urlencode({
        "grant_type": "password",
        "client_id": os.getenv("KC_CLIENT", "vantage-api"),
        "client_secret": os.getenv("KC_SECRET", "vantage-secret"),
        "username": os.getenv("KC_USER", "support"),
        "password": os.getenv("KC_PASS", "support"),
    }).encode()
    with urllib.request.urlopen(TOKEN_URL, data=data) as resp:
        return json.loads(resp.read())["access_token"]


def _result_payload(result) -> dict:
    """Pull the JSON dict a tool returned out of the MCP CallToolResult."""
    if getattr(result, "structuredContent", None):
        return result.structuredContent
    return json.loads(result.content[0].text)


async def call(token: str):
    async with streamablehttp_client(MCP_URL, headers={"Authorization": f"Bearer {token}"}) as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            print("discovered tools:", names)
            assert names == ["get_customer_profile", "get_open_issues", "summarise_issue_history"], names

            hero = _result_payload(await session.call_tool("get_open_issues", {"name": "Velocity Marketplace"}))
            print(f"Velocity -> status={hero['status']} open_count={hero['open_count']}")
            assert hero["status"] == "found" and hero["open_count"] >= 3, hero

            calm = _result_payload(await session.call_tool("get_open_issues", {"name": "Calm Waters Subscriptions"}))
            print(f"Calm Waters -> status={calm['status']} open_count={calm['open_count']} (E3)")
            assert calm["status"] == "found" and calm["open_count"] == 0, calm

    print("OK: authenticated path (discovery + grounded tool calls)")


async def expect_rejected():
    """A garbage token must never reach a tool — the transport rejects it (T1/T2)."""
    try:
        async with streamablehttp_client(MCP_URL, headers={"Authorization": "Bearer not-a-real-token"}) as (r, w, _):
            async with ClientSession(r, w) as session:
                await session.initialize()
        print("FAIL: invalid token was accepted")
        return False
    except Exception as exc:
        print(f"OK: invalid token rejected ({type(exc).__name__})")
        return True


async def main():
    token = get_token()
    print(f"got token (len={len(token)})")
    await call(token)
    ok = await expect_rejected()
    if not ok:
        raise SystemExit(1)
    print("\nSMOKE TEST PASSED")


if __name__ == "__main__":
    asyncio.run(main())
