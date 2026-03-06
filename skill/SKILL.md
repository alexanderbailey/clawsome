---
name: clawsome
description: Control Playwright browser sessions on your Pi via the Clawsome automation service
user-invocable: true
metadata: {"openclaw":{"os":["linux","darwin"],"requires":{"bins":["curl"]}}}
---

# Clawsome — Browser Automation

You control a Playwright browser automation service. The service runs at `http://localhost:3000` (adjust if different).

Use `curl` via bash to interact with the API. Always parse JSON responses to extract IDs and results.

## Workflow

1. **Create a context** for each task (one browser tab per task)
2. **Navigate** to the target URL
3. **Execute actions** (click, type, etc.) to accomplish the task
4. **Log progress** so the user can follow along on the dashboard
5. **Destroy the context** when the task is done

## API Reference

### Create a browser context

```bash
curl -s -X POST http://localhost:3000/api/contexts \
  -H "Content-Type: application/json" \
  -d '{"name": "TASK_DESCRIPTION", "profile": "PROFILE_NAME_OR_NULL", "visible": false}'
```

- `name`: a short description of the task
- `profile`: use a saved login profile (e.g. "amazon", "github") or omit for no profile
- `visible`: set `true` if the user wants to watch the session on their TV

Returns: `{"id": "...", "name": "...", ...}`

### Navigate to a URL

```bash
curl -s -X POST http://localhost:3000/api/contexts/CONTEXT_ID/goto \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

### Execute actions on the page

```bash
curl -s -X POST http://localhost:3000/api/contexts/CONTEXT_ID/exec \
  -H "Content-Type: application/json" \
  -d '{"action": "ACTION", "selector": "CSS_SELECTOR", "value": "TEXT"}'
```

Available actions:
- `click` — click an element. Requires `selector`.
- `type` — fill a text field. Requires `selector` and `value`.
- `select` — select a dropdown option. Requires `selector` and `value`.
- `wait` — wait for an element to appear. Requires `selector`.
- `evaluate` — run JavaScript in the page. Use `script` instead of `selector`.

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
- Use profiles for sites that require login (amazon, github, banking, etc.).
- Set `visible: true` when the user explicitly wants to watch the session.
- Log each significant step so the dashboard stays informative.
- Handle errors gracefully — if a selector isn't found, try alternatives or report the issue.
- Destroy contexts when done, even if the task fails.
- The dashboard is viewable at `http://localhost:3000/summary`.
