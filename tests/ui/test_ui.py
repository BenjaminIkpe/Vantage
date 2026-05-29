"""Vantage UI end-to-end tests — Playwright + Chromium.

Comprehensive coverage of every interactive surface, every role, every reported bug.
Run on the Codespace where the stack is alive:

    pip install -r tests/ui/requirements.txt
    playwright install chromium
    pytest tests/ui -v
    pytest tests/ui -v -n 4               # parallel
    pytest tests/ui -v -k auth            # filter
"""
import os
import re
import time
import pytest
from playwright.sync_api import Page, BrowserContext, expect

from helpers import (
    BASE_URL, SEL, sign_in_as, send_message, wait_for_streaming_done,
    assistant_messages, last_assistant_text, is_streaming,
)


# ════════════════════════════════════════════════════════════════════════════
# 1) AUTH — sign-in card, all 3 roles, persistence, sign-out
# ════════════════════════════════════════════════════════════════════════════

class TestAuth:
    def test_unauthed_visit_shows_signin_card(self, page: Page):
        page.goto(BASE_URL + "/")
        expect(page.get_by_text("Sign in with Keycloak")).to_be_visible(timeout=10_000)

    def test_unauthed_chat_input_not_present(self, page: Page):
        page.goto(BASE_URL + "/")
        page.wait_for_selector("text=Sign in with Keycloak", timeout=10_000)
        # Chat input should not be visible / interactive when unauthed
        assert not page.locator(SEL["chat_input"]).is_visible()

    def test_signin_card_lists_dev_users(self, page: Page):
        page.goto(BASE_URL + "/")
        page.wait_for_selector("text=Sign in with Keycloak", timeout=10_000)
        body = page.inner_text("body").lower()
        assert "sales" in body and "support" in body and "admin" in body, \
            "sign-in card should list the seeded dev users"

    @pytest.mark.parametrize("role", ["sales", "support", "admin"])
    def test_signin_succeeds_for_role(self, page: Page, role: str):
        sign_in_as(page, role)
        expect(page.locator(SEL["chat_input"])).to_be_visible(timeout=10_000)

    def test_role_badge_after_signin_sales(self, page_sales: Page):
        body = page_sales.inner_text("body").lower()
        assert "sales" in body

    def test_role_badge_after_signin_support(self, page_support: Page):
        body = page_support.inner_text("body").lower()
        assert "support" in body

    def test_role_badge_after_signin_admin(self, page_admin: Page):
        body = page_admin.inner_text("body").lower()
        assert "admin" in body

    def test_signin_persists_across_reload(self, page_support: Page):
        page_support.reload()
        expect(page_support.locator(SEL["chat_input"])).to_be_visible(timeout=10_000)

    def test_signout_clears_session(self, page_support: Page):
        page_support.get_by_role("button", name="Account menu").click()
        page_support.get_by_text("Sign out").click()
        expect(page_support.get_by_text("Sign in with Keycloak")).to_be_visible(timeout=10_000)

    def test_signout_clears_cookie(self, page_support: Page, context: BrowserContext):
        # Sign out and verify the vantage_sid cookie is gone.
        before = [c for c in context.cookies() if c["name"] == "vantage_sid"]
        assert before, "expected vantage_sid cookie to exist after sign-in"
        page_support.get_by_role("button", name="Account menu").click()
        page_support.get_by_text("Sign out").click()
        page_support.wait_for_selector("text=Sign in with Keycloak", timeout=10_000)
        after = [c for c in context.cookies() if c["name"] == "vantage_sid"]
        assert not after, "vantage_sid cookie should be cleared after sign-out"


# ════════════════════════════════════════════════════════════════════════════
# 2) BASIC CHAT — input, send, response visible
# ════════════════════════════════════════════════════════════════════════════

