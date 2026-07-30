// Live-view connection helpers with automatic reconnection and a visible
// connection state, so a dropped socket no longer looks like a frozen frame.
(function () {
  // A peer that dies without announcing it leaves the connection open and
  // silent: readyState stays OPEN, no error fires, and nothing arrives again.
  // Neither EventSource nor WebSocket detects this on its own, so both streams
  // are watched the same way — the server promises to send something on a
  // known cadence, and silence past a multiple of it means dead.
  //
  // The cadence is advertised by the server in its opening ping rather than
  // hard-coded here, so changing it on one side cannot silently wedge the
  // other into a permanent reconnect loop.
  var STALE_FACTOR = 2.5;

  // A cadence is the gap the server sleeps between sends, not a guarantee of
  // when the next one lands — a slow screenshot capture pushes a frame well
  // past 2.5x its 1.5s interval. The floor absorbs that; without it the fast
  // stream would tear down healthy sockets.
  var MIN_STALE_MS = 10000;

  // Used until the server says otherwise, and if its ping is unparseable.
  var DEFAULT_STALE_MS = 40000;

  var CHECK_MS = 2000;

  // Polls getLastMs() and calls onStale() once it falls further behind than
  // the threshold allows. thresholdMs may be a number or a function, so a
  // caller can keep reading a value the server revises at runtime.
  function staleWatchdog(getLastMs, onStale, thresholdMs) {
    var threshold = typeof thresholdMs === 'function'
      ? thresholdMs
      : function () { return thresholdMs; };
    var timer = setInterval(function () {
      if (Date.now() - getLastMs() > threshold()) onStale();
    }, CHECK_MS);
    return { close: function () { clearInterval(timer); } };
  }

  // Read an advertised cadence out of a ping payload, falling back when the
  // server sends nothing useful.
  function staleFrom(raw, fallback) {
    try {
      var ms = JSON.parse(raw).intervalMs;
      if (typeof ms === 'number' && ms > 0) {
        return Math.max(Math.round(ms * STALE_FACTOR), MIN_STALE_MS);
      }
    } catch (_) {}
    return fallback;
  }

  // Reconnecting screenshot socket. Calls onFrame(blob) for each frame and
  // onState('online' | 'offline' | 'gone') as the connection changes. Uses
  // exponential backoff, and stops permanently when the server closes the
  // socket normally (code 1000 — e.g. the context no longer exists).
  //
  // Text messages are keepalives, binary ones are frames.
  window.liveScreenshot = function (url, onFrame, onState) {
    var delay = 1000;
    var MAX = 15000;
    var stopped = false;
    var ws = null;
    var timer = null;
    var lastMessage = Date.now();
    var staleMs = DEFAULT_STALE_MS;

    function open() {
      if (stopped) return;
      ws = new WebSocket(url);
      ws.binaryType = 'blob';
      lastMessage = Date.now();
      ws.onopen = function () {
        delay = 1000;
        lastMessage = Date.now();
        if (onState) onState('online');
      };
      ws.onmessage = function (e) {
        lastMessage = Date.now();
        if (typeof e.data === 'string') {
          staleMs = staleFrom(e.data, staleMs);
          return;
        }
        onFrame(e.data);
      };
      ws.onerror = function () {
        if (ws) ws.close();
      };
      ws.onclose = function (e) {
        if (stopped) return;
        if (e.code === 1000) {
          // The context is gone; nothing will arrive again and the watchdog
          // must not keep resurrecting the socket.
          stopped = true;
          watchdog.close();
          if (onState) onState('gone');
          return;
        }
        if (onState) onState('offline');
        timer = setTimeout(open, delay);
        delay = Math.min(delay * 2, MAX);
      };
    }

    // Detach the old socket's handlers before replacing it, so its close does
    // not also schedule a reconnect on top of this one.
    function reopen() {
      if (stopped) return;
      if (onState) onState('offline');
      if (ws) {
        ws.onopen = ws.onmessage = ws.onerror = ws.onclose = null;
        ws.close();
      }
      if (timer) clearTimeout(timer);
      lastMessage = Date.now();
      open();
    }

    open();

    var watchdog = staleWatchdog(
      function () { return lastMessage; },
      reopen,
      function () { return staleMs; });

    return {
      close: function () {
        stopped = true;
        watchdog.close();
        if (timer) clearTimeout(timer);
        if (ws) ws.close();
      },
    };
  };

  // Retitle the tab as what the page is showing changes, in the same shape the
  // server renders in layout.html. Worth keeping current: the dashboard is
  // usually a background tab, where the title is all you can see of it.
  window.setPageTitle = function (text) {
    document.title = text ? text + ' — Clawsome' : 'Clawsome';
  };

  // Updates stream over SSE.
  //
  // onState reports 'online' / 'offline'. onReconnect (optional) fires after
  // the stream comes back, so the caller can re-sync state that changed while
  // it was down — events emitted during the gap are gone for good.
  window.liveUpdates = function (url, types, onEvent, onState, onReconnect) {
    var src = null;
    var lastMessage = Date.now();
    var everConnected = false;
    var staleMs = DEFAULT_STALE_MS;

    function handle(type, raw) {
      lastMessage = Date.now();
      if (type === 'ping') {
        staleMs = staleFrom(raw, staleMs);
        return;
      }
      var data = {};
      try {
        data = JSON.parse(raw);
      } catch (_) {}
      onEvent(type, data);
    }

    function open() {
      src = new EventSource(url);
      lastMessage = Date.now();

      src.onopen = function () {
        lastMessage = Date.now();
        if (onState) onState('online');
        if (everConnected && onReconnect) onReconnect();
        everConnected = true;
      };
      src.onerror = function () {
        if (src.readyState === EventSource.CLOSED && onState) onState('offline');
      };
      // 'ping' refreshes the liveness timer and carries the server's cadence.
      ['ping'].concat(types).forEach(function (type) {
        src.addEventListener(type, function (e) {
          handle(type, e.data);
        });
      });
    }

    function reopen() {
      if (onState) onState('offline');
      if (src) src.close();
      lastMessage = Date.now();
      open();
    }

    open();

    var watchdog = staleWatchdog(
      function () { return lastMessage; },
      reopen,
      function () { return staleMs; });

    return {
      close: function () {
        watchdog.close();
        if (src) src.close();
      },
    };
  };

  // Streaming log view, shared by the context page's mini-log and the full log
  // view. Both render the same entries the same way, and both lose whatever
  // was emitted while the stream was down — the SSE endpoint sets no event id,
  // so there is no replay to fall back on. Refetching on reconnect is cheap
  // and exact, which a client-side ring buffer would not be.
  //
  // opts: emptyEl, limit, statusEl, types (extra event names), onEvent.
  window.liveLogs = function (container, contextId, opts) {
    opts = opts || {};
    var empty = opts.emptyEl || null;

    function entry(level, message, time) {
      var div = document.createElement('div');
      div.className = 'log-entry log-' + level;
      var span = document.createElement('span');
      span.className = 'log-time';
      span.textContent = time;
      div.appendChild(span);
      // Log text is untrusted; append it as text rather than markup.
      div.appendChild(document.createTextNode(
        ' [' + level.toUpperCase() + '] ' + message));
      return div;
    }

    // Live entries are arriving now, so this matches their real timestamp to
    // within the round trip. Server-rendered ones carry their own.
    function now() {
      return new Date().toISOString().replace('T', ' ').split('.')[0];
    }

    function resync() {
      fetch('/api/contexts/' + contextId + '/logs')
        .then(function (r) { return r.json(); })
        .then(function (logs) {
          // Newest first from the API; the view reads oldest first.
          var rows = logs.slice(0, opts.limit || logs.length).reverse();
          container.innerHTML = '';
          rows.forEach(function (log) {
            container.appendChild(
              entry(log.level || 'info', log.message, log.created_at));
          });
          if (empty) {
            container.appendChild(empty);
            empty.style.display = rows.length ? 'none' : '';
          }
          container.scrollTop = container.scrollHeight;
        })
        .catch(function () {});
    }

    // Preloaded entries can overflow the container; show the newest.
    container.scrollTop = container.scrollHeight;

    return liveUpdates(
      '/sse/updates',
      ['log:new'].concat(opts.types || []),
      function (type, data) {
        if (type !== 'log:new') {
          if (opts.onEvent) opts.onEvent(type, data);
          return;
        }
        if (data.contextId !== contextId) return;
        if (empty) empty.style.display = 'none';
        container.appendChild(entry(data.level || 'info', data.message, now()));
        container.scrollTop = container.scrollHeight;
      },
      function (state) {
        if (opts.statusEl) opts.statusEl.setAttribute('data-conn', state);
      },
      resync);
  };
})();
