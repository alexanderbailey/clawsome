# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Until 1.0.0 the API may still change between minor versions; anything breaking
will be called out here.

## [Unreleased]

## [0.1.1] — 2026-07-26

### Added

- Container images published to `ghcr.io/alexanderbailey/clawsome` on every push
  to `main` and on version tags, so Docker no longer requires cloning and
  building. `latest` moves only on tagged releases.
- A `Release` workflow that tags a commit, publishes the GitHub release from the
  matching changelog section, and builds the image for the tag — so cutting a
  release no longer needs a checkout and a local `git push`.

### Changed

- README leads with watching rather than automating, compares Clawsome against
  the tools it will be measured against, and says plainly when to use something
  else.

## [0.1.0] — 2026-07-25

First tagged release. Clawsome drives headless Chromium over a REST API and
shows the work happening live in a dashboard.

### Browser control

- REST API for the browser context lifecycle: create, navigate, act, screenshot,
  log, destroy. Contexts can be ephemeral, backed by a saved profile, or
  external (metadata only, frames pushed in by a client).
- Page actions: `click`, `type`, `select`, `wait`, `scroll`, `press`, `hover`,
  `back`, `reload`, `evaluate` and `waitForNavigation`, each with an optional
  per-call timeout.
- `GET /api/contexts/:id/snapshot` returns a JSON digest of the page — URL,
  title, visible text, and interactive elements with selectors — so a caller can
  read the page before acting on it rather than guessing selectors.
- Tabs opened by the page itself (`target="_blank"`, `window.open`) are adopted
  automatically, so a click that spawns a tab doesn't leave the context pointing
  at the old page.
- Configurable viewport per context, defaulting to 1280×720.
- Browser profiles keep logged-in sessions on disk. A profile can only back one
  live context at a time; a second attempt gets a `409` naming the holder rather
  than a Chromium lock error.
- Contexts idle beyond `CLAWSOME_CONTEXT_TTL` (default 30 minutes) are destroyed
  automatically, and the expiry is written to the context's log.

### Dashboard

- Summary view of every live context as a tile, thumbnails streaming over
  WebSocket, reconciled in place as contexts come and go.
- Per-context view with a live screenshot, status, recent log entries and the
  saved frame history; a paginated history view for stopped contexts.
- Live log stream over SSE, on both the context page and the full log view.
- Connections recover on their own: WebSockets reconnect with backoff, and the
  SSE stream is rebuilt when it goes silent — an `EventSource` cannot detect a
  server that dies without closing cleanly.

### Screenshots

- The server records history itself — a frame after every navigation and action,
  plus a periodic capture — so the history is complete whether or not anyone had
  the dashboard open.
- Identical frames are skipped by hash, and the minimum interval between saved
  frames is configurable.
- Retention keeps the most recent `CLAWSOME_SCREENSHOT_LIMIT` frames per context
  (default 500) and deletes frames older than `CLAWSOME_SCREENSHOT_MAX_AGE_DAYS`
  (default 7).

### Integrations

- Playwright fixture (`reporter/fixture.js`): every test appears on the
  dashboard with live screenshots and its own log stream.
- MCP server (`src/mcp_server.py`) exposing the API as agent tools, with
  screenshots returned as images the agent can look at.
- Skill definition for agents that read one.

### Running it

- Docker image and compose file, honouring `PORT` and `HOST`, with `./data` and
  `./profiles` persisted as volumes.
- Optional bearer-token authentication on the API via `CLAWSOME_TOKEN`; `/health`
  and the dashboard stay open.
- Playwright failures come back as structured `4xx` responses — `timeout`,
  `navigation` or `error`, with the page's URL — instead of bare `500`s.
- End-to-end test suite driving real servers against real browsers, run in CI on
  every push.

[Unreleased]: https://github.com/alexanderbailey/clawsome/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/alexanderbailey/clawsome/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/alexanderbailey/clawsome/releases/tag/v0.1.0