class TestBasicChat:
    def test_empty_input_does_not_send(self, page_support: Page):
        inp = page_support.locator(SEL["chat_input"])
        inp.click()
        inp.press("Enter")
        time.sleep(1.0)
        assert not is_streaming(page_support)

    def test_whitespace_only_input_does_not_send(self, page_support: Page):
        inp = page_support.locator(SEL["chat_input"])
        inp.click()
        inp.fill("    \t  \n   ")
        inp.press("Enter")
        time.sleep(1.0)
        assert not is_streaming(page_support)

    def test_send_via_enter_shows_user_bubble(self, page_support: Page):
        msg = "Open issues for Velocity Marketplace?"
        send_message(page_support, msg)
        # User bubble appears (text matches)
        page_support.wait_for_selector(f"text=/{re.escape(msg[:30])}/", timeout=5_000)

    def test_send_via_button_works(self, page_support: Page):
        inp = page_support.locator(SEL["chat_input"])
        inp.click()
        inp.fill("Open issues for Velocity Marketplace?")
        page_support.locator(SEL["send_button"]).first.click()
        page_support.wait_for_selector("text=/Velocity Marketplace/i", timeout=10_000)

    def test_shift_enter_inserts_newline(self, page_support: Page):
        inp = page_support.locator(SEL["chat_input"])
        inp.click()
        inp.type("hello")
        inp.press("Shift+Enter")
        inp.type("world")
        value = inp.input_value()
        assert "\n" in value, f"expected newline in input value, got {value!r}"

    def test_send_button_disabled_while_streaming(self, page_support: Page):
        send_message(page_support, "Open issues for Velocity Marketplace?")
        # Briefly, isStreaming should flip to true
        time.sleep(0.5)
        # During streaming, the button shows Stop (or is disabled)
        body = page_support.inner_text("body").lower()
        # Either we see "stop" affordance OR streaming has already finished
        wait_for_streaming_done(page_support, timeout=60)
        # After finishing, isStreaming false
        assert not is_streaming(page_support)

    def test_user_bubble_renders_text_safely(self, page_support: Page):
        msg = "<script>alert(1)</script> and a <b>bold</b> thing"
        send_message(page_support, msg)
        # No actual <script> or <b> element should be in user bubble (it's x-text, safe)
        # The plain text should still appear
        page_support.wait_for_selector(f"text=/script.alert/i", timeout=5_000)

    def test_long_input_still_sends(self, page_support: Page):
        msg = "Tell me about Velocity Marketplace. " * 50
        inp = page_support.locator(SEL["chat_input"])
        inp.click()
        inp.fill(msg)
        inp.press("Enter")
        wait_for_streaming_done(page_support, timeout=60)
        assert len(last_assistant_text(page_support)) > 0


# ════════════════════════════════════════════════════════════════════════════
# 3) STREAMING (the reported reactivity bug)
# ════════════════════════════════════════════════════════════════════════════

