# Clawsome — Product Review

*A candid review of Clawsome as a product: who it's for, what already exists, where the gaps are, and how to promote it. Code quality is only discussed where it affects the user or agent experience.*

---

## TL;DR

Clawsome's real product is **not** browser automation — that's a commodity. The real product is the **glass cockpit**: a human watching, live, while an AI agent drives a browser, with a screenshot trail and narrated log left behind as a receipt. That's a genuine need (agent trust and observability), it's underserved in the self-hosted space, and it should be the headline of every pitch.

The three things standing between Clawsome and being genuinely promotable:

1. **Agents can't "see" the page.** There's no endpoint to read page content or find selectors, so an agent driving the API is flying blind. This is the single biggest functional gap.
2. **No authentication** on an API that can execute arbitrary JavaScript and reuse saved login sessions. Fine on localhost, disqualifying for every other advertised setup (Pi on the TV, CI, remote agents).
3. **No MCP server.** In 2026, "how do I connect my agent to a browser" has a default answer, and it's MCP. A curl-based skill works, but MCP is where adoption is.

None of these are large builds. With them done, Clawsome has a clear, defensible niche: *the self-hosted, watchable browser for AI agents.*

---

## 1. What is the point? (Positioning)

### The honest competitive landscape

People *will* ask "why not just use X?" — so answer it head-on:

| Tool | What it is | What it has that Clawsome doesn't | What Clawsome has that it doesn't |
|---|---|---|---|
| **Playwright MCP** (Microsoft, official) | MCP server giving agents structured browser control | Accessibility-tree snapshots (the agent can *read* the page), rich action set, zero setup with Claude Code | **No dashboard, no spectators.** The human sees nothing. No REST API for non-MCP callers. No persistence/history. |
| **Browserbase / Steel / Hyperbrowser / Anchor** | Cloud (Steel also OSS) "browsers for agents" with live session viewers | Session replays, proxies, scale, polished viewers | **Self-hosted, no account, no per-session pricing**, one `docker compose up`, your profiles stay on your disk |
| **Browserless** | Self-hosted headless browser service | Scale, mature REST/WS APIs | A dashboard meant for *watching agents*, agent-shaped skill, log narration |
| **Playwright UI mode / trace viewer** | Test debugging | Deep post-hoc traces | **Live, remote, multi-suite**: a wall of running tests viewable from any device, not a local dev tool |
| **browser-use / Stagehand** | Agent-side browsing libraries | The agent loop itself | Clawsome is agent-agnostic infrastructure; these could even be *clients* of it |

### The niche that's actually open

Every cell in that table points at the same gap: **nothing self-hosted lets a human watch an agent browse, live, with history.** Playwright MCP is invisible; cloud viewers are SaaS. Clawsome's differentiators, in order of defensibility:

1. **The spectator experience.** Live thumbnails of *every* concurrent context on one page, from any device on the network. This is the demo, the gif, the pitch.
2. **The receipt.** Screenshot history + narrated logs = an audit trail of what the agent actually did. "Trust but verify" is the emotional hook — people are nervous about agents acting on real websites, especially logged-in ones.
3. **Self-hosted simplicity.** One Python service, SQLite, no accounts. Login profiles never leave your machine — a real answer to "I'm not giving a SaaS my Amazon cookies."
4. **The Playwright test wall** is a sleeper feature no one else has in this form: point a CI suite at Clawsome and get a live wall of running tests. Consider promoting it harder — it may be the easiest wedge into teams (devs trust test tooling before they trust agent tooling).

### Suggested pitch (README first line)

Current framing — "a browser automation service you control over a REST API" — leads with the commodity. Suggested reframe:

> **Watch your AI agent browse the web.** Clawsome gives agents a real browser over a plain REST API, and gives *you* a live dashboard: every click, every page, every screenshot, as it happens — self-hosted, with a full history left behind.

The tagline "Live browser automation dashboard" is close but buries the agent angle, which is the timely part.

---

## 2. Critical gaps (blockers for promotion)

### 2.1 Agents are flying blind — no way to read the page

