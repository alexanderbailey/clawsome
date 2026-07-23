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

  // Updates stream over SSE. The native EventSource reconnects on its own; we
  // surface the connection state via onState and hand parsed events for the
  // requested types to onEvent(type, data).
  window.liveUpdates = function (url, types, onEvent, onState) {
    var src = new EventSource(url);
    src.onopen = function () {
      if (onState) onState('online');
    };
    src.onerror = function () {
      if (src.readyState !== EventSource.OPEN && onState) onState('offline');
    };
    types.forEach(function (type) {
      src.addEventListener(type, function (e) {
        var data = {};
        try {
          data = JSON.parse(e.data);
        } catch (_) {}
        onEvent(type, data);
      });
    });
    return src;
  };
})();