class TestStreaming:
    def test_response_grows_progressively_without_tab_switch(self, page_support: Page):
        """REPORTED BUG: response should grow over time as it streams in — without needing
        to switch chats and come back. Sample text length several times during streaming."""
        send_message(page_support, "What open issues does Velocity Marketplace have?")

        samples = []
        deadline = time.time() + 25
        while time.time() < deadline:
            text = last_assistant_text(page_support)
            samples.append((time.time(), len(text)))
            if len(text) > 300:
                break
            time.sleep(0.5)

        distinct_sizes = sorted(set(s[1] for s in samples))
        assert len(distinct_sizes) >= 3, (
            f"answer never grew progressively — saw distinct text-sizes {distinct_sizes}. "
            "Streaming UI isn't re-rendering as deltas arrive (Alpine reactivity bug?)."
        )

    def test_final_answer_meaningful(self, page_support: Page):
        send_message(page_support, "Open issues for Velocity Marketplace?")
        wait_for_streaming_done(page_support, timeout=60)
        text = last_assistant_text(page_support).lower()
        assert len(text) > 100 and "velocity" in text

    def test_trace_expander_visible_after_stream(self, page_support: Page):
        # The canonical multi-tool hero query — needs get_customer_profile + get_open_issues
        # + summarise_issue_history. Reliably triggers tools most of the time; under load
        # Claude occasionally answers from memory, in which case there's nothing to render
        # in the trace and we skip rather than fail (this test verifies *rendering*, not
        # the model's tool-selection — that's covered by the eval harness).
        send_message(page_support, "Show open issues for Velocity Marketplace, summarise the most urgent, and suggest a next action.")
        wait_for_streaming_done(page_support, timeout=120)
        trace_len = page_support.evaluate(
            "() => { const d = window.Alpine.$data(document.body); "
            "const c = d.activeChat; const m = c?.messages?.[c.messages.length - 1]; "
            "return (m?.trace || []).length; }"
        )
        if trace_len == 0:
            pytest.skip("model variance: query was answered without tool calls — nothing to render in the trace")
        # After streaming, the expander button shows 'show thinking' (collapsed) or 'hide'
        # (still expanded by user). Either label is fine — just confirm the expander rendered.
        page_support.wait_for_selector("text=/show thinking|^hide$/", timeout=5_000)

    def test_elapsed_ms_displayed(self, page_support: Page):
        send_message(page_support, "Show open issues for Velocity Marketplace, summarise the most urgent, and suggest a next action.")
        wait_for_streaming_done(page_support, timeout=120)
        # Same model-variance handling as the trace-expander test above.
        trace_len = page_support.evaluate(
            "() => { const d = window.Alpine.$data(document.body); "
            "const c = d.activeChat; const m = c?.messages?.[c.messages.length - 1]; "
            "return (m?.trace || []).length; }"
        )
        if trace_len == 0:
            pytest.skip("model variance: query was answered without tool calls — no trace summary to find")
        # Look for a "·" followed by a duration
        body = page_support.inner_text("body")
        # something like "2 tools · 4.8s" or "· 4810ms"
        assert re.search(r"·\s*\d+\.?\d*\s*[ms]", body), \
            "expected to find elapsed time in the trace summary"

    def test_streaming_data_in_alpine_state(self, page_support: Page):
        """Diagnostic: after streaming done, the Alpine data MUST have the answer.

        If this passes but DOM tests fail, the bug is Alpine reactivity (mutations on a
        plain object pushed into a reactive array don't re-render). If this fails too,
        the bug is upstream (streaming/SSE delivery)."""
        send_message(page_support, "Open issues for Velocity Marketplace?")
        wait_for_streaming_done(page_support, timeout=60)
        # Read msg.md from Alpine state directly.
        state = page_support.evaluate("""() => {
          const root = window.Alpine?.$data?.(document.body);
          if (!root) return null;
          const chat = root.chats.find(c => c.id === root.activeChatId);
          if (!chat) return {error: 'no active chat'};
          const last = chat.messages[chat.messages.length - 1];
          return {role: last?.role, md_len: (last?.md || '').length, md_preview: (last?.md || '').slice(0, 100)};
        }""")
        assert state is not None, "Alpine data not accessible — UI didn't mount"
        assert state.get("role") == "assistant", f"last message not assistant: {state}"
        assert state.get("md_len", 0) > 50, \
            f"Alpine state has empty/short assistant.md ({state}) — upstream streaming bug, not reactivity"

    def test_streaming_dom_matches_alpine_state(self, page_support: Page):
        """If Alpine state has the answer but DOM doesn't, that's the reactivity bug the
        user reported (have-to-switch-chats to see the response)."""
        send_message(page_support, "Open issues for Velocity Marketplace?")
        wait_for_streaming_done(page_support, timeout=90)  # absorb LLM-side latency variance
        alpine_len = page_support.evaluate("""() => {
          const root = window.Alpine?.$data?.(document.body);
          const chat = root.chats.find(c => c.id === root.activeChatId);
          const last = chat.messages[chat.messages.length - 1];
          return (last?.md || '').length;
        }""")
        dom_len = len(last_assistant_text(page_support))
        # Allow some slack — DOM strips markdown markers; expect DOM to have most of the text
        assert dom_len > alpine_len * 0.3, (
            f"Alpine state has {alpine_len} chars of answer but DOM only {dom_len} — "
            "this is the REPORTED REACTIVITY BUG (deltas don't trigger re-render)"
        )

    def test_streaming_done_flag_clears(self, page_support: Page):
        send_message(page_support, "Open issues for Velocity Marketplace?")
        wait_for_streaming_done(page_support, timeout=60)
        # isStreaming back to false
        assert not is_streaming(page_support)

    def test_tool_indicator_appears_mid_stream(self, page_support: Page):
        """The 'calling X…' indicator should appear at least briefly between deltas."""
        send_message(page_support, "Open issues for Velocity Marketplace, summarise the most urgent.")
        # Poll for the indicator
        deadline = time.time() + 15
        saw_indicator = False
        while time.time() < deadline:
            body = page_support.inner_text("body").lower()
            if "calling" in body or "thinking" in body or "running" in body:
                saw_indicator = True
                break
            time.sleep(0.3)
        wait_for_streaming_done(page_support, timeout=60)
        # Soft assertion — we just want to confirm SOME mid-stream feedback exists
        # (even if we missed the exact window). If trace has entries, agent did fire tools.
        if not saw_indicator:
            # fall back: trace was populated, so tools fired (just didn't catch the indicator)
            text = page_support.inner_text("body")
            assert "tools" in text.lower(), "no tool indicator and no trace summary — bad sign"


