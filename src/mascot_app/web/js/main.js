/* 启动：桥接就绪后开始轮询快照，把各个模块接起来。 */
(function () {
  const M = (window.Mascot = window.Mascot || {});
  const $ = function (id) { return document.getElementById(id); };

  let setSending = function (flag) { M.store.sending = !!flag; };

  function apply(snap) {
    M.store.snapshot = snap;
    M.paintShell(snap);
    M.renderMessages(snap.messages || []);
    setSending(!!snap.sending);
  }

  function boot() {
    if (M.booted) return;
    M.booted = true;

    setSending = M.initComposer(function (text) {
      M.store.sending = true;
      setSending(true);
      M.api.send(text);
      /* 本地先回显，避免等待后端时输入区“没反应” */
      const echo = M.store.messages.concat([{ role: 'user', text: text, ts: Date.now() / 1000, id: 'local-' + Date.now(), pending: true }]);
      M.renderMessages(echo);
    });
    M.store.messages = [];

    $('toBall').addEventListener('click', function () { M.api.toBall(); });
    M.mountClock($('avatar'), function () { M.api.toBall(); });

    M.startPolling(apply);
  }

  if (M.hasBridge()) boot();
  window.addEventListener('pywebviewready', boot);
  setTimeout(function () { if (!M.booted) boot(); }, 1500);
})();