The API can click, type, and select by CSS selector — but offers **no way to discover what's on the page**. An agent's options today are:

- `evaluate` with hand-rolled JS (`document.body.innerText`, DOM-walking scripts) — works, but every agent reinvents it badly, and nothing in the skill suggests it;
- download the screenshot PNG and use vision — slow, token-expensive, and doesn't yield selectors.

This is *the* reason Playwright MCP wins head-to-head today: its accessibility-tree snapshot gives the agent labeled, ref-addressable elements. Without an equivalent, real-world Clawsome sessions will loop on "selector not found."

**Recommendation (highest-impact single feature):** add `GET /api/contexts/:id/snapshot` returning a compact, agent-friendly page digest — URL, title, visible text, and interactive elements (links, buttons, inputs) each with a usable selector. Even a simple implementation (roles + names + generated selectors) transforms the agent experience. Then teach it in SKILL.md: *"After every navigation, take a snapshot to see what's on the page."*

Cheap adjacent wins: also return the current `url` and `title` from every `goto`/`exec` response so the agent gets feedback without an extra round trip.

### 2.2 No authentication

The API is unauthenticated and the docs default to `HOST=0.0.0.0`. Anyone who can reach the port can run arbitrary JavaScript in the browser (`evaluate`), and — much worse — **open a context with any saved login profile** ("amazon", "github", the skill even suggests "banking") and act as you. The advertised setups (Raspberry Pi on the TV, CI runners, phone → agent → screen) all put this on a LAN or beyond.

**Recommendation:** a single optional `CLAWSOME_TOKEN` env var checked as a bearer token on `/api/*` (the fixture and skill pass it from the environment). A read-only-dashboard vs. control split would be a bonus. Also add a loud "Security" section to the README — its absence will be the first thing a Hacker News commenter finds, and being upfront about the localhost trust model costs nothing.