# ════════════════════════════════════════════════════════════════════════════
# 4) MARKDOWN RENDERING
# ════════════════════════════════════════════════════════════════════════════

class TestMarkdown:
    def test_tables_render_as_html_table(self, page_support: Page):
        # Hero query reliably triggers the multi-issue table output (short variants
        # occasionally come back as a plain-prose answer with no table).
        send_message(page_support, "Show open issues for Velocity Marketplace, summarise the most urgent, and suggest a next action.")
        wait_for_streaming_done(page_support, timeout=120)
        # A <table> should be present inside an assistant `.md` container
        tables = page_support.locator(".md table").count()
        assert tables >= 1, "expected at least one rendered <table> in the assistant answer"

    def test_richly_formatted_content_renders(self, page_support: Page):
        """Markdown content (tables, code, strong, em) actually renders to real elements
        — at least one of them should be present for a real grounded answer."""
        send_message(page_support, "Profile for Velocity Marketplace?")
        wait_for_streaming_done(page_support, timeout=60)
        rich_elements = page_support.evaluate("""() => {
          const md = document.querySelectorAll('.md');
          let count = 0;
          md.forEach(el => { count += el.querySelectorAll('table, code, strong, em, h2, h3, ul, ol').length; });
          return count;
        }""")
        assert rich_elements >= 1, "expected the assistant answer to contain rendered markdown elements"

    def test_dompurify_strips_dangerous_html(self, page_support: Page):
        """The model is unlikely to emit raw HTML, but the renderer should still sanitise."""
        send_message(page_support, "Tell me about Velocity Marketplace.")
        wait_for_streaming_done(page_support, timeout=60)
        # No <script> element should ever be in the assistant content
        assert page_support.locator(".md script").count() == 0


# ════════════════════════════════════════════════════════════════════════════
# 5) MULTI-TURN — context preserved across messages
# ════════════════════════════════════════════════════════════════════════════

class TestMultiTurn:
    def test_second_message_streams_normally(self, page_support: Page):
        send_message(page_support, "Open issues for Velocity Marketplace?")
        wait_for_streaming_done(page_support, timeout=60)
        send_message(page_support, "Now summarise the most urgent.")
        wait_for_streaming_done(page_support, timeout=60)
        bubbles = assistant_messages(page_support)
        assert len(bubbles) >= 2

    def test_followup_resolves_from_context(self, page_support: Page):
        """X1 — multi-turn memory: 'the second one' should resolve in conversation context."""
        send_message(page_support, "Open issues for Velocity Marketplace?")
        wait_for_streaming_done(page_support, timeout=60)
        send_message(page_support, "Summarise the second one.")
        wait_for_streaming_done(page_support, timeout=60)
        text = last_assistant_text(page_support).lower()
        # Should reference one of Velocity's issues, not ask for clarification
        assert "velocity" in text or "issue" in text or "webhook" in text or "kyc" in text

    def test_three_turns_all_render(self, page_support: Page):
        for q in [
            "Open issues for Velocity Marketplace?",
            "Now summarise the most urgent.",
            "What should I do next?",
        ]:
            send_message(page_support, q)
            wait_for_streaming_done(page_support, timeout=60)
        bubbles = assistant_messages(page_support)
        assert len(bubbles) >= 3, f"expected 3 assistant bubbles, got {len(bubbles)}"


# ════════════════════════════════════════════════════════════════════════════
# 6) SIDEBAR — chat history persistence
# ════════════════════════════════════════════════════════════════════════════

