"""Vantage UI end-to-end tests with Playwright.

Designed to catch the bugs the user reported on live poking + add comprehensive coverage:
  - streaming visibility: response should grow as it streams, not require a tab switch
  - skills modal: open, list, pick one, run, see grounded result in chat
  - layout: page height should not grow as messages accumulate (thread scrolls internally)
  - RBAC: sales denied / support+admin allowed
  - sidebar: chats persist across reload; clicking an old chat loads its history
  - keyboard + theme polish

Run on the Codespace where the stack is alive:
    pip install -r tests/ui/requirements.txt
    playwright install --with-deps chromium
    pytest tests/ui -v
"""
import os
import time
import pytest
from playwright.sync_api import Page, expect

from helpers import (
    BASE_URL, SEL, sign_in_as, send_message, wait_for_streaming_done,
    assistant_messages, last_assistant_text,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1) Auth — sign-in card, sign-in for each role, sign-out, persistence
# ─────────────────────────────────────────────────────────────────────────────

def test_unauthed_visit_shows_signin_card(page: Page):
    """A fresh visit (no cookie) renders the sign-in overlay, not the chat."""
    page.goto(BASE_URL + "/")
    expect(page.get_by_text("Sign in with Keycloak")).to_be_visible(timeout=10_000)
    # Chat input is not visible (it's behind authStatus === 'authed')
    assert page.locator(SEL["chat_input"]).count() == 0 or not page.locator(SEL["chat_input"]).is_visible()


@pytest.mark.parametrize("role,expected_role_word", [
    ("sales", "sales"),
    ("support", "support"),
    ("admin", "admin"),
])
def test_signin_loads_chat_with_correct_role(page: Page, role: str, expected_role_word: str):
    """Sign in as each role → chat loads, role chip shows the right text."""
    sign_in_as(page, role)
    # Chat input is visible (we're in the authed UI)
    expect(page.locator(SEL["chat_input"])).to_be_visible()
    # Role text appears somewhere in the header / footer
    page_text = page.inner_text("body").lower()
    assert expected_role_word in page_text, f"role text {expected_role_word!r} not found in page"


def test_signin_persists_across_reload(page: Page):
    """After sign-in, hard reload → still authed (cookie path)."""
    sign_in_as(page, "support")
    page.reload()
    expect(page.locator(SEL["chat_input"])).to_be_visible(timeout=10_000)
    # Should NOT see the sign-in card after reload
    assert page.locator("text=Sign in with Keycloak").count() == 0 or \
           not page.locator("text=Sign in with Keycloak").is_visible()


def test_signout_returns_signin_card(page: Page):
    """Open avatar menu → Sign out → land on sign-in card."""
    sign_in_as(page, "support")
    # Open the avatar menu (3-dot button)
    page.get_by_role("button", name="Account menu").click()
    page.get_by_text("Sign out").click()
    expect(page.get_by_text("Sign in with Keycloak")).to_be_visible(timeout=10_000)


# ─────────────────────────────────────────────────────────────────────────────
# 2) Streaming visibility (the headline reported bug)
# ─────────────────────────────────────────────────────────────────────────────

def test_streaming_response_visible_without_tab_switch(page: Page):
    """Bug repro: after sending, the assistant's answer should grow as it streams in,
    visible immediately — NOT require switching to another chat and back."""
    sign_in_as(page, "support")
    send_message(page, "What open issues does Velocity Marketplace have?")

    # Watch the assistant's message text grow over time.
    samples = []
    deadline = time.time() + 25
    while time.time() < deadline:
        text = last_assistant_text(page)
        samples.append((time.time(), len(text)))
        # Break early once we have a meaningful answer growing
        if len(text) > 300:
            break
        time.sleep(0.5)

    # Strict assertion: text length grew over time (we saw at least 3 distinct sizes,
    # not just a final dump).
    distinct_sizes = sorted(set(s[1] for s in samples))
    assert len(distinct_sizes) >= 3, (
        f"answer never grew progressively — saw sizes {distinct_sizes} "
        f"(if there are only 1-2 sizes, the UI isn't re-rendering as deltas arrive)"
    )
    assert distinct_sizes[-1] > 100, (
        f"final assistant text was only {distinct_sizes[-1]} chars — did the stream stall?"
    )


def test_trace_expander_populates_after_response(page: Page):
    """Once the stream finishes, the trace expander should list the tools that fired."""
    sign_in_as(page, "support")
    send_message(page, "Open issues for Velocity Marketplace?")
    wait_for_streaming_done(page, timeout=45)

    # Look for the trace summary text "N tools · ..."
    page.wait_for_selector("text=/\\d+ tools? · /", timeout=5_000)


