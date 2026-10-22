/* 状态与桥接：唯一知道 pywebview 的地方。其它模块只读 Mascot.store。 */
(function () {
  const M = (window.Mascot = window.Mascot || {});

  M.store = {
    snapshot: null,
    messages: [],
    sending: false,
    streaming: { active: false, text: '' },
    draftKey: 'mascot.draft',
    pollMs: 200,
  };

  M.hasBridge = function () {
    return !!(window.pywebview && window.pywebview.api);
  };

  M.api = {
    snapshot: function () { return M.hasBridge() ? window.pywebview.api.snapshot() : null; },
    send: function (text) { return M.hasBridge() ? window.pywebview.api.send(text) : Promise.resolve(null); },
    stop: function () { return M.hasBridge() ? (window.pywebview.api.stop ? window.pywebview.api.stop() : Promise.resolve(null)) : Promise.resolve(null); },
    toBall: function () { return M.hasBridge() ? window.pywebview.api.to_ball() : Promise.resolve(null); },
    toPanel: function () { return M.hasBridge() ? window.pywebview.api.to_panel() : Promise.resolve(null); },
  };

  /* 轮询快照：M2 定下的单向通道（Python 从不反调 JS）。 */
  M.startPolling = function (onSnapshot) {
    let stopped = false;
    let timer = null;
    async function tick() {
      if (stopped) return;
      try {
        const snap = await M.api.snapshot();
        if (snap) onSnapshot(snap);
      } catch (err) {
        /* 启动早期 api 还没注入：静默重试 */
      }
      timer = setTimeout(tick, M.store.pollMs);
    }
    tick();
    return function stop() {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  };
})();
