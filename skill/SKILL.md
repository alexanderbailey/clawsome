---
name: clawsome
description: Drive a real browser through the Clawsome automation service, with live progress on the Clawsome dashboard. Use when the user names Clawsome, or asks to browse, check, or screenshot a live website in a watchable session. Not needed for Playwright test runs, which the Clawsome reporter fixture streams to the dashboard on its own.
user-invocable: true
metadata: {"openclaw":{"requires":{"bins":["curl"]}}}
---

# Clawsome Browser Automation

You control a Playwright browser automation service. The service runs at `http://localhost:3000` (adjust if different).

Interact with the API over HTTP. The examples below use `curl` via bash, but any HTTP client works. Always parse JSON responses to extract IDs and results.

### Authentication

If the instance is configured with a token (the `CLAWSOME_TOKEN` environment variable is set on the server), every `/api/*` request must include an `Authorization: Bearer $CLAWSOME_TOKEN` header. Add `-H "Authorization: Bearer $CLAWSOME_TOKEN"` to each `curl` below when `$CLAWSOME_TOKEN` is set; requests without it get `401`. When no token is configured, omit the header.

## Workflow

1. **Create a context** for each task (one browser tab per task)
2. **Navigate** to the target URL
3. **Take a snapshot** to see what's on the page and find selectors before acting
4. **Execute actions** (click, type, etc.) to accomplish the task
5. **Log progress** so the user can follow along on the dashboard
6. **Destroy the context** when the task is done

## API Reference

### Create a browser context

```bash
curl -s -X POST http://localhost:3000/api/contexts \
  -H "Content-Type: application/json" \
  -d '{"name": "TASK_DESCRIPTION", "profile": "PROFILE_NAME_OR_NULL"}'
```

- `name`: a short description of the task
- `profile`: use a saved login profile (e.g. "amazon", "github") or omit for no profile

Returns: `{"id": "...", "name": "...", ...}`

### Navigate to a URL

```bash
curl -s -X POST http://localhost:3000/api/contexts/CONTEXT_ID/goto \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

### Read the page before acting

```bash
curl -s http://localhost:3000/api/contexts/CONTEXT_ID/snapshot
```

Returns the current `url` and `title`, the visible text content, and a list of interactive elements (links, buttons, inputs, selects) each with a `label` and a usable `selector`. Take a snapshot after every navigation instead of guessing selectors blind — it's cheaper than a failed action and a retry.

### Execute actions on the page

```bash
curl -s -X POST http://localhost:3000/api/contexts/CONTEXT_ID/exec \
  -H "Content-Type: application/json" \
  -d '{"action": "ACTION", "selector": "CSS_SELECTOR", "value": "TEXT"}'
```

Available actions:
- `click`: click an element. Requires `selector`.
- `type`: fill a text field. Requires `selector` and `value`.
- `select`: select a dropdown option. Requires `selector` and `value`.
- `wait`: wait for an element to appear. Requires `selector`.
- `evaluate`: run JavaScript in the page. Use `script` instead of `selector`.
- `waitForNavigation`: wait for the page URL to settle after a click or form submit. Pass a URL glob in `selector` to wait for a specific destination.
- `solveTurnstile`: click through a Cloudflare Turnstile checkbox if the page shows one. Returns `{"status": "no_challenge"}` when there is nothing to solve.

All actions accept an optional `timeout` in milliseconds.

Every `goto` and `exec` response also includes the page's current `url` and `title`, so you can see where an action landed without a separate request. If an action fails in the browser (timeout, missing selector, navigation error), the response is a `400` with `{"error", "message", "url"}` instead.

### Take a screenshot

```bash
curl -s http://localhost:3000/api/contexts/CONTEXT_ID/screenshot --output screenshot.png
```

### Log progress

```bash
curl -s -X POST http://localhost:3000/api/contexts/CONTEXT_ID/logs \
  -H "Content-Type: application/json" \
  -d '{"level": "info", "message": "Completed step 1: logged in"}'
```

Log important steps so the user can follow progress on the dashboard. Levels: `info`, `warn`, `error`.

### List active contexts

```bash
curl -s http://localhost:3000/api/contexts
```

### Get logs for a context

```bash
curl -s http://localhost:3000/api/contexts/CONTEXT_ID/logs
```

### Destroy a context

```bash
curl -s -X DELETE http://localhost:3000/api/contexts/CONTEXT_ID
```

Always destroy contexts when tasks are complete to free resources.

## Guidelines

- Always create a context before performing any browser actions.
- Take a snapshot after navigating to an unfamiliar page instead of guessing selectors.
- Use profiles for sites that require login (amazon, github, banking, etc.).
- Log each significant step so the dashboard stays informative.
- Handle errors gracefully. If a selector isn't found, try alternatives or report the issue.
- Destroy contexts when done, even if the task fails.
- The dashboard is viewable at `http://localhost:3000/summary`.
