// Live-view connection helpers with automatic reconnection and a visible
// connection state, so a dropped socket no longer looks like a frozen frame.
(function () {
  // Reconnecting screenshot socket. Calls onFrame(blob) for each frame and
  // onState('online' | 'offline' | 'gone') as the connection changes. Uses
  // exponential backoff, and stops permanently when the server closes the
  // socket normally (code 1000 — e.g. the context no longer exists).
  window.liveScreenshot = function (url, onFrame, onState) {
    var delay = 1000;
    var MAX = 15000;
    var stopped = false;
    var ws = null;
    var timer = null;

    function open() {
      if (stopped) return;
      ws = new WebSocket(url);
      ws.binaryType = 'blob';
      ws.onopen = function () {
        delay = 1000;
        if (onState) onState('online');
      };
      ws.onmessage = function (e) {
        onFrame(e.data);
      };
      ws.onerror = function () {
        if (ws) ws.close();
      };
      ws.onclose = function (e) {
        if (stopped) return;
        if (e.code === 1000) {
          if (onState) onState('gone');
          return;
        }
        if (onState) onState('offline');
        timer = setTimeout(open, delay);
        delay = Math.min(delay * 2, MAX);
      };
    }

    open();

    return {
      close: function () {
        stopped = true;
        if (timer) clearTimeout(timer);
        if (ws) ws.close();
      },
    };
  };

  // Updates stream over SSE.
  //
  // EventSource cannot be trusted to notice a dead server: when the process
  // goes away without a clean close, readyState stays OPEN and onerror never
  // fires, so the stream silently delivers nothing and no events arrive again.
  // The server sends a ping every 15s, so we treat "no message for STALE_MS"
  // as dead and rebuild the connection ourselves.
  //
  // onState reports 'online' / 'offline'. onReconnect (optional) fires after
  // the stream comes back, so the caller can re-sync state that changed while
  // it was down — events emitted during the gap are gone for good.
  var STALE_MS = 40000;

  window.liveUpdates = function (url, types, onEvent, onState, onReconnect) {
    var src = null;
    var lastMessage = Date.now();
    var everConnected = false;
    var stopped = false;

    function handle(type, raw) {
      lastMessage = Date.now();
      if (type === 'ping') return;
      var data = {};
      try {
        data = JSON.parse(raw);
      } catch (_) {}
      onEvent(type, data);
    }

    function open() {
      if (stopped) return;
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
      // 'ping' only refreshes the liveness timer; it carries no payload.
      ['ping'].concat(types).forEach(function (type) {
        src.addEventListener(type, function (e) {
          handle(type, e.data);
        });
      });
    }

    function reopen() {
      if (onState) onState('offline');
      if (src) {
        src.onerror = null;
        src.close();
      }
      open();
    }

    open();

    var watchdog = setInterval(function () {
      if (stopped) return;
      if (Date.now() - lastMessage > STALE_MS) reopen();
    }, 5000);

    return {
      close: function () {
        stopped = true;
        clearInterval(watchdog);
        if (src) src.close();
      },
    };
  };
})();