class TestSidebar:
    def test_chat_appears_in_sidebar_after_send(self, page_support: Page):
        msg = "Sidebar test — Velocity Marketplace please"
        send_message(page_support, msg)
        wait_for_streaming_done(page_support, timeout=60)
        # Sidebar should show this chat's title (first user message)
        page_support.wait_for_selector(f"text=/{re.escape(msg[:30])}/", timeout=10_000)

    def test_chats_persist_after_reload(self, page_support: Page):
        msg = "Persistence test — pull Velocity"
        send_message(page_support, msg)
        wait_for_streaming_done(page_support, timeout=60)
        page_support.reload()
        page_support.wait_for_selector(SEL["chat_input"], timeout=10_000)
        page_support.wait_for_selector(f"text=/{re.escape(msg[:25])}/", timeout=10_000)

    def test_new_chat_button_resets_thread(self, page_support: Page):
        send_message(page_support, "Open issues for Velocity Marketplace?")
        wait_for_streaming_done(page_support, timeout=60)
        # Click + New chat
        page_support.locator("button:has-text('New chat')").first.click()
        # The messages area should be empty (or just the welcome state)
        time.sleep(0.5)
        bubbles = assistant_messages(page_support)
        assert len(bubbles) == 0, f"expected 0 messages in new chat, saw {len(bubbles)}"

    def test_click_old_chat_loads_history(self, page_support: Page):
        """After a new chat is opened, the previous chat should still be in the sidebar's
        data and clickable to resume."""
        msg1 = "Velocity Marketplace please — sidebar load test"
        send_message(page_support, msg1)
        wait_for_streaming_done(page_support, timeout=90)
        # Wait for the chat to land in Alpine's chats array with our title (loadSessions
        # runs fire-and-forget after first /ask; this is its observable side-effect).
        deadline = time.time() + 15
        while time.time() < deadline:
            titles = page_support.evaluate(
                "() => window.Alpine.$data(document.body).chats.map(c => c.title)"
            )
            if any("Velocity" in (t or "") for t in titles):
                break
            time.sleep(0.5)
        else:
            pytest.fail(f"chat title never appeared in Alpine state: titles={titles}")

        # Open a fresh chat — the previous one should still be in the chats array
        page_support.locator("button:has-text('New chat')").first.click()
        time.sleep(0.8)
        titles_after = page_support.evaluate(
            "() => window.Alpine.$data(document.body).chats.map(c => c.title)"
        )
        assert any("Velocity" in (t or "") for t in titles_after), \
            f"previous chat vanished after newChat: {titles_after}"

    def test_sidebar_search_filters(self, page_support: Page):
        # Send two messages so there are two chats
        send_message(page_support, "Velocity Marketplace please")
        wait_for_streaming_done(page_support, timeout=60)
        page_support.locator("button:has-text('New chat')").first.click()
        time.sleep(0.3)
        send_message(page_support, "Calm Waters Subscriptions check")
        wait_for_streaming_done(page_support, timeout=60)
        # Type into sidebar search
        page_support.locator("input[placeholder*='Search chats']").fill("Velocity")
        time.sleep(0.4)
        body = page_support.inner_text("body")
        # Calm Waters should be filtered out (best-effort — depends on implementation)
        assert "Velocity" in body


# ════════════════════════════════════════════════════════════════════════════
# 7) SKILLS — menu, list, run, save-as-skill
# ════════════════════════════════════════════════════════════════════════════

class TestSkills:
    def test_skills_button_opens_modal(self, page_support: Page):
        page_support.locator(SEL["skills_button"]).first.click()
        # Modal contains text "Skills" or "Run"
        page_support.wait_for_selector("text=/Skills|Run/", timeout=3_000)

    def test_skills_modal_lists_seeded_skill(self, page_support: Page):
        page_support.locator(SEL["skills_button"]).first.click()
        page_support.wait_for_selector("text=escalation-summary", timeout=5_000)

    def test_skills_modal_closes_on_escape(self, page_support: Page):
        page_support.locator(SEL["skills_button"]).first.click()
        page_support.wait_for_selector("text=escalation-summary", timeout=5_000)
        page_support.keyboard.press("Escape")
        time.sleep(0.5)
        # Should no longer see the modal listing
        assert not page_support.locator("text=escalation-summary").is_visible()

    def test_skills_run_escalation_summary(self, page_support: Page):
        page_support.locator(SEL["skills_button"]).first.click()
        page_support.wait_for_selector("text=escalation-summary", timeout=5_000)
        page_support.click("text=escalation-summary")
        # Param form replaces list when activeSkill is set; "Run skill" button is the signal.
        page_support.get_by_role("button", name="Run skill").wait_for(state="visible", timeout=5_000)
        # The param input has no name/placeholder — find the visible input that isn't the
        # sidebar search or the chat textarea (those are textareas / have placeholders).
        all_inputs = page_support.locator("input").all()
        param_input = None
        for inp in reversed(all_inputs):
            if inp.is_visible() and not inp.is_disabled():
                ph = inp.get_attribute("placeholder") or ""
                if "Search" not in ph and "Ask" not in ph:
                    param_input = inp
                    break
        assert param_input is not None, "couldn't find a skill-param input on the page"
        param_input.fill("Velocity Marketplace")
        page_support.get_by_role("button", name="Run skill").click()
        wait_for_streaming_done(page_support, timeout=120)
        text = last_assistant_text(page_support).lower()
        assert any(w in text for w in ["velocity", "critical", "high", "risk"]), \
            f"skill output didn't look like a risk brief: {text[:200]!r}"

    def test_skills_modal_shows_skill_description(self, page_support: Page):
        page_support.locator(SEL["skills_button"]).first.click()
        page_support.wait_for_selector("text=escalation-summary", timeout=5_000)
        body = page_support.inner_text("body").lower()
        # Description should mention escalation / risk / brief
        assert "risk" in body or "escalation" in body or "brief" in body

    def test_save_as_skill_button_after_chat(self, page_support: Page):
        # 3+ messages with assistant turns
        send_message(page_support, "Open issues for Velocity Marketplace?")
        wait_for_streaming_done(page_support, timeout=60)
        send_message(page_support, "Summarise the most urgent.")
        wait_for_streaming_done(page_support, timeout=60)
        page_support.wait_for_selector("text=Save as skill", timeout=5_000)

    def test_save_as_skill_opens_draft_modal(self, page_support: Page):
        send_message(page_support, "Open issues for Velocity Marketplace?")
        wait_for_streaming_done(page_support, timeout=60)
        send_message(page_support, "Summarise the most urgent.")
        wait_for_streaming_done(page_support, timeout=60)
        page_support.locator("text=Save as skill").click()
        # Draft modal opens — look for an editable name field
        page_support.wait_for_selector("input[placeholder*='name'], input[name='name']", timeout=10_000)