Related hardening: `GET /api/contexts/:id/screenshots/{filename}` should reject path separators in `filename` (an encoded `%2F..%2F` can escape the context's directory; the `.png` suffix check is not enough).

### 2.3 No MCP server

The curl-based skill is genuinely nice (portable, agent-agnostic, no dependencies) — keep it. But MCP is the standard integration path now, and its absence means Clawsome loses the default comparison with Playwright MCP before the dashboard is ever seen.

**Recommendation:** ship a thin MCP server (stdio, ~150 lines with the Python `mcp` package) exposing `create_context`, `goto`, `act`, `snapshot`, `screenshot`, `log`, `destroy` as tools that call the REST API. Clawsome's story then becomes strictly better than Playwright MCP's: *same agent ergonomics, plus a dashboard, history, and any-HTTP-client access.* One `claude mcp add` line in the README.

---

## 3. Significant issues (fix before or shortly after promoting)

### 3.1 Failures return unhelpful 500s to the agent

Only `ValueError` is caught in the API routes. The most common real-world failure — a Playwright `TimeoutError` from a bad selector or slow page — propagates as a bare **500 Internal Server Error** with no body. The agent gets nothing to reason about, so it can't distinguish "selector wrong" from "server broken." For a product whose primary users are LLMs, structured errors *are* the UX: catch Playwright errors and return 4xx JSON like `{"error": "timeout", "message": "waiting for selector \".add-to-cart\"", "url": "...", "suggestion": "take a snapshot to see available elements"}`.

### 3.2 Screenshot history only exists if someone was watching

Disk saves happen inside `take_screenshot`, which only runs when a dashboard WebSocket is connected or the GET endpoint is polled. Run an agent task with no dashboard open and the "audit trail" is empty — which quietly breaks the receipt/history pitch (item #2 in the positioning). **Recommendation:** a server-side capture loop (e.g. every 2–5 s per live context, and one forced capture on every `goto`/`exec`) so history exists unconditionally. Capturing on-action also makes the history read like a story: one frame per step.

### 3.3 Finished work is invisible

`/summary` only lists *alive* contexts. Once a context is destroyed, its screenshots and logs are preserved but **unreachable** — there's no page listing past contexts, so you'd need to have saved the UUID. The "come back and see what the agent did" story doesn't survive the agent finishing. **Recommendation:** a history section (or a "Recent" strip on `/summary`) listing stopped contexts from SQLite with name, duration, last screenshot, and links to logs/screenshots. The data is already all there.

### 3.4 Contexts leak

If an agent crashes or forgets `DELETE`, its context lives until server restart — each one a Chromium page. A idle-TTL reaper (e.g. destroy after 30 min without an API call, configurable) plus `created_at`/`last_activity` in the meta would keep long-running instances healthy.

### 3.5 Same profile twice = crash

Two contexts on the same profile means two `launch_persistent_context` calls on one user-data dir — Chromium's profile lock makes the second fail with an opaque error. Return a clear 409 ("profile 'amazon' is in use by context X") instead.

### 3.6 The action vocabulary is thin

Missing verbs agents reach for constantly: **scroll** (essential — screenshots only show the top 720px of every page), `press` (Enter to submit a search is the canonical case), `hover`, `back`, `reload`, `screenshot region`. Also, anything opening in a new tab (`target="_blank"`) is silently lost since only one page per context is tracked — at minimum, auto-adopt new pages as the active page.

### 3.7 `solveTurnstile` + stealth flags are a promotion liability

A README bullet that says "clicks through Cloudflare challenges," combined with `navigator.webdriver` spoofing and `AutomationControlled` disabling, reads as *bot-detection evasion* — a bad look for a tool you want to promote broadly, an invitation for the wrong crowd, and (against real Turnstile) mostly ineffective anyway, which means it also over-promises. Recommendation: keep the capability if you want it, but drop it from the marketing surface and frame docs around *your own / authorized sites* (staging, internal tools, sites you have accounts on). The legitimate use cases don't need it.

---

## 4. Smaller UX gaps and polish

- **Skill hardcodes `localhost:3000`** and asks users to hand-edit SKILL.md. Have the skill read `CLAWSOME_URL` from the environment, falling back to localhost — same convention the fixture already uses.
- **Live view doesn't reconnect.** If the server restarts or the WS drops, the image silently freezes — the worst failure mode for a monitoring tool (a stale frame looks like a live one). Add reconnect-with-backoff and a visible "disconnected" state. Same for the SSE-driven summary.
- **Context page's mini-log starts empty** ("Waiting for log entries...") — it only shows *new* SSE entries, so arriving mid-task shows nothing even though history exists one click away. Preload the last N logs into it.
- **Duplicate SSE connections** on the context page: the `hx-ext="sse"` attribute opens one EventSource and the inline script opens a second; the htmx one does nothing (no `sse-swap`). Harmless but wasteful — drop the attribute.
- **No favicon / page title polish** on the dashboard; small, but this is a product whose whole point is being looked at.
- **Fixed 1280×720 viewport**, not configurable per context — fine as a default, but mobile-viewport checks are a natural agent task; accept `viewport` in the create body.
- **Screenshot history is unbounded** — long-running instances will accumulate PNGs forever. A per-context cap or retention window (env-configurable) avoids the "why is my disk full" issue.
- **`.env.example` is only PORT/HOST** — as config grows (token, retention, capture interval), keep it the single documented source of truth.

## 5. Trust signals for promotion

These matter disproportionately when you ask strangers to run your code against their logged-in sessions:

- **No tests and no CI badge.** Ironic for a tool that *monitors tests*. Even a small pytest suite (API happy paths against a local page) plus a GitHub Actions badge changes the first impression.
- **No releases / tags / changelog.** Cut a `v0.1.0`; version the API implicitly with it.
- **No published Docker image.** `docker compose up --build` is good; `docker run ghcr.io/alexanderbailey/clawsome` is better — pushing to GHCR from Actions is ~20 lines and collapses time-to-demo to one command.
- **The README is genuinely good** — screenshots, gif, architecture diagram, honest tone. Two additions would make it complete: a short **"Why not Playwright MCP / Browserbase?"** section (own the comparison before commenters do) and the **Security** section from §2.2.
- **A 60–90 second video/gif of an *agent* run** — phone message → agent narrating in logs → thumbnails moving → final screenshot — would outperform the current dashboard-only gif. The agent story is the shareable one.

---

## 6. Example agent prompts

Prompts that make the best use of Clawsome, assuming the skill is installed (or the README API section is in context). Patterns that matter: **name the context after the task** (it's the tile's caption), **narrate via logs** (the dashboard is only as interesting as what's logged), **screenshot after each meaningful step** (builds the visual story), and **always destroy the context**.

### Everyday tasks

> Use clawsome to check whether the Steam Deck OLED is in stock on currys.co.uk and what it costs. Log each step so I can follow along on the dashboard, and take a screenshot of the product page before you finish.

> Use clawsome with the `amazon` profile to open my orders page and tell me the delivery status of anything arriving this week. Screenshot the orders list. Don't buy anything or change any settings.

### The "second pair of eyes" dev workflow

> Use clawsome to smoke-test the staging deploy: log in with the `staging` profile, open /invoices/new, fill the form with test data, submit, and confirm the success page shows an invoice number. Log every step, screenshot after each page transition, and if anything looks broken, stop and show me the screenshot instead of pushing through.

> Use clawsome to open http://localhost:5173 and check the new pricing page: screenshot it, confirm all three tier cards render with prices, and click each "Choose plan" button to verify it routes to checkout. Narrate what you see in the logs.

### Parallel work (shows off the summary grid)

> Use clawsome to compare Hetzner, DigitalOcean, and Vultr pricing for a 4 vCPU / 8 GB VPS. Use a separate context per provider, named after the provider, so I can watch all three side by side on the dashboard. Log the price you find in each before closing it, then give me a comparison table.

### Visual checks (uses screenshots as evidence)

> Use clawsome to open our marketing site and screenshot the homepage, /pricing, and /docs. Download each screenshot and look at it — tell me about anything visually broken: overlapping text, missing images, layout overflow.

### Long-form research

> Use clawsome to find the top three highest-rated cordless drills on Screwfix under £100. Read each product page, log the name, price, and rating as you go, screenshot each one, and finish with a recommendation. Leave the screenshots in the history so I can review your evidence.

### Worth adding to SKILL.md itself

Two techniques agents won't discover alone and that dramatically improve success today (pre-snapshot-endpoint):

- *"To read a page, use `evaluate` with `document.body.innerText` (content) or a script that lists links/buttons/inputs with their selectors (before clicking anything on an unfamiliar page)."*
- *"To verify visually, download the screenshot to a file and read it."*

---

## 7. Suggested priority order

| # | Item | Why | Effort |
|---|---|---|---|
| 1 | Page snapshot endpoint (§2.1) + teach it in SKILL.md | Agents currently can't see; biggest capability jump | Medium |
| 2 | Bearer-token auth + README security section (§2.2) | Disqualifying for every non-localhost setup | Small |
| 3 | Structured 4xx errors for Playwright failures (§3.1) | Errors are the agent UX | Small |
| 4 | Server-side screenshot capture (§3.2) + history page (§3.3) | Makes the "receipt" pitch actually true | Medium |
| 5 | MCP server wrapping the REST API (§2.3) | Meets agents where they are; neutralizes the Playwright MCP comparison | Medium |
| 6 | Scroll/press/back actions, new-tab adoption (§3.6) | Closes the most common task failures | Small–Medium |
| 7 | Context TTL, profile-lock 409, WS reconnect, mini-log preload | Robustness for real use | Small each |
| 8 | GHCR image, v0.1.0 release, CI badge, agent-run demo video | Trust and time-to-demo for promotion | Small |

**Bottom line:** the concept is sound and the niche — self-hosted, human-watchable browsing for agents — is real and open. The dashboard, the fixture, and the README are already ahead of most hobby projects. What's missing is the agent-side half of the loop (seeing the page, useful errors, MCP) and the safety story (auth). Close those and this is a tool people will actually adopt — and one with an obvious, honest answer to "why does this exist?"
