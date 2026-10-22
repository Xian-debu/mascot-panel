/* 输入区：1-4 行自适应、草稿持久化、IME 保护、Enter 发送 / Shift+Enter 换行。 */
(function () {
  const M = (window.Mascot = window.Mascot || {});
  const $ = function (id) { return document.getElementById(id); };
  const LINE = 20;
  let composing = false;

  function autosize() {
    const el = $('input');
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, LINE * 4 + 14) + 'px';
  }

  M.initComposer = function (onSend, onStop) {
    const input = $('input');
    const send = $('send');

    try { input.value = localStorage.getItem(M.store.draftKey) || ''; } catch (e) { /* 隐私模式 */ }
    autosize();
    input.focus();

    input.addEventListener('input', function () {
      autosize();
      try { localStorage.setItem(M.store.draftKey, input.value); } catch (e) {}
      send.disabled = !input.value.trim() || M.store.sending;
    });

    input.addEventListener('compositionstart', function () { composing = true; });
    input.addEventListener('compositionend', function () { composing = false; autosize(); });

    input.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Enter' || ev.shiftKey || composing) return;
      ev.preventDefault();
      submit();
    });

    send.addEventListener('click', function () {
      if (M.store.sending) {
        if (onStop) onStop();
        return;
      }
      submit();
    });

    function submit() {
      const text = input.value.trim();
      if (!text || M.store.sending) return;
      input.value = '';
      try { localStorage.removeItem(M.store.draftKey); } catch (e) {}
      autosize();
      onSend(text);
    }

    return function setSending(flag) {
      M.store.sending = !!flag;
      send.textContent = M.store.sending ? '停止' : '发送';
      send.classList.toggle('stopping', M.store.sending);
      send.disabled = !M.store.sending && !input.value.trim();
    };
  };
})();