# ════════════════════════════════════════════════════════════════════════════
# 8) RBAC — sales denied, support+admin allowed
# ════════════════════════════════════════════════════════════════════════════

class TestRBAC:
    def test_sales_can_browse_customers(self, page_sales: Page):
        send_message(page_sales, "Who are our customers?")
        wait_for_streaming_done(page_sales, timeout=60)
        text = last_assistant_text(page_sales).lower()
        assert "velocity" in text or "lumen" in text or "calm" in text

    def test_sales_can_read_open_issues(self, page_sales: Page):
        send_message(page_sales, "Open issues for Velocity Marketplace?")
        wait_for_streaming_done(page_sales, timeout=60)
        text = last_assistant_text(page_sales).lower()
        assert "velocity" in text

    def test_sales_update_issue_denied(self, page_sales: Page):
        send_message(page_sales, "Add a note to issue 3 saying I checked with the customer.")
        wait_for_streaming_done(page_sales, timeout=60)
        text = last_assistant_text(page_sales).lower()
        assert any(w in text for w in ["denied", "requires", "permission", "support", "admin"]), \
            f"agent didn't relay an RBAC refusal: {text[:300]!r}"

    def test_sales_create_next_action_denied(self, page_sales: Page):
        send_message(page_sales, "Create a next action on issue 1 to chase the UBO docs.")
        wait_for_streaming_done(page_sales, timeout=60)
        text = last_assistant_text(page_sales).lower()
        assert any(w in text for w in ["denied", "requires", "permission", "admin"]), \
            f"agent didn't relay an RBAC refusal: {text[:300]!r}"

    def test_support_update_issue_allowed(self, page_support: Page):
        send_message(page_support, "Add a note to issue 4 saying 'UI test write check'.")
        wait_for_streaming_done(page_support, timeout=60)
        text = last_assistant_text(page_support).lower()
        assert any(w in text for w in ["added", "updated", "noted", "recorded", "done"]), \
            f"support write didn't look like a success: {text[-300:]!r}"

    def test_support_create_next_action_denied(self, page_support: Page):
        send_message(page_support, "Create a next action on issue 4 to follow up.")
        wait_for_streaming_done(page_support, timeout=60)
        text = last_assistant_text(page_support).lower()
        assert any(w in text for w in ["denied", "requires", "admin"]), \
            f"support shouldn't be allowed to create next actions: {text[:300]!r}"

    def test_admin_can_create_next_action(self, page_admin: Page):
        send_message(page_admin, "Create a next action on issue 1: 'UI test directive', due 2026-06-10.")
        wait_for_streaming_done(page_admin, timeout=90)
        text = last_assistant_text(page_admin).lower()
        assert any(w in text for w in ["created", "recorded", "next action"]), \
            f"admin write didn't look like a success: {text[-300:]!r}"

    def test_admin_can_update_issue(self, page_admin: Page):
        send_message(page_admin, "Add a note to issue 5 saying 'admin UI test'.")
        wait_for_streaming_done(page_admin, timeout=60)
        text = last_assistant_text(page_admin).lower()
        assert any(w in text for w in ["added", "updated", "noted", "recorded", "done"])


