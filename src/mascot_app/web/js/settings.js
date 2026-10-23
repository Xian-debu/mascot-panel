/* 设置：模型 + API Key。key 只写用户环境变量（等价 setx），不落配置文件。 */
(function () {
  const M = (window.Mascot = window.Mascot || {});
  const $ = function (id) { return document.getElementById(id); };
  let opened = false;

  function setHint(text, bad) {
    const hint = $('set-hint');
    if (!hint) return;
    hint.textContent = text;
    hint.classList.toggle('bad', !!bad);
  }

  function fill(res) {
    if (!res || res.ok === false) {
      setHint('读取设置失败', true);
      return;
    }
    const sel = $('set-model');
    if (res.models && res.models.indexOf(res.model) < 0) {
      // 配置里是别的模型（比如旧值）：留一个选项，别让 select 显示空白
      const opt = document.createElement('option');
      opt.value = res.model;
      opt.textContent = res.model;
      sel.appendChild(opt);
    }
    sel.value = res.model;
    const key = $('set-key');
    key.value = '';
    key.placeholder = res.has_key ? '已设置（留空不修改）' : '未设置';
    setHint(res.has_key ? '当前已有 key。留空保存只会改模型。' : '还没有 key。填一个才能在线聊天。');
  }

  M.initSettings = function () {
    const mask = $('settings-mask');
    if (!mask) return;
    $('gear').addEventListener('click', function (ev) {
      ev.stopPropagation();
      if (opened) return close();
      opened = true;
      mask.hidden = false;
      setHint('读取中…');
      if (M.api && M.api.getSettings) {
        M.api.getSettings().then(fill).catch(function () { setHint('读取设置失败', true); });
      }
    });
    $('settings-close').addEventListener('click', close);
    mask.addEventListener('click', function (ev) {
      if (ev.target === mask) close();
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape' && opened) close();
    });
    $('set-save').addEventListener('click', function () {
      const model = $('set-model').value;
      const key = $('set-key').value.trim();
      setHint('保存中…');
      M.api.saveSettings(model, key).then(function (res) {
        if (!res || res.ok === false) {
          const why = res && res.reason;
          setHint(why === 'BAD_KEY' ? 'key 太短，请检查' : '保存失败：' + (why || '未知原因'), true);
          return;
        }
        setHint('已保存' + (key ? '（key 已写入用户环境变量）' : '（模型会在下一次请求生效）'));
        if (M.log) M.log('settings saved', res);
        setTimeout(close, 700);
      }).catch(function () { setHint('保存失败', true); });
    });
    $('set-key').addEventListener('keydown', function (ev) {
      ev.stopPropagation();
      if (ev.key === 'Enter') $('set-save').click();
    });
  };

  function close() {
    opened = false;
    const mask = $('settings-mask');
    if (mask) mask.hidden = true;
  }
})();
