"""Common test helpers: sign-in via Keycloak, wait for streaming, common selectors."""
import time
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8000"

USERS = {
    "sales":   ("sales",      "sales"),
    "support": ("support",    "support"),
    "admin":   ("admin-user", "admin"),
}

# CSS / role-based selectors used by multiple tests.
SEL = {
    "signin_card": "text=Sign in with Keycloak",
    "kc_username": "input[name=username]",
    "kc_password": "input[name=password]",
    "kc_submit":   "input[type=submit], button[type=submit], #kc-login",
    "chat_input":  "textarea[placeholder*='Ask anything']",
    "send_button": "button[aria-label='Send'], button:has-text('Send')",
    "user_name":   "span.text-textsoft",   # signed-in user line
    "role_badge":  "[class*='border-accentedge']",
    "skills_button": "button:has-text('Skills')",
    "new_chat":    "button:has-text('New chat')",
}


def sign_in_as(page: Page, role: str):
    """Drive the Keycloak Auth-Code + PKCE flow as the named seeded user."""
    username, password = USERS[role]
    page.goto(BASE_URL + "/")
    # Wait for the sign-in card (auth gate)
    page.wait_for_selector(SEL["signin_card"], timeout=10_000)
    page.click(SEL["signin_card"])
    # Keycloak hosted login form
    page.wait_for_selector(SEL["kc_username"], timeout=10_000)
    page.fill(SEL["kc_username"], username)
    page.fill(SEL["kc_password"], password)
    page.click(SEL["kc_submit"])
    # Back at Vantage; chat surface mounts after /auth/whoami returns
    page.wait_for_url(f"{BASE_URL}/", timeout=15_000)
    page.wait_for_selector(SEL["chat_input"], timeout=10_000)


def send_message(page: Page, text: str):
    """Type a message and press Enter to submit."""
    inp = page.locator(SEL["chat_input"])
    inp.click()
    inp.fill(text)
    inp.press("Enter")


def _alpine_streaming(page: Page):
    """Read `isStreaming` from the body's Alpine 3 component (returns None if unreachable)."""
    return page.evaluate("""() => {
      if (window.Alpine && document.body) {
        try {
          const d = window.Alpine.$data(document.body);
          return typeof d.isStreaming === 'boolean' ? d.isStreaming : null;
        } catch (e) { return null; }
      }
      return null;
    }""")


def wait_for_streaming_done(page: Page, timeout: float = 45.0):
    """Block until isStreaming is back to false (i.e. the run has finished)."""
    start = time.time()
    while time.time() - start < timeout:
        if _alpine_streaming(page) is False:
            return
        time.sleep(0.25)
    raise TimeoutError(f"streaming did not finish in {timeout}s")


def is_streaming(page: Page) -> bool:
    return _alpine_streaming(page) is True


def assistant_messages(page: Page):
    """All assistant message bubbles currently in the DOM."""
    # The HTML template renders user/assistant with the same outer structure; assistant
    # bubbles are the ones that have a markdown render container (`.md` class).
    return page.locator(".md").all()


def last_assistant_text(page: Page) -> str:
    bubbles = assistant_messages(page)
    if not bubbles:
        return ""
    return bubbles[-1].inner_text()