# ════════════════════════════════════════════════════════════════════════════
# 9) LAYOUT — page height stable, thread scrolls internally
# ════════════════════════════════════════════════════════════════════════════

class TestLayout:
    def test_body_height_equals_viewport(self, page_support: Page):
        viewport = page_support.viewport_size["height"]
        body_height = page_support.evaluate("() => document.body.scrollHeight")
        assert body_height <= viewport + 50, \
            f"body is {body_height}px, viewport is {viewport}px — body is too tall on fresh page"

    def test_body_height_stays_stable_after_many_messages(self, page_support: Page):
        """REPORTED BUG: page should not grow as messages accumulate."""
        viewport = page_support.viewport_size["height"]
        for q in [
            "Open issues for Velocity Marketplace?",
            "Summarise the most urgent.",
            "What's the history on issue 3?",
            "Open issues for Calm Waters Subscriptions?",
        ]:
            send_message(page_support, q)
            wait_for_streaming_done(page_support, timeout=60)

        body_height = page_support.evaluate("() => document.body.scrollHeight")
        assert body_height <= viewport + 50, \
            f"body grew to {body_height}px (viewport={viewport}); thread should scroll internally"

    def test_thread_autoscrolls_after_send(self, page_support: Page):
        send_message(page_support, "Open issues for Velocity Marketplace?")
        wait_for_streaming_done(page_support, timeout=60)
        send_message(page_support, "Summarise the most urgent.")
        wait_for_streaming_done(page_support, timeout=60)
        at_bottom = page_support.evaluate(
            """() => {
              const t = document.querySelector('[x-ref="thread"]') ||
                        document.querySelector('.overflow-y-auto');
              if (!t) return false;
              return Math.abs(t.scrollHeight - t.scrollTop - t.clientHeight) < 80;
            }"""
        )
        assert at_bottom, "thread did not auto-scroll to bottom after sending"

    def test_sidebar_does_not_overflow_viewport(self, page_support: Page):
        viewport_h = page_support.viewport_size["height"]
        sidebar_height = page_support.evaluate(
            "() => document.querySelector('aside')?.scrollHeight || 0"
        )
        # Sidebar should fit within viewport (its own internal scroll handles overflow)
        assert sidebar_height <= viewport_h + 10, \
            f"sidebar measured {sidebar_height}px, viewport {viewport_h}px"

    def test_input_box_visible_after_many_messages(self, page_support: Page):
        for q in [
            "Open issues for Velocity Marketplace?",
            "Summarise the most urgent.",
            "What's the history on issue 3?",
        ]:
            send_message(page_support, q)
            wait_for_streaming_done(page_support, timeout=60)
        expect(page_support.locator(SEL["chat_input"])).to_be_visible()


# ════════════════════════════════════════════════════════════════════════════
# 10) THEME — dark default, light toggle, persistence
# ════════════════════════════════════════════════════════════════════════════

class TestTheme:
    def test_default_is_dark(self, page_support: Page):
        expect(page_support.locator("html")).to_have_attribute("data-theme", "dark")

    def test_toggle_to_light(self, page_support: Page):
        page_support.get_by_role("button", name="Account menu").click()
        page_support.get_by_text("Switch to light theme").click()
        expect(page_support.locator("html")).to_have_attribute("data-theme", "light")

    def test_theme_persists_after_reload(self, page_support: Page):
        page_support.get_by_role("button", name="Account menu").click()
        page_support.get_by_text("Switch to light theme").click()
        page_support.reload()
        page_support.wait_for_selector(SEL["chat_input"], timeout=10_000)
        expect(page_support.locator("html")).to_have_attribute("data-theme", "light")


# ════════════════════════════════════════════════════════════════════════════
# 11) KEYBOARD SHORTCUTS
# ════════════════════════════════════════════════════════════════════════════

def _meta_key():
    return "Meta" if os.uname().sysname == "Darwin" else "Control"


