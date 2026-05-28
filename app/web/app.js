// prototype-app.js — Alpine state + mocked agent for Vantage.
// No backend; all responses are scripted to mirror the real seed data
// (db/seed.sql) and RBAC matrix (Vantage-vault/02-User-Stories.md).

const md = window.markdownit({ html: false, linkify: true, breaks: false, typographer: true });

function renderMd(text) {
  if (!text) return "";
  return window.DOMPurify.sanitize(md.render(text));
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let MID = 1; // monotonic message id

function uid(prefix = "id") { return `${prefix}-${Math.random().toString(36).slice(2, 9)}`; }
function previewArgs(args) {
  return Object.entries(args)
    .map(([k, v]) => `${k}: ${typeof v === "string" ? JSON.stringify(v) : v}`)
    .join(", ");
}

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const SLOW = reducedMotion ? 0.05 : 1; // multiplier; near-zero when reduced motion is on

// ─────────────────────────────────────────────────────────────────────────────
// Roles & RBAC (matches Vantage-vault/02-User-Stories.md role × tool matrix)
// ─────────────────────────────────────────────────────────────────────────────
const ROLE_TOOLS = {
  sales:   new Set(["get_customer_profile", "get_open_issues", "summarise_issue_history"]),
  support: new Set(["get_customer_profile", "get_open_issues", "summarise_issue_history", "update_issue"]),
  admin:   new Set(["get_customer_profile", "get_open_issues", "summarise_issue_history", "update_issue", "create_next_action", "update_next_action"]),
};

function roleAllows(role, tool) { return ROLE_TOOLS[role].has(tool); }

// ─────────────────────────────────────────────────────────────────────────────
// Seed chats (the pre-existing sidebar history)
// ─────────────────────────────────────────────────────────────────────────────
function seedChats() {
  return [
    { id: "c1", title: "Velocity Marketplace — risk brief before the renewal call", time: "2m ago", group: "Today", messages: heroConversation() },
    { id: "c2", title: "Set 5-day deadline on the UBO escalation, assign Marcus",    time: "11m ago", group: "Today", messages: [] },
    { id: "c3", title: "Pinebrook Retail — what's blocking PB-5240?",                time: "3h ago",  group: "Today", messages: [] },
    { id: "c4", title: "Lumen Commerce — which one has the delayed payout?",         time: "Yesterday", group: "Yesterday", messages: lumenConversation() },
    { id: "c5", title: "Quartz Talent — open access requests across the team",       time: "Yesterday", group: "Yesterday", messages: [] },
    { id: "c6", title: "Calm Waters Subscriptions — anything open?",                 time: "Mon",      group: "Last 7 days", messages: calmConversation() },
    { id: "c7", title: "Cross-customer integration issues this week",                time: "Sun",      group: "Last 7 days", messages: [] },
  ];
}

// ─────────────────────────────────────────────────────────────────────────────
// Pre-rendered conversations for the chats that aren't blank
// ─────────────────────────────────────────────────────────────────────────────
function heroConversation() {
  return [
    {
      id: MID++, role: "user",
      text: "Show open issues for Velocity Marketplace, summarise the most urgent, and suggest a next action.",
    },
    {
      id: MID++, role: "assistant",
      md: `**Velocity Marketplace** (\`ACME-76085\`, Enterprise, South East) has **4 open issues**. The most urgent is the **webhook signature mismatch** after their key rotation — go-live is effectively blocked until they finish redeploying the new signing secret across all workers.

### Open issues

| # | Issue | Cat. | Priority | Status | Age |
|---|---|---|---|---|---|
| 3 | Webhook delivery failing — signature mismatch after key rotation | integration | **critical** | open | 7d |
| 1 | KYC review blocking marketplace go-live | onboarding | **critical** | in_progress | 97d |
| 2 | Repeated payout failures to connected accounts | payments | high | in_progress | 35d |
| 4 | Dashboard latency during the settlement window | performance | medium | pending | 16d |

### Most urgent — issue #3 · Webhook signature mismatch

After the customer rotated their API signing secret, all webhook deliveries from us are rejected at their endpoint with \`HTTP 401 invalid signature\`. They redeployed one service, but **a second worker still uses the cached old secret** — that's the live blocker. \`payment_succeeded\` events aren't reaching them, so order fulfilment is stalled.

### Recommended next action

Push the customer for a **full rollout of the new signing secret** across every worker, with a 48-hour deadline. Once we observe one clean delivery batch, downgrade the priority.

*advice only — recording a formal next action is admin-only*`,
      trace: [
        { tool: "get_customer_profile", argPreview: 'name: "Velocity Marketplace"', status: "found", ms: 64 },
        { tool: "get_open_issues",      argPreview: "customer_id: 1",                status: "found", ms: 71 },
        { tool: "summarise_issue_history", argPreview: "issue_id: 3",                status: "found", ms: 142 },
      ],
      elapsedMs: 4812,
    },
  ];
}

function lumenConversation() {
  return [
    { id: MID++, role: "user", text: "open issues for Lumen Commerce" },
    {
      id: MID++, role: "assistant",
      md: `That name matches **two** customers — I don't want to silently pick one. Could you confirm which?

| # | Name | Account ref | Region | Tier |
|---|---|---|---|---|
| 2 | Lumen Commerce | \`ACME-53063\` | North West | premium |
| 3 | Lumen Commerce Group | \`ACME-32819\` | Scotland | strategic |`,
      trace: [
        { tool: "get_customer_profile", argPreview: 'name: "Lumen Commerce"', status: "ambiguous", ms: 38 },
      ],
      elapsedMs: 412,
    },
    { id: MID++, role: "user", text: "Lumen Commerce Group — the Scottish one with the delayed payout." },
    {
      id: MID++, role: "assistant",
      md: `**Lumen Commerce Group** (\`ACME-32819\`, Scotland, strategic) has 1 open high-priority issue:

- **Issue #9 — Payout delayed beyond schedule.** Held by automated risk review after an unusual volume spike. Cleared 2 days ago; payout re-queued and the customer notified of the new arrival window. Nothing currently blocked — safe to mark resolved on the next confirmation.`,
      trace: [
        { tool: "get_customer_profile", argPreview: 'name: "Lumen Commerce Group"', status: "found", ms: 41 },
        { tool: "get_open_issues",      argPreview: "customer_id: 3",                status: "found", ms: 58 },
        { tool: "summarise_issue_history", argPreview: "issue_id: 9",                status: "found", ms: 96 },
      ],
      elapsedMs: 2104,
    },
  ];
}

function calmConversation() {
  return [
    { id: MID++, role: "user", text: "Calm Waters Subscriptions — anything open?" },
    {
      id: MID++, role: "assistant",
      md: `**Calm Waters Subscriptions** (\`ACME-21090\`, SMB, South West) has **no open issues** right now. The three issues on record (proration question, SSO setup, sandbox webhook test) are all resolved or closed.

Nothing to flag ahead of a renewal conversation — risk: **Low**.`,
      trace: [
        { tool: "get_customer_profile", argPreview: 'name: "Calm Waters Subscriptions"', status: "found", ms: 52 },
        { tool: "get_open_issues",      argPreview: "customer_id: 4",                     status: "not_found", ms: 47 },
      ],
      elapsedMs: 1208,
    },
  ];
}

// ─────────────────────────────────────────────────────────────────────────────
// Mock agent — routes a user query to a scripted response
// Returns: { tools: [...{tool, args, argPreview, status, ms, mustAllow}], md, elapsedMs }
//   mustAllow=true → if RBAC blocks the tool, the scripted call becomes denied.
// ─────────────────────────────────────────────────────────────────────────────
function routeQuery(text, role) {
  const q = text.toLowerCase();

  // E1 not_found
  if (/zzzz|globex foobar|unknownco|absent customer/i.test(q)) {
    return {
      tools: [
        { tool: "get_customer_profile", args: { name: pickCustomerWord(text) || "Zzzz Holdings Ltd" }, status: "not_found", ms: 58 },
      ],
      md: `No matching customer for **"${pickCustomerWord(text) || "Zzzz Holdings Ltd"}"**. I checked by name and got no hit — I won't guess at a close match. If you have an account reference (\`ACME-…\`) I can look it up directly.`,
      elapsedMs: 720,
    };
  }

  // E2 ambiguous (Lumen)
  if (/lumen(?!\s*commerce\s*group)/i.test(q) && !/group/i.test(q)) {
    return {
      tools: [
        { tool: "get_customer_profile", args: { name: "Lumen Commerce" }, status: "ambiguous", ms: 39 },
      ],
      md: `That name matches **two** customers — I don't want to silently pick one. Could you confirm which?

| # | Name | Account ref | Region | Tier |
|---|---|---|---|---|
| 2 | Lumen Commerce | \`ACME-53063\` | North West | premium |
| 3 | Lumen Commerce Group | \`ACME-32819\` | Scotland | strategic |`,
      elapsedMs: 480,
    };
  }

  // E3 / Calm Waters → no open
  if (/calm waters/i.test(q)) {
    return {
      tools: [
        { tool: "get_customer_profile", args: { name: "Calm Waters Subscriptions" }, status: "found", ms: 51 },
        { tool: "get_open_issues",      args: { customer_id: 4 },                     status: "not_found", ms: 46 },
      ],
      md: `**Calm Waters Subscriptions** has **no open issues**. The three on record are resolved or closed. Risk before a renewal call: **Low**.`,
      elapsedMs: 1100,
    };
  }

  // Velocity / KYC blocker — the headline query
  if (/velocity|kyc|webhook|signature/i.test(q) && /open|issue|risk|brief|urgent|next|kyc|block/i.test(q)) {
    return {
      tools: [
        { tool: "get_customer_profile", args: { name: "Velocity Marketplace" }, status: "found", ms: 64 },
        { tool: "get_open_issues",      args: { customer_id: 1 },                status: "found", ms: 71 },
        { tool: "summarise_issue_history", args: { issue_id: 3 },                status: "found", ms: 142 },
      ],
      md: `**Velocity Marketplace** (\`ACME-76085\`, Enterprise, South East) has **4 open issues**. The most urgent is the **webhook signature mismatch** after their key rotation — go-live is effectively blocked until they finish redeploying the new signing secret across all workers.

### Open issues

| # | Issue | Cat. | Priority | Status | Age |
|---|---|---|---|---|---|
| 3 | Webhook delivery failing — signature mismatch after key rotation | integration | **critical** | open | 7d |
| 1 | KYC review blocking marketplace go-live | onboarding | **critical** | in_progress | 97d |
| 2 | Repeated payout failures to connected accounts | payments | high | in_progress | 35d |
| 4 | Dashboard latency during the settlement window | performance | medium | pending | 16d |

### Most urgent — issue #3 · Webhook signature mismatch

After the customer rotated their API signing secret, all webhook deliveries are rejected at their endpoint with \`HTTP 401 invalid signature\`. They redeployed one service, but **a second worker still uses the cached old secret** — that's the live blocker.

### Recommended next action

Push the customer for a **full rollout of the new signing secret** across every worker with a 48-hour deadline. Downgrade priority after one clean delivery batch.`,
      elapsedMs: 4640,
    };
  }

  // Write paths
  // (a) create / record next action → admin-only
  if (/record|create|set\b|add\b/.test(q) && /next action|deadline|directive/.test(q)) {
    return {
      tools: [
        { tool: "create_next_action",
          args: { issue_id: 1, due_date: "2026-06-02", assignee: "marcus.webb" },
          status: roleAllows(role, "create_next_action") ? "created" : "denied",
          ms: roleAllows(role, "create_next_action") ? 188 : 71,
          mustAllow: true,
        },
      ],
      md: roleAllows(role, "create_next_action")
        ? `Recorded. Created next action **NA-118** on issue **#1 — KYC review blocking go-live**, due **2026-06-02** (5 days), assigned to **Marcus Webb**.

\`\`\`json
{
  "id": 118,
  "issue_id": 1,
  "description": "Chase customer for certified second-UBO ID and the source-of-funds questionnaire; escalate to compliance lead if not received by deadline.",
  "due_date": "2026-06-02",
  "assignee": "marcus.webb",
  "status": "open",
  "created_by": "${currentUserKey(role)}",
  "created_at": "2026-05-28T14:21:08Z"
}
\`\`\`

It's now visible on the issue for the rest of the team.`
        : `I couldn't record that — your role (\`${role}_user\`) doesn't permit creating next actions. Only **admin** can record formal next actions. Your draft has been kept here; I can hand it to an admin colleague, or reword it as advice in this chat.`,
      elapsedMs: roleAllows(role, "create_next_action") ? 1124 : 580,
    };
  }

  // (b) add note / update issue → support + admin
  if (/(add|leave)\s+a?\s*note|update\s+issue|status.*(resolved|in_progress|in progress|closed)|mark.*(resolved|closed|in.progress)/i.test(q)) {
    return {
      tools: [
        { tool: "update_issue",
          args: { issue_id: 3, note: "asked them to redeploy worker B by Friday" },
          status: roleAllows(role, "update_issue") ? "updated" : "denied",
          ms: roleAllows(role, "update_issue") ? 121 : 89,
          mustAllow: true,
        },
      ],
      md: roleAllows(role, "update_issue")
        ? `Recorded a note on **issue #3 — Webhook signature mismatch**:

> asked them to redeploy worker B by Friday

Attributable to **${displayUser(role)}**, timestamp \`2026-05-28T14:23:11Z\`. Visible on the next read of the issue.`
        : `I couldn't add that note — your role (\`${role}_user\`) doesn't permit writes to issues. Updating issue notes requires **support** or **admin**. The text of your note has been kept here; ask a support teammate to record it, or I can draft a paste-ready handoff if helpful.`,
      elapsedMs: roleAllows(role, "update_issue") ? 920 : 380,
    };
  }

  // simulate network error
  if (/^trigger error|^error\b|^break it|crash/.test(q)) {
    return { error: "The MCP server returned <code>502 upstream_timeout</code> after 12.4s while running <code>summarise_issue_history</code>. Your message wasn't lost — retry or rephrase." };
  }

  // generic fallback — show the agent reasoning but with a soft answer
  return {
    tools: [
      { tool: "get_customer_profile", args: { name: pickCustomerWord(text) || "the named customer" }, status: "not_found", ms: 64 },
    ],
    md: `I didn't find enough specifics in that question to answer with confidence — could you tell me which customer (or issue id) you mean? You can also pick one of the prompts on the empty-chat screen to see a worked example.`,
    elapsedMs: 720,
  };
}

function pickCustomerWord(text) {
  // crude: extract a Capitalised Phrase if present
  const m = text.match(/([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)/);
  return m ? m[1] : null;
}

function currentUserKey(role) {
  return { sales: "priya.nair", support: "marcus.webb", admin: "dana.okafor" }[role];
}
function displayUser(role) {
  return { sales: "Priya Nair", support: "Marcus Webb", admin: "Dana Okafor" }[role];
}

// ─────────────────────────────────────────────────────────────────────────────
// Alpine component
// ─────────────────────────────────────────────────────────────────────────────
window.vantage = function () {
  return {
    // identity — `me` comes from GET /auth/whoami (real Keycloak session via httpOnly
    // BFF cookie; the access token never reaches the browser). authStatus: 'checking' on
    // first load, 'authed' once whoami returns 200, 'guest' if 401 (sign-in card shown).
    authStatus: "checking",
    me: null,
    role: "admin",   // active-role key the UI binds to; reset from /auth/whoami
    get user() {
      if (this.me) {
        const initials = (this.me.username || "?").slice(0, 2).toUpperCase();
        return { name: this.me.username, initials, email: `${this.me.username}@acme.test` };
      }
      return { sales: { name: "Priya Nair", initials: "PN", email: "sales@acme.test" },
               support: { name: "Marcus Webb", initials: "MW", email: "support@acme.test" },
               admin: { name: "Dana Okafor", initials: "DO", email: "admin@acme.test" }
             }[this.role];
    },

    // chats
    chats: [],
    activeChatId: "c1",
    search: "",

    // composer
    input: "",
    isStreaming: false,
    cancelRequested: false,

    // theme
    theme: "dark",

    // overlays
    showSkillsMenu: false,
    activeSkill: null,
    skillParams: {},
    skillsSearch: "",
    showSaveSkill: false,
    skillDraft: { name: "", description: "", instructions: "", parameters: [], allowed_tools: [] },
    showUserMenu: false,

    // toast
    toast: "",

    // skills library (seeded + authored)
    skills: [
      {
        name: "escalation-summary",
        description: "Customer escalation/risk brief: open issues, most urgent summarised, overall risk level (Low/Med/High/Critical), recommended next action.",
        parameters: [{ name: "customer", description: "Customer name (or partial name).", required: true }],
        allowed_tools: ["get_open_issues", "summarise_issue_history"],
        authored: false,
      },
      {
        name: "handoff-brief",
        description: "One-paragraph paste-ready brief for a support or compliance handoff on a specific issue.",
        parameters: [{ name: "issue_id", description: "Issue id to brief (e.g. 3).", required: true }],
        allowed_tools: ["summarise_issue_history"],
        authored: true, authoredBy: "dana",
      },
    ],

    // computed
    get activeChat() { return this.chats.find(c => c.id === this.activeChatId); },
    get messages()   { return this.activeChat?.messages || []; },
    get starterChips() {
      return [
        "Open issues for `Velocity Marketplace`",
        "Risk brief for `Calm Waters Subscriptions`",
        "What's blocking the KYC review on issue `#1`?",
      ];
    },
    get chatGroups() {
      const q = this.search.trim().toLowerCase();
      const filtered = this.chats.filter(c => !q || c.title.toLowerCase().includes(q));
      const order = ["Today", "Yesterday", "Last 7 days", "Earlier"];
      return order
        .map(label => ({ label, items: filtered.filter(c => c.group === label) }))
        .filter(g => g.items.length > 0);
    },
    get filteredSkills() {
      const q = this.skillsSearch.trim().toLowerCase();
      if (!q) return this.skills;
      return this.skills.filter(s => s.name.includes(q) || s.description.toLowerCase().includes(q));
    },

    // lifecycle
    init() {
      this.chats = seedChats();
      // restore theme
      const saved = localStorage.getItem("vantage.theme");
      if (saved === "light" || saved === "dark") this.setTheme(saved);
      // ⌘K opens skills
      window.addEventListener("keydown", (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
          e.preventDefault();
          this.openSkillsMenu();
        }
        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "n") {
          e.preventDefault();
          this.newChat();
        }
      });
      this.$nextTick(() => this.scrollToEnd());
      // Ask the backend who's logged in (cookie flows automatically).
      this.whoami();
    },

    // auth — bootstrap, sign in, sign out
    async whoami() {
      try {
        const r = await fetch("/auth/whoami", { credentials: "include" });
        if (r.status === 401) { this.authStatus = "guest"; return; }
        if (!r.ok) throw new Error(`whoami ${r.status}`);
        const data = await r.json();
        this.me = data;
        // Map realm roles → the UI's role key. First match wins; default to lowest priv.
        const roleMap = { admin: "admin", support_user: "support", sales_user: "sales" };
        const matched = (data.roles || []).map((r) => roleMap[r]).find(Boolean);
        if (matched) this.role = matched;
        this.authStatus = "authed";
      } catch (e) {
        this.authStatus = "guest";
      }
    },
    signIn()  { window.location.href = "/auth/login"; },
    signOut() { window.location.href = "/auth/logout"; },

    // theme
    setTheme(t) { this.theme = t; document.documentElement.setAttribute("data-theme", t); localStorage.setItem("vantage.theme", t); },
    toggleTheme() { this.setTheme(this.theme === "dark" ? "light" : "dark"); },

    // role helpers
    setRole(r) {
      this.role = r;
      this.flash(`Role switched to ${this.roleLabel(r)} — try a write to see RBAC live.`);
    },
    roleLabel(r) { return { sales: "sales", support: "support", admin: "admin" }[r]; },
    roleSubLabel(r) { return { sales: "read-only", support: "read + update issues", admin: "full access" }[r]; },
    roleBadgeClass(r) {
      if (r === "admin")   return "border-accentedge text-accent bg-accentsoft";
      if (r === "support") return "border-[oklch(0.66_0.14_220_/_0.4)] text-[oklch(0.78_0.12_220)] bg-[oklch(0.74_0.12_220_/_0.10)]";
      return                       "border-[oklch(0.65_0.12_160_/_0.4)] text-[oklch(0.78_0.11_155)] bg-[oklch(0.74_0.11_155_/_0.10)]";
    },
    roleDotStyle(r) {
      if (r === "admin")   return "background: var(--accent);";
      if (r === "support") return "background: oklch(0.78 0.12 220);";
      return "background: oklch(0.78 0.11 155);";
    },
    traceStatusClass(s) {
      if (["found", "updated", "created"].includes(s)) return "bg-[oklch(0.74_0.11_155_/_0.14)] text-[oklch(0.74_0.11_155)]";
      if (s === "denied") return "bg-[oklch(0.68_0.16_25_/_0.14)] text-[oklch(0.78_0.14_25)]";
      if (s === "ambiguous") return "bg-[oklch(0.80_0.13_75_/_0.14)] text-[oklch(0.86_0.13_75)]";
      return "bg-surface text-textmuted";
    },

    formatChip(s) {
      // turn `text` into a code-styled span
      return s.replace(/`([^`]+)`/g, '<code class="mono text-[12px] px-1.5 py-0.5 rounded bg-bg border border-linesoft text-[oklch(0.85_0.06_45)]">$1</code>');
    },

    // chat lifecycle
    newChat() {
      const id = uid("chat");
      this.chats.unshift({ id, title: "", time: "now", group: "Today", messages: [] });
      this.activeChatId = id;
      this.input = "";
      this.$nextTick(() => this.scrollToEnd());
    },
    openChat(id) {
      this.activeChatId = id;
      this.cancelRequested = true;
      this.$nextTick(() => this.scrollToEnd());
    },

    // sending
    ask(promptWithMaybeBackticks) {
      // The starter chips have backticks for "code" formatting in display; strip for the actual query
      this.input = promptWithMaybeBackticks.replace(/`/g, "");
      this.send();
    },

    async send() {
      const text = this.input.trim();
      if (!text || this.isStreaming) return;
      const chat = this.activeChat;
      if (!chat) return;
      this.input = "";

      // title from the first message
      if (!chat.title) chat.title = text.length > 64 ? text.slice(0, 64) + "…" : text;

      // push user message
      chat.messages.push({ id: MID++, role: "user", text });
      this.$nextTick(() => this.scrollToEnd());

      await this.runAgent(chat, text);
    },

    async runAgent(chat, text) {
      const route = routeQuery(text, this.role);
      const ass = {
        id: MID++, role: "assistant", md: "", trace: [], elapsedMs: 0,
        streaming: true, currentTool: null, errored: null,
      };
      chat.messages.push(ass);
      this.isStreaming = true;
      this.cancelRequested = false;

      // network error path
      if (route.error) {
        await sleep(900 * SLOW);
        if (this.cancelRequested) return this.finishStreaming(ass);
        ass.errored = route.error;
        return this.finishStreaming(ass);
      }

      // tool-call loop
      const start = performance.now();
      for (const t of route.tools) {
        if (this.cancelRequested) return this.finishStreaming(ass);
        ass.currentTool = { tool: t.tool, argPreview: previewArgs(t.args) };
        await sleep(Math.min(900, t.ms * 6) * SLOW);
        ass.currentTool = null;
        ass.trace.push({
          tool: t.tool,
          argPreview: previewArgs(t.args),
          status: t.status,
          ms: t.ms,
        });
        ass.elapsedMs = Math.round(performance.now() - start);
        this.$nextTick(() => this.scrollToEnd());
      }

      // stream the markdown
      const md = route.md || "";
      const chunkSize = reducedMotion ? md.length : 3;
      for (let i = 0; i < md.length; i += chunkSize) {
        if (this.cancelRequested) break;
        ass.md = md.slice(0, i + chunkSize);
        ass.elapsedMs = Math.round(performance.now() - start);
        if (i % 30 === 0) this.$nextTick(() => this.scrollToEnd());
        await sleep(reducedMotion ? 0 : 6);
      }
      ass.md = md;
      ass.elapsedMs = route.elapsedMs;
      this.finishStreaming(ass);
    },

    finishStreaming(ass) {
      ass.streaming = false;
      ass.currentTool = null;
      this.isStreaming = false;
      this.$nextTick(() => this.scrollToEnd());
    },

    cancel() {
      this.cancelRequested = true;
      this.isStreaming = false;
      // mark last assistant message as stopped
      const last = this.messages[this.messages.length - 1];
      if (last && last.role === "assistant" && last.streaming) {
        last.streaming = false;
        last.currentTool = null;
        if (!last.md && (!last.trace || last.trace.length === 0)) {
          last.md = "_(stopped before any tools ran)_";
        }
      }
    },

    retryMessage(idx) {
      // remove the failed assistant turn and re-run from the prior user message
      const chat = this.activeChat;
      const prior = chat.messages[idx - 1];
      if (!prior || prior.role !== "user") return;
      chat.messages.splice(idx, 1);
      this.runAgent(chat, prior.text);
    },

    // skills
    openSkillsMenu() {
      this.showSkillsMenu = true;
      this.activeSkill = null;
      this.skillsSearch = "";
    },
    selectSkill(s) {
      this.activeSkill = s;
      this.skillParams = {};
      s.parameters.forEach(p => { this.skillParams[p.name] = ""; });
      // sensible defaults for the demo
      if (s.name === "escalation-summary") this.skillParams.customer = "Velocity Marketplace";
      if (s.name === "handoff-brief") this.skillParams.issue_id = "3";
    },
    runSkill() {
      const s = this.activeSkill;
      if (!s) return;
      const missing = s.parameters.filter(p => p.required && !String(this.skillParams[p.name] || "").trim());
      if (missing.length) { this.flash(`Missing: ${missing.map(p => p.name).join(", ")}`); return; }
      this.showSkillsMenu = false;
      // ensure we have an active chat
      const chat = this.activeChat;
      const param = Object.entries(this.skillParams).map(([k,v]) => `${k}=${v}`).join(" ");
      const pretty = `/${s.name} ${param}`;
      if (!chat.title) chat.title = `Skill — ${s.name}`;
      chat.messages.push({ id: MID++, role: "user", text: pretty });
      // Translate to a routed query that mirrors what the skill would do
      this.$nextTick(() => this.scrollToEnd());
      this.runAgent(chat, this.skillToQuery(s, this.skillParams));
      this.activeSkill = null;
    },
    skillToQuery(s, params) {
      if (s.name === "escalation-summary") {
        return `risk brief for ${params.customer}: open issues, most urgent, recommended next action`;
      }
      if (s.name === "handoff-brief") {
        return `velocity webhook handoff brief for issue ${params.issue_id}`;
      }
      return `run ${s.name} with ${JSON.stringify(params)}`;
    },

    // save as skill
    openSaveSkill() {
      const chat = this.activeChat;
      if (!chat) return;
      // Derive a draft from the actual messages: title-derived name, instructions w/ placeholders, allowed_tools = union of tool calls
      const tools = new Set();
      chat.messages.forEach(m => {
        if (m.role === "assistant" && m.trace) m.trace.forEach(t => { if (t.status !== "denied") tools.add(t.tool); });
      });
      const firstUser = chat.messages.find(m => m.role === "user")?.text || "";
      const name = this.slugify(firstUser).slice(0, 36) || "new-skill";
      const customer = pickCustomerWord(firstUser) || "the named customer";
      const instructions = firstUser
        ? firstUser.replace(new RegExp(customer, "g"), "{customer}") + `\n\nGround every claim in tool results. If the customer is not found or ambiguous, say so plainly.`
        : "";
      this.skillDraft = {
        name,
        description: `Generalised from "${chat.title || firstUser}" — see editable instructions below.`,
        instructions,
        parameters: [{ name: "customer", description: "Customer name (or partial name)", required: true }],
        allowed_tools: [...tools],
      };
      this.showSaveSkill = true;
    },
    saveSkillFromDraft() {
      const d = this.skillDraft;
      this.skills.unshift({
        name: d.name, description: d.description,
        parameters: d.parameters.filter(p => p.name.trim()),
        allowed_tools: d.allowed_tools,
        authored: true, authoredBy: this.user.name.split(" ")[0].toLowerCase(),
      });
      this.showSaveSkill = false;
      this.flash(`Skill "${d.name}" saved — it's now in the Skills menu.`);
    },
    slugify(s) {
      return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    },

    // toast
    flash(text) {
      this.toast = text;
      clearTimeout(this._toastT);
      this._toastT = setTimeout(() => { this.toast = ""; }, 3200);
    },

    // scroll
    scrollToEnd() {
      const el = this.$refs.thread;
      if (el) el.scrollTop = el.scrollHeight;
    },
  };
};