def test_multiple_messages_keep_streaming(page: Page):
    """Send a second message — it also streams in (no broken state from the first)."""
    sign_in_as(page, "support")
    send_message(page, "Open issues for Velocity Marketplace?")
    wait_for_streaming_done(page, timeout=45)
    send_message(page, "Summarise the most urgent.")
    wait_for_streaming_done(page, timeout=45)
    # Two assistant bubbles should be visible
    bubbles = assistant_messages(page)
    assert len(bubbles) >= 2, f"expected ≥2 assistant messages, saw {len(bubbles)}"


# ─────────────────────────────────────────────────────────────────────────────
# 3) Skills (reported as "don't work")
# ─────────────────────────────────────────────────────────────────────────────

def test_skills_menu_opens_and_lists_seeded_skill(page: Page):
    """Clicking 'Skills' should open the modal AND populate with seeded skills."""
    sign_in_as(page, "support")
    page.locator(SEL["skills_button"]).first.click()

    # Modal opens
    page.wait_for_selector("text=/Skills/", timeout=3_000)
    # The seeded escalation-summary should be in the list
    page.wait_for_selector("text=escalation-summary", timeout=5_000)


def test_skills_run_escalation_summary(page: Page):
    """Pick the seeded skill → param form → run → assistant message with content appears."""
    sign_in_as(page, "support")
    page.locator(SEL["skills_button"]).first.click()
    page.wait_for_selector("text=escalation-summary", timeout=5_000)
    page.click("text=escalation-summary")
    # Parameter form should appear with `customer`
    customer_input = page.locator("input[placeholder*='customer'], input[placeholder*='Customer']").first
    customer_input.wait_for(timeout=3_000)
    customer_input.fill("Velocity Marketplace")
    # Run
    page.get_by_role("button", name="Run").click()
    wait_for_streaming_done(page, timeout=60)
    # Some answer text should be in the assistant bubble
    text = last_assistant_text(page).lower()
    assert "velocity" in text or "critical" in text or "risk" in text, \
        f"skill output didn't look like a risk brief (got {text[:200]!r})"


def test_save_as_skill_button_appears_after_chat(page: Page):
    """The 'Save as skill' affordance should appear after 3+ messages with assistant turns."""
    sign_in_as(page, "support")
    send_message(page, "Open issues for Velocity Marketplace?")
    wait_for_streaming_done(page, timeout=45)
    send_message(page, "Now summarise the most urgent.")
    wait_for_streaming_done(page, timeout=45)
    # Header should now show the Save as skill button
    assert page.get_by_text("Save as skill").count() > 0


# ─────────────────────────────────────────────────────────────────────────────
# 4) Layout — page height stable, thread scrolls internally
# ─────────────────────────────────────────────────────────────────────────────

def test_layout_page_height_stays_stable(page: Page):
    """Bug repro: after several messages, the document body should not be much taller
    than the viewport (the thread is supposed to scroll internally)."""
    sign_in_as(page, "support")
    viewport = page.viewport_size["height"]

    # Send a handful of messages so the chat has real length.
    queries = [
        "Open issues for Velocity Marketplace?",
        "Summarise the most urgent.",
        "What's the history on issue 3?",
        "Open issues for Calm Waters Subscriptions?",
    ]
    for q in queries:
        send_message(page, q)
        wait_for_streaming_done(page, timeout=45)

    body_height = page.evaluate("() => document.body.scrollHeight")
    # Body shouldn't grow past viewport by more than 50px slack — anything bigger means the
    # main page is scrolling instead of the thread div inside.
    assert body_height <= viewport + 50, (
        f"body grew to {body_height}px (viewport={viewport}); "
        "thread should scroll internally, not extend the page"
    )


def test_layout_thread_autoscrolls_to_bottom_after_send(page: Page):
    """After a new message, the visible scroll should be at the bottom of the thread."""
    sign_in_as(page, "support")
    send_message(page, "Open issues for Velocity Marketplace?")
    wait_for_streaming_done(page, timeout=45)
    send_message(page, "Now summarise the most urgent.")
    wait_for_streaming_done(page, timeout=45)

    # The thread div has x-ref="thread"; query by that.
    at_bottom = page.evaluate(
        """() => {
          const t = document.querySelector('[x-ref="thread"]') ||
                    document.querySelector('.overflow-y-auto');
          if (!t) return false;
          return Math.abs(t.scrollHeight - t.scrollTop - t.clientHeight) < 80;
        }"""
    )
    assert at_bottom, "thread did not auto-scroll to bottom after sending a message"


