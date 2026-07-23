<p align="center">
  <img src="clawsome.png" alt="Clawsome" width="280">
</p>

<h3 align="center">Live browser automation dashboard powered by Playwright</h3>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12+-3776ab?logo=python&logoColor=white" alt="Python 3.12+"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.135+-009688?logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="https://playwright.dev/python/"><img src="https://img.shields.io/badge/Playwright-1.58+-2ead33?logo=playwright&logoColor=white" alt="Playwright"></a>
  <a href="https://github.com/alexanderbailey/clawsome/blob/main/LICENSE"><img src="https://img.shields.io/github/license/alexanderbailey/clawsome" alt="License"></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/badge/uv-package%20manager-de5fe9?logo=uv&logoColor=white" alt="uv"></a>
  <a href="https://hub.docker.com/"><img src="https://img.shields.io/badge/docker-ready-2496ed?logo=docker&logoColor=white" alt="Docker"></a>
</p>

<p align="center">
  <a href="#screenshots">Screenshots</a> &middot;
  <a href="#quick-start">Quick Start</a> &middot;
  <a href="#rest-api">API Reference</a> &middot;
  <a href="#example-setups">Example Setups</a> &middot;
  <a href="#playwright-test-integration">Test Integration</a> &middot;
  <a href="#docker">Docker</a>
</p>

---

Clawsome is a browser automation service you control over a REST API, from any AI agent that can make HTTP requests (OpenClaw, Claude Code, a custom script) or from your own tooling directly. It runs headless Chromium, exposes a REST API for browser control, and serves a real-time dashboard with live screenshots via WebSocket and SSE.

**Two main use cases:**

- **AI-driven browser tasks.** An agent creates a context, drives it through the API, and you watch the task happen live on the dashboard. OpenClaw and Claude Code are two examples below; anything that can make an HTTP request works the same way.
- **Playwright test monitoring.** Run your test suite normally and watch every test live on the dashboard with real-time screenshots and logs.

Runs anywhere Python and Chromium can. No particular OS or hardware assumed.

## Screenshots

<p align="center">
  <img src="docs/screenshots/summary.png" alt="Summary dashboard with three live context tiles" width="700">
</p>

<p align="center"><em>Summary view: every active context as a live tile, thumbnails streaming over WebSocket as each one navigates.</em></p>

<p align="center">
  <img src="docs/screenshots/context-detail.png" alt="Single context detail view" width="700">
</p>

<p align="center"><em>Context detail: live screenshot, status, and controls for one browser context.</em></p>

<p align="center">
  <img src="docs/screenshots/logs.png" alt="Scrolling log view for a context" width="700">
</p>

<p align="center"><em>Logs view: full timestamped history of an agent's narrated progress.</em></p>

<p align="center">
  <img src="docs/screenshots/dashboard-live.gif" alt="Live dashboard demo showing thumbnails updating in real time" width="700">
</p>

<p align="center"><em>Live in action: thumbnails refresh in real time as a context navigates, no page reload needed.</em></p>

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/alexanderbailey/clawsome.git
cd clawsome
uv sync
uv run playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
```

Defaults are fine for local use (`PORT=3000`, `HOST=0.0.0.0`).

### 3. Run the server

```bash
# Development (auto-restarts on file changes)
uv run uvicorn src.app:app --host 0.0.0.0 --port 3000 --reload

# Production
uv run uvicorn src.app:app --host 0.0.0.0 --port 3000
```

### 4. Verify

```bash
curl http://localhost:3000/health
# {"status":"ok"}
```

Open [http://localhost:3000/summary](http://localhost:3000/summary) for the live dashboard.

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Data and profiles are persisted via volumes (`./data` and `./profiles`).

## Architecture

```
                         ┌──────────────────┐
   Agent / HTTP ────────►│   REST API       │
                         │   /api/contexts  │
                         └────────┬─────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼              ▼
              ┌──────────┐ ┌──────────┐  ┌────────────┐
              │ Browser  │ │  SQLite  │  │    SSE     │
              │ Contexts │ │   DB     │  │ Broadcast  │
              └────┬─────┘ └──────────┘  └─────┬──────┘
                   │                           │
                   ▼                           ▼
              ┌──────────┐             ┌──────────────┐
              │Playwright│             │  Dashboard   │
              │ Chromium │             │  HTMX + WS   │
              └──────────┘             └──────────────┘
