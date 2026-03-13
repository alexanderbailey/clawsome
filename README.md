# Clawsome

Playwright browser automation service for [OpenClaw](https://openclaw.ai). Runs headless Chromium on a Raspberry Pi 5, exposes a REST API for browser control, and serves a live dashboard.

Two main use cases:

- **OpenClaw integration** — AI-driven browser tasks triggered via Telegram, executed by Clawsome, streamed to the dashboard
- **Playwright Test monitoring** — run your test suite normally and watch every test live on the dashboard with real-time screenshots and logs

## Quick Start

### 1. Clone and install

```bash
git clone <repo-url> && cd clawsome
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

The server launches Playwright Chromium, initializes SQLite, and listens on port 3000.

Verify it's running:

```bash
curl http://localhost:3000/health
# {"status":"ok"}
```

### 4. Open the dashboard

Go to [http://localhost:3000/summary](http://localhost:3000/summary) in a browser. This is the live grid of all active browser contexts, updated in real-time via SSE.

## Docker

For deployment (especially on a Pi):

```bash
cp .env.example .env
docker compose up --build
```

Data and profiles are persisted via volumes (`./data` and `./profiles`).

## Setting Up Browser Profiles

Profiles save login sessions (cookies, localStorage) so Clawsome can access authenticated sites without re-entering credentials.

```bash
uv run python -m src.browser.create_profile amazon
```

This opens a visible Chromium window. Log in to the site manually, then close the browser. The session is saved to `./profiles/amazon/`.

When creating a context through the API, pass the profile name to reuse the session:

```json
{"name": "check prices", "profile": "amazon"}
```

## Connecting to OpenClaw

Clawsome integrates with OpenClaw as a skill. OpenClaw discovers the skill definition and uses `curl` to call the REST API.

### Install the skill

Copy (or symlink) the `skill/` directory into your OpenClaw skills workspace:

```bash
cp -r skill/ ~/.openclaw/workspace/skills/clawsome/
# or
ln -s "$(pwd)/skill" ~/.openclaw/workspace/skills/clawsome
```

OpenClaw will detect the skill on its next reload. You can now issue browser automation commands through Telegram, and OpenClaw will call the Clawsome API to carry them out.

### How it works

1. You send a message to OpenClaw via Telegram (e.g. "check the price of X on Amazon")
2. OpenClaw reads `skill/SKILL.md` and uses `curl` to call Clawsome's REST API
3. Clawsome creates a browser context, navigates, executes actions, and logs progress
4. You can watch it live on the dashboard at `/summary` or `/context/:id`
5. OpenClaw destroys the context when the task is done

### If Clawsome runs on a different host

The skill defaults to `http://localhost:3000`. If Clawsome runs on a different machine (e.g. your Pi), edit `skill/SKILL.md` and replace `localhost:3000` with the actual address.

## REST API

All endpoints are under `/api/`.

| Method | Endpoint | Body | Description |
|--------|----------|------|-------------|
| `POST` | `/api/contexts` | `{name, profile?, external?}` | Create a browser context |
| `GET` | `/api/contexts` | | List all contexts |
| `GET` | `/api/contexts/:id` | | Get context details |
| `DELETE` | `/api/contexts/:id` | | Destroy context and free resources |
| `POST` | `/api/contexts/:id/goto` | `{url}` | Navigate to a URL |
| `POST` | `/api/contexts/:id/exec` | `{action, selector?, value?, script?}` | Execute a page action |
| `GET` | `/api/contexts/:id/screenshot` | | Returns PNG image |
| `POST` | `/api/contexts/:id/screenshot` | PNG body | Upload screenshot (external contexts) |
| `GET` | `/api/contexts/:id/logs` | | Get log entries |
| `POST` | `/api/contexts/:id/logs` | `{level?, message}` | Append a log entry |

### Example: full workflow

```bash
# Create a context
curl -s -X POST http://localhost:3000/api/contexts \
  -H "Content-Type: application/json" \
  -d '{"name": "example task"}'
# Returns: {"id": "abc123", ...}

# Navigate
curl -s -X POST http://localhost:3000/api/contexts/abc123/goto \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# Click a link
curl -s -X POST http://localhost:3000/api/contexts/abc123/exec \
  -H "Content-Type: application/json" \
  -d '{"action": "click", "selector": "a.more-info"}'

# Take a screenshot
curl -s http://localhost:3000/api/contexts/abc123/screenshot --output shot.png

# Log progress
curl -s -X POST http://localhost:3000/api/contexts/abc123/logs \
  -H "Content-Type: application/json" \
  -d '{"level": "info", "message": "Clicked the link, page loaded"}'

# Clean up
curl -s -X DELETE http://localhost:3000/api/contexts/abc123
```

### Exec actions

| Action | Requires | Description |
|--------|----------|-------------|
| `click` | `selector` | Click an element |
| `type` | `selector`, `value` | Fill a text field |
| `select` | `selector`, `value` | Choose a dropdown option |
| `wait` | `selector` | Wait for an element to appear |
| `evaluate` | `script` | Run JavaScript in the page |

## Playwright Test Integration

Clawsome includes a Playwright fixture (`reporter/fixture.js`) that streams live screenshots and test progress to the dashboard. Your tests run normally — Clawsome just displays them.

### Setup

In your test project, import `test` and `expect` from the fixture instead of `@playwright/test`:

```js
// tests/example.spec.js
import { test, expect } from '../path/to/clawsome/reporter/fixture.js';

test('loads the homepage', async ({ page }) => {
  await page.goto('https://example.com');
  await expect(page).toHaveTitle(/Example/);
});
```

Every test automatically appears on the Clawsome dashboard with live screenshots updating every 1.5 seconds. When the test finishes, the result is logged and the card disappears.

### Optional: custom log messages

Destructure `clawsome` to log custom messages that appear on the dashboard:

```js
test('checkout flow', async ({ page, clawsome }) => {
  await page.goto('https://shop.example.com');
  await clawsome.log('Navigated to shop');

  await page.click('.add-to-cart');
  await clawsome.log('Added item to cart');
});
```

### Configuration

Set `CLAWSOME_URL` if Clawsome runs on a different host (default: `http://localhost:3000`):

```bash
CLAWSOME_URL=http://192.168.1.50:3000 npx playwright test
```

If Clawsome is unreachable, tests run normally with no errors or side effects.

## Dashboard Pages

| Route | Description |
|-------|-------------|
| `/summary` | Grid of active contexts with thumbnails (auto-updates via SSE) |
| `/context/:id` | Live screenshot view with metadata and mini log stream |
| `/logs/:id` | Full scrolling log viewer |
| `/sse/updates` | Raw SSE stream (`context:created`, `context:destroyed`, `context:updated`, `log:new`) |

## License

MIT