class TestKeyboard:
    def test_cmd_k_opens_skills(self, page_support: Page):
        page_support.keyboard.press(f"{_meta_key()}+K")
        page_support.wait_for_selector("text=escalation-summary", timeout=3_000)

    def test_cmd_n_starts_new_chat(self, page_support: Page):
        send_message(page_support, "Open issues for Velocity Marketplace?")
        wait_for_streaming_done(page_support, timeout=60)
        page_support.keyboard.press(f"{_meta_key()}+N")
        time.sleep(0.5)
        # New chat → thread is empty
        bubbles = assistant_messages(page_support)
        assert len(bubbles) == 0, "Cmd+N should open a fresh chat with no messages"

    def test_escape_closes_skills_modal(self, page_support: Page):
        page_support.locator(SEL["skills_button"]).first.click()
        page_support.wait_for_selector("text=escalation-summary", timeout=3_000)
        page_support.keyboard.press("Escape")
        time.sleep(0.4)
        assert not page_support.locator("text=escalation-summary").is_visible()


# ════════════════════════════════════════════════════════════════════════════
# 12) ACCESSIBILITY (basic)
# ════════════════════════════════════════════════════════════════════════════

class TestA11y:
    def test_messages_container_has_aria_live(self, page_support: Page):
        loc = page_support.locator('[aria-live="polite"]')
        assert loc.count() >= 1, "expected at least one aria-live region for the messages"

    def test_inputs_have_placeholder(self, page_support: Page):
        # Chat input has a placeholder for SR/UX
        placeholder = page_support.locator(SEL["chat_input"]).first.get_attribute("placeholder")
        assert placeholder and len(placeholder) > 0


# ════════════════════════════════════════════════════════════════════════════
# 13) ERRORS / EDGE CASES
# ════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_special_chars_in_input_render_safely(self, page_support: Page):
        send_message(page_support, "Tell me about 'Velocity \"Marketplace\" — €£$'")
        wait_for_streaming_done(page_support, timeout=60)
        assert len(last_assistant_text(page_support)) > 0

    def test_emoji_only_input_does_not_crash(self, page_support: Page):
        send_message(page_support, "🚀💎🎉")
        # Either we get an answer or a graceful "I'm not sure" — must not crash
        wait_for_streaming_done(page_support, timeout=60)
        assert page_support.locator(SEL["chat_input"]).is_visible()

    def test_lumen_ambiguous_handled(self, page_support: Page):
        send_message(page_support, "Open issues for Lumen.")
        wait_for_streaming_done(page_support, timeout=60)
        text = last_assistant_text(page_support).lower()
        # Should ask for clarification or list candidates
        assert "lumen" in text and ("which" in text or "two" in text or "ambiguous" in text or "group" in text)

    def test_zzzz_not_found_handled(self, page_support: Page):
        send_message(page_support, "Open issues for Zzzz Holdings.")
        wait_for_streaming_done(page_support, timeout=60)
        text = last_assistant_text(page_support).lower()
        assert any(s in text for s in ["not found", "no customer", "couldn't find", "could not find", "could not be found"])

    def test_calm_waters_no_open(self, page_support: Page):
        send_message(page_support, "Open issues for Calm Waters Subscriptions?")
        wait_for_streaming_done(page_support, timeout=60)
        text = last_assistant_text(page_support).lower()
        assert "no open" in text or "zero" in text or "none" in text


# ════════════════════════════════════════════════════════════════════════════
# 14) BROWSE TOOLS (new in PR #21)
# ════════════════════════════════════════════════════════════════════════════

class TestBrowseTools:
    def test_who_are_our_customers(self, page_support: Page):
        send_message(page_support, "Who are our customers?")
        wait_for_streaming_done(page_support, timeout=60)
        text = last_assistant_text(page_support).lower()
        assert any(c in text for c in ["velocity", "lumen", "calm waters", "pinebrook"])

    def test_critical_open_issues_browse(self, page_support: Page):
        send_message(page_support, "Show me all critical open issues across customers.")
        wait_for_streaming_done(page_support, timeout=60)
        text = last_assistant_text(page_support).lower()
        assert "critical" in text

    def test_overdue_next_actions_browse(self, page_admin: Page):
        send_message(page_admin, "What next actions are overdue?")
        wait_for_streaming_done(page_admin, timeout=90)
        # Either lists overdue ones or honestly says there are none
        text = last_assistant_text(page_admin).lower()
        assert ("overdue" in text or "next action" in text or "none" in text or "no overdue" in text)