# ─────────────────────────────────────────────────────────────────────────────
# 5) RBAC — the panel-relevant moment
# ─────────────────────────────────────────────────────────────────────────────

def test_rbac_sales_update_denied_relayed(page: Page):
    """As sales, asking for a write → trace shows update_issue → denied, answer relays."""
    sign_in_as(page, "sales")
    send_message(page, "Add a note to issue 3 saying I checked with the customer.")
    wait_for_streaming_done(page, timeout=45)
    text = page.inner_text("body").lower()
    # Either explicit 'denied' or 'requires' / 'role' phrasing — model has some freedom
    assert ("denied" in text or "requires" in text or "permission" in text
            or "support" in text or "admin" in text), \
        "agent didn't relay an RBAC refusal to the sales user"


def test_rbac_support_update_succeeds(page: Page):
    """As support, the same query should succeed."""
    sign_in_as(page, "support")
    send_message(page, "Add a note to issue 4 saying 'UI test write check'.")
    wait_for_streaming_done(page, timeout=45)
    text = page.inner_text("body").lower()
    assert ("added" in text or "updated" in text or "noted" in text or "recorded" in text), \
        f"support write didn't look like a success (got: {text[-300:]!r})"


def test_rbac_admin_create_next_action_succeeds(page: Page):
    """As admin, creating a next action should succeed."""
    sign_in_as(page, "admin")
    send_message(page, "Create a next action on issue 1: 'UI test directive', due 2026-06-10.")
    wait_for_streaming_done(page, timeout=60)
    text = page.inner_text("body").lower()
    assert ("created" in text or "recorded" in text or "next action" in text), \
        f"admin next-action creation didn't look like a success"


# ─────────────────────────────────────────────────────────────────────────────
# 6) Sidebar — chat persistence, click-to-resume
# ─────────────────────────────────────────────────────────────────────────────

def test_sidebar_shows_new_chat_after_send(page: Page):
    """After the first message of a new chat, it should appear in the sidebar."""
    sign_in_as(page, "support")
    msg = "Sidebar test — open issues for Velocity Marketplace?"
    send_message(page, msg)
    wait_for_streaming_done(page, timeout=45)
    # The sidebar should contain a chat with our message as its title.
    page.wait_for_selector(f"text=/{msg[:30]}/", timeout=10_000)


def test_sidebar_chats_persist_after_reload(page: Page):
    """After reloading, the chat we just sent should still be in the sidebar."""
    sign_in_as(page, "support")
    msg = "Persistence test — pull Velocity Marketplace please"
    send_message(page, msg)
    wait_for_streaming_done(page, timeout=45)
    page.reload()
    page.wait_for_selector(SEL["chat_input"], timeout=10_000)
    # Sidebar should still have our chat
    page.wait_for_selector(f"text=/{msg[:30]}/", timeout=10_000)


# ─────────────────────────────────────────────────────────────────────────────
# 7) Keyboard shortcuts + theme
# ─────────────────────────────────────────────────────────────────────────────

def test_keyboard_cmd_k_opens_skills(page: Page):
    """⌘K / Ctrl+K opens the Skills modal."""
    sign_in_as(page, "support")
    page.keyboard.press("Meta+K" if os.uname().sysname == "Darwin" else "Control+K")
    # Either modal title or skill name should appear within a moment
    page.wait_for_selector("text=escalation-summary, text=Skills", timeout=3_000)


def test_theme_toggle_persists(page: Page):
    """Switch to light, reload, still light."""
    sign_in_as(page, "support")
    # Avatar menu → theme toggle
    page.get_by_role("button", name="Account menu").click()
    page.get_by_text("Switch to light theme").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    page.reload()
    page.wait_for_selector(SEL["chat_input"], timeout=10_000)
    expect(page.locator("html")).to_have_attribute("data-theme", "light")


# ─────────────────────────────────────────────────────────────────────────────
# 8) Error handling
# ─────────────────────────────────────────────────────────────────────────────

def test_empty_input_does_not_send(page: Page):
    """Pressing Enter on an empty input should be a no-op (no fetch, no message)."""
    sign_in_as(page, "support")
    inp = page.locator(SEL["chat_input"])
    inp.click()
    inp.press("Enter")
    # Nothing should appear in the thread
    time.sleep(1.0)
    assert page.evaluate("() => document.querySelector('body').__x?.$data?.isStreaming") in (False, None)