```

**Context lifecycle:** Create &rarr; Navigate / Execute &rarr; Screenshot &rarr; Log &rarr; Destroy

**Context types:**
| Type | Description |
| --- | --- |
| **Ephemeral** | Fresh context in the shared browser instance (default) |
| **Persistent** | Uses a profile directory with stored cookies/sessions |
| **External** | Metadata only, no browser. Screenshots pushed via API (used by the test fixture) |

## Browser Profiles

Profiles save login sessions so Clawsome can access authenticated sites without re-entering credentials.

```bash
uv run python -m src.browser.create_profile amazon
```

This opens a visible Chromium window. Log in manually, then close the browser. The session is saved to `./profiles/amazon/`.

Use it when creating a context:

```json
{ "name": "check prices", "profile": "amazon" }
```

## REST API

All endpoints are under `/api/`.

### Contexts

| Method | Endpoint | Body | Description |
| --- | --- | --- | --- |
| `POST` | `/api/contexts` | `{ name, profile?, external? }` | Create a browser context |
| `GET` | `/api/contexts` | - | List all contexts |
| `GET` | `/api/contexts/:id` | - | Get context details |
| `DELETE` | `/api/contexts/:id` | - | Destroy context and free resources |

### Browser Actions

| Method | Endpoint | Body | Description |
| --- | --- | --- | --- |
| `POST` | `/api/contexts/:id/goto` | `{ url, timeout?, waitUntil? }` | Navigate to a URL |
| `POST` | `/api/contexts/:id/exec` | `{ action, selector?, value?, script?, timeout? }` | Execute a page action |
| `GET` | `/api/contexts/:id/snapshot` | - | Get a JSON digest of the current page: URL, title, visible text, and interactive elements with selectors |

<details>
<summary>Supported exec actions</summary>

| Action | Requires | Description |
| --- | --- | --- |
| `click` | `selector` | Click an element |
| `type` | `selector`, `value` | Fill a text field |
| `select` | `selector`, `value` | Choose a dropdown option |
| `wait` | `selector` | Wait for an element to appear |
| `evaluate` | `script` | Run JavaScript in the page |
| `waitForNavigation` | - | Wait for the page URL to settle. Pass a glob in `selector` to wait for a specific URL (default `**/*`) |
| `solveTurnstile` | - | Click through a Cloudflare Turnstile checkbox if one is present, otherwise proceed |

All actions accept an optional `timeout` in milliseconds.

</details>

### Screenshots & Logs

| Method | Endpoint | Body | Description |
| --- | --- | --- | --- |
| `GET` | `/api/contexts/:id/screenshot` | - | Get current screenshot (PNG) |
| `POST` | `/api/contexts/:id/screenshot` | Raw PNG body | Upload screenshot (external contexts) |
| `GET` | `/api/contexts/:id/screenshots` | - | List saved screenshot filenames |
| `GET` | `/api/contexts/:id/screenshots/:file` | - | Get a saved screenshot |
| `GET` | `/api/contexts/:id/logs` | - | Get log entries |
| `POST` | `/api/contexts/:id/logs` | `{ level?, message }` | Append a log entry |

### Example workflow

```bash
# Create a context
curl -s -X POST http://localhost:3000/api/contexts \
  -H "Content-Type: application/json" \
  -d '{"name": "example task"}'
# → {"id": "abc123", ...}

# Navigate
curl -s -X POST http://localhost:3000/api/contexts/abc123/goto \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# See what's on the page before acting
curl -s http://localhost:3000/api/contexts/abc123/snapshot
# → {"url": "...", "title": "...", "text": "...", "elements": [{"tag": "a", "label": "More info", "selector": "a.more-info", "href": "..."}, ...]}

# Click a link
curl -s -X POST http://localhost:3000/api/contexts/abc123/exec \
  -H "Content-Type: application/json" \
  -d '{"action": "click", "selector": "a.more-info"}'

# Take a screenshot
curl -s http://localhost:3000/api/contexts/abc123/screenshot -o shot.png

# Clean up
curl -s -X DELETE http://localhost:3000/api/contexts/abc123
```

## Playwright Test Integration

Clawsome includes a Playwright test fixture (`reporter/fixture.js`) that streams live screenshots and test progress to the dashboard. Your tests run as normal; Clawsome just watches.

### Setup

Import `test` and `expect` from the fixture instead of `@playwright/test`:

```js
import { test, expect } from '../path/to/clawsome/reporter/fixture.js';

test('loads the homepage', async ({ page }) => {
  await page.goto('https://example.com');
  await expect(page).toHaveTitle(/Example/);
});
```

Every test automatically appears on the dashboard with live screenshots, captured every second by default (identical frames are skipped). Set `CLAWSOME_SCREENSHOT_INTERVAL_MS` to change the capture interval. When the test finishes, the context is destroyed and screenshots are preserved in the history.

### Custom log messages

```js
test('checkout flow', async ({ page, clawsome }) => {
  await page.goto('https://shop.example.com');
  await clawsome.log('Navigated to shop');

  await page.click('.add-to-cart');
  await clawsome.log('Added item to cart');
});
```

### Configuration

Set `CLAWSOME_URL` if the server runs on a different host:

```bash
CLAWSOME_URL=http://192.168.1.50:3000 npx playwright test
```

If Clawsome is unreachable, tests run normally with no errors or side effects.

## Dashboard

| Route | Description |
| --- | --- |
| `/summary` | Grid of active contexts with live thumbnails (auto-updates via SSE + WebSocket) |
| `/history` | Grid of stopped contexts with last screenshot, paginated |
| `/context/:id` | Live screenshot view with metadata, mini log stream, and screenshot history |
| `/logs/:id` | Full scrolling log viewer |
| `/sse/updates` | Raw SSE event stream |

**SSE events:** `context:created`, `context:destroyed`, `context:updated`, `log:new`

## Example Setups

The API is generic, but here's what you can do with it:

- **Phone → agent → screen.** Message your agent from your phone and watch the task run live on any screen with the dashboard open, whether that's a second monitor or a Raspberry Pi plugged into the TV. You see every click as it happens without touching a laptop.
- **A second pair of eyes on your coding agent.** Mid-session, ask Claude Code to "log into staging with the `staging` profile and check the new invoice page renders". It drives the browser through the API while you watch on `/summary`, instead of trusting a text summary after the fact.
- **CI test monitoring.** Point `reporter/fixture.js` at a Clawsome instance and open `/summary` during a deploy. Every Playwright test in the suite shows up as a live tile with screenshots, so a flaky test is visible while it happens instead of buried in a CI log afterward.

## AI Agent Integration

Clawsome has no dependency on any particular agent: it's a REST API, and anything that can make an HTTP request can drive it. For agents that support skills, `skill/` contains a ready-made one that teaches the full workflow (create a context, navigate, act, log progress, clean up). The same file works for OpenClaw, Claude Code, and anything else that reads the SKILL.md format:

```bash
# OpenClaw
cp -r skill/ ~/.openclaw/workspace/skills/clawsome/

# Claude Code, this project only
cp -r skill/ .claude/skills/clawsome/

# Claude Code, all projects
cp -r skill/ ~/.claude/skills/clawsome/
```

If Clawsome runs on a different host, edit `skill/SKILL.md` and replace `localhost:3000` with the actual address.

Once installed, the reliable way to invoke it is by name: say "use clawsome to check the checkout page", or type `/clawsome` in Claude Code. Agents can also pick the skill up on their own when a request clearly needs a live browser, but that matching is best effort, so name it when it matters.

The skill is a convenience, not a requirement. Any agent can be pointed at the [REST API](#rest-api) reference above and drive Clawsome directly.

## License

[MIT](LICENSE)
