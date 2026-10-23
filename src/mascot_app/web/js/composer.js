/* 输入区：1-4 行自适应、草稿落盘（走 runtime 的 draft.txt）、IME 保护、Enter 发送 / Shift+Enter 换行。 */
(function () {
  const M = (window.Mascot = window.Mascot || {});
  const $ = function (id) { return document.getElementById(id); };
  const LINE = 20;
  let composing = false;
  let draftTimer = null;

  function autosize() {
    const el = $('input');
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, LINE * 4 + 14) + 'px';
  }

  /* 草稿：WebView 在 about:blank 源下 localStorage 不持久，必须落到状态目录。
     每 400ms 一次，别在每次按键都写盘。 */
  function scheduleSave(value) {
    if (draftTimer) clearTimeout(draftTimer);
    draftTimer = setTimeout(function () {
      draftTimer = null;
      if (M.api && M.api.saveDraft) M.api.saveDraft(value);
    }, 400);
  }

  M.initComposer = function (onSend, onStop) {
    const input = $('input');
    const send = $('send');

    if (M.api && M.api.draft) {
      M.api.draft().then(function (res) {
        if (res && res.text && !input.value) {
          input.value = res.text;
          autosize();
          send.disabled = !input.value.trim() || M.store.sending;
        }
      });
    }
    autosize();
    input.focus();

    input.addEventListener('input', function () {
      autosize();
      scheduleSave(input.value);
      send.disabled = !input.value.trim() || M.store.sending;
    });

    /* IME：中文输入法组词过程中的 Enter 是"选词"，不是发送 */
    input.addEventListener('compositionstart', function () { composing = true; });
    input.addEventListener('compositionend', function () { composing = false; autosize(); });

    input.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Enter' || ev.shiftKey || composing || ev.isComposing) return;
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
      scheduleSave('');
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
