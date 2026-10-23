/* 消息操作（B2）：悬停操作条——复制/折叠/编辑/冻结/版本/上移下移。
   都要按 msg_id 生效；编辑是就地编辑（编辑期间暂停消息重绘，见 chat.js）。 */
(function () {
  const M = (window.Mascot = window.Mascot || {});
  let editingId = null;
  let draft = '';

  M.isEditing = function () { return editingId !== null; };

  function refresh() { if (M.refreshMessages) M.refreshMessages(); }

  /* 调桥接并等回执：无论成败都重绘（失败由后端状态兜底） */
  function call(fn) {
    let result;
    try { result = fn(); } catch (e) { refresh(); return; }
    if (result && typeof result.then === 'function') {
      result.then(refresh, refresh);
    } else {
      refresh();
    }
  }

  function copyText(text, btn) {
    const done = function () {
      const old = btn.textContent;
      btn.textContent = '已复制';
      setTimeout(function () { btn.textContent = old; }, 1000);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text || '').then(done, function () {});
    } else {
      done();
    }
  }

  function actBtn(label, title, fn) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'act';
    b.textContent = label;
    b.title = title;
    b.addEventListener('click', function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      fn(b, ev);
    });
    return b;
  }

  /* 图标（内联 SVG，14px 线性）：比中文两字按钮省一半宽度，语义仍靠 tooltip 说明 */
  const SVG = '<svg viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" '
    + 'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">';
  const ICONS = {
    copy: SVG + '<rect x="5" y="5" width="7" height="7" rx="1.5"/><path d="M9 5V3.5A1.5 1.5 0 0 0 7.5 2h-4A1.5 1.5 0 0 0 2 3.5v4A1.5 1.5 0 0 0 3.5 9H5"/></svg>',
    fold: SVG + '<path d="M4 5.5l3 3 3-3"/></svg>',
    unfold: SVG + '<path d="M4 8.5l3-3 3 3"/></svg>',
    edit: SVG + '<path d="M9.6 2.9l1.5 1.5L5.6 10H4V8.4l5.6-5.5z"/><path d="M3 12h8"/></svg>',
    freeze: SVG + '<path d="M7 2v10M2.6 4.5l8.8 5M11.4 4.5l-8.8 5"/></svg>',
    thaw: SVG + '<path d="M7 2v10M2.6 4.5l8.8 5M11.4 4.5l-8.8 5"/><path d="M2.5 12.5l9-11" stroke-width="1.5"/></svg>',
    version: SVG + '<path d="M11 7a4 4 0 1 1-1.2-2.9"/><path d="M11 2.8V6H7.8"/></svg>',
    select: SVG + '<rect x="2.5" y="2.5" width="9" height="9" rx="2"/><path d="M5 7l1.4 1.5L9.4 5.4"/></svg>',
    grip: '<svg viewBox="0 0 14 14" width="14" height="14" fill="currentColor" aria-hidden="true">'
      + '<circle cx="5" cy="4" r="1"/><circle cx="9" cy="4" r="1"/><circle cx="5" cy="7" r="1"/>'
      + '<circle cx="9" cy="7" r="1"/><circle cx="5" cy="10" r="1"/><circle cx="9" cy="10" r="1"/></svg>',
  };

  function iconBtn(name, title, fn) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'act';
    b.innerHTML = ICONS[name];
    b.title = title;
    b.addEventListener('click', function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      if (fn) fn(b, ev);
    });
    return b;
  }

  function startEdit(id, text) {
    editingId = id;
    draft = text || '';
    refresh();
  }

  function cancelEdit() {
    editingId = null;
    draft = '';
    refresh();
  }

  function saveEdit(id) {
    const text = draft;
    editingId = null;
    draft = '';
    call(function () { return M.api.editMessage(id, text); });
  }

  function renderEditor(el, msg) {
    el.classList.add('editing');
    /* 折叠态会把 .body 截断，编辑时必须放开，否则编辑框被裁成一条线 */
    el.classList.remove('collapsed', 'folded');
    const body = el.querySelector('.body');
    if (!body) return;
    body.textContent = '';
    const ta = document.createElement('textarea');
    ta.className = 'edit-box';
    ta.value = draft;
    ta.setAttribute('spellcheck', 'false');
    ta.addEventListener('input', function () { draft = ta.value; });
    ta.addEventListener('keydown', function (ev) {
      ev.stopPropagation();
      if (ev.key === 'Escape') { ev.preventDefault(); cancelEdit(); }
      if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); saveEdit(msg.id); }
    });
    body.appendChild(ta);

    const row = document.createElement('div');
    row.className = 'edit-row';
    row.appendChild(actBtn('保存', '保存（Ctrl+Enter）', function () { saveEdit(msg.id); }));
    row.appendChild(actBtn('取消', '放弃修改（Esc）', function () { cancelEdit(); }));
    const hint = document.createElement('span');
    hint.className = 'edit-hint';
    hint.textContent = '旧正文会留作上一版本';
    row.appendChild(hint);
    body.appendChild(row);
    setTimeout(function () { ta.focus(); ta.selectionStart = ta.value.length; }, 0);
  }

  M.decorateMessage = function (el, msg) {
    const id = msg.id || '';
    el.dataset.id = id;
    if (msg.frozen) el.classList.add('frozen');
    if (msg.collapsed) el.classList.add('collapsed');
    el.title = '';
    if (!id || msg.pending) return;

    if (editingId === id) { renderEditor(el, msg); return; }

    if (selMode) {
      el.classList.add('selmode');
      if (selIds.has(id)) el.classList.add('sel');
      const box = document.createElement('span');
      box.className = 'sel-box';
      el.appendChild(box);
      el.addEventListener('click', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        toggleSel(id);
      }, true);
      return;
    }

    if (msg.frozen) {
      const flag = document.createElement('span');
      flag.className = 'msg-flag';
      flag.textContent = '冻结';
      flag.title = '这条不发给 AI';
      el.appendChild(flag);
    }

    const acts = document.createElement('div');
    acts.className = 'acts';
    acts.appendChild(iconBtn('copy', '复制这条消息', function (b) {
      copyText(msg.text, b);
      b.classList.add('act-ok');
      setTimeout(function () { b.classList.remove('act-ok'); }, 800);
    }));
    acts.appendChild(iconBtn(msg.collapsed ? 'unfold' : 'fold',
      msg.collapsed ? '展开全文' : '折叠成一行',
      function () { call(function () { return M.api.collapseMessage(id); }); }));
    acts.appendChild(iconBtn('edit', '编辑（旧正文留作上一版本）', function () { startEdit(id, msg.text); }));
    acts.appendChild(iconBtn(msg.frozen ? 'thaw' : 'freeze',
      msg.frozen ? '解冻：重新发给 AI' : '冻结：这条不发给 AI',
      function () { call(function () { return M.api.freezeMessage(id); }); }));
    if (msg.versions) {
      const vb = iconBtn('version', '切回上一个版本（共 ' + (msg.versions + 1) + ' 个版本）',
        function () { call(function () { return M.api.switchVersion(id); }); });
      const num = document.createElement('span');
      num.className = 'act-num';
      num.textContent = msg.versions;
      vb.appendChild(num);
      acts.appendChild(vb);
    }
    /* 上下移动改成拖动（像 session-group 那样直接拖），这里只留把手 */
    const grip = document.createElement('span');
    grip.className = 'act act-grip';
    grip.innerHTML = ICONS.grip;
    grip.title = '拖动调整顺序';
    grip.addEventListener('mousedown', function () { el.draggable = true; });
    grip.addEventListener('mouseup', function () { el.draggable = false; });
    acts.appendChild(grip);
    acts.appendChild(iconBtn('select', '多选：批量冻结 / 合并 / 总结', function () { enterSel(id); }));
    el.appendChild(acts);

    bindDrag(el, id);
  };
  /* ---- 拖动排序（B2）：按住把手拖到目标消息上方/下方 --------------------- */
  let dragId = null;

  function clearDrop() {
    document.querySelectorAll('.msg.drop-before, .msg.drop-after').forEach(function (n) {
      n.classList.remove('drop-before', 'drop-after');
    });
  }

  function markDrop(el, before) {
    clearDrop();
    el.classList.add(before ? 'drop-before' : 'drop-after');
  }

  function destIndex(targetEl, before) {
    const els = Array.from(document.querySelectorAll('#stream article.msg[data-id]'))
      .filter(function (e) { return e.dataset.id !== dragId; });
    let at = targetEl ? els.indexOf(targetEl) : els.length;
    if (at < 0) at = els.length;
    return before ? at : at + 1;
  }

  function bindDrag(el, id) {
    el.addEventListener('dragstart', function (ev) {
      dragId = id;
      el.classList.add('dragging');
      ev.dataTransfer.effectAllowed = 'move';
      try { ev.dataTransfer.setData('text/plain', id); } catch (e) { /* 老内核忽略 */ }
    });
    el.addEventListener('dragend', function () {
      el.draggable = false;
      el.classList.remove('dragging');
      clearDrop();
      dragId = null;
    });
    el.addEventListener('dragover', function (ev) {
      if (!dragId || dragId === id) return;
      ev.preventDefault();
      ev.stopPropagation();
      ev.dataTransfer.dropEffect = 'move';
      const r = el.getBoundingClientRect();
      markDrop(el, ev.clientY - r.top < r.height / 2);
    });
    el.addEventListener('drop', function (ev) {
      if (!dragId || dragId === id) return;
      ev.preventDefault();
      ev.stopPropagation();
      const r = el.getBoundingClientRect();
      const before = ev.clientY - r.top < r.height / 2;
      const at = destIndex(el, before);
      const from = dragId;
      clearDrop();
      call(function () { return M.api.reorder(from, at); });
    });
  }

  /* 拖到列表空白处 = 移到末尾 */
  M.initDragTail = function () {
    const stream = document.getElementById('stream');
    if (!stream || stream.dataset.dragBound) return;
    stream.dataset.dragBound = '1';
    stream.addEventListener('dragover', function (ev) {
      if (!dragId) return;
      ev.preventDefault();
      clearDrop();
    });
    stream.addEventListener('drop', function (ev) {
      if (!dragId) return;
      ev.preventDefault();
      const from = dragId;
      const at = destIndex(null, false);
      clearDrop();
      call(function () { return M.api.reorder(from, at); });
    });
  };

  /* ---- 多选（B2）：批量冻结 / 合并 / 总结 ------------------------------- */
  let selMode = false;
  const selIds = new Set();

  /* 参与 chat.js 的重绘签名：选举状态变了要立刻重画，勾选框才能跟上 */
  M.selectionSig = function () {
    return selMode ? 'sel:' + Array.from(selIds).join(',') : '';
  };

  function enterSel(id) {
    selMode = true;
    selIds.clear();
    if (id) selIds.add(id);
    refresh();
  }

  function exitSel() {
    selMode = false;
    selIds.clear();
    refresh();
  }

  function toggleSel(id) {
    if (selIds.has(id)) selIds.delete(id);
    else selIds.add(id);
    refresh();
  }

  function selAct(name, args) {
    exitSel();
    call(function () { return M.api[name].apply(null, args); });
  }

  function selBtn(label, title, disabled, fn) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'sel-act';
    b.textContent = label;
    b.title = title;
    b.disabled = !!disabled;
    b.addEventListener('click', function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      fn();
    });
    return b;
  }

  function renderSelBar() {
    const bar = document.getElementById('selbar');
    if (!bar) return;
    if (!selMode) {
      bar.hidden = true;
      bar.textContent = '';
      return;
    }
    bar.hidden = false;
    bar.textContent = '';
    const count = document.createElement('span');
    count.className = 'sel-count';
    count.textContent = '已选 ' + selIds.size + ' 条';
    bar.appendChild(count);
    const ids = function () { return Array.from(selIds); };
    const none = selIds.size === 0;
    const two = selIds.size >= 2;
    bar.appendChild(selBtn('冻结', '选中消息不发给 AI', none, function () { selAct('bulkFreeze', [ids(), true]); }));
    bar.appendChild(selBtn('解冻', '选中消息重新发给 AI', none, function () { selAct('bulkFreeze', [ids(), false]); }));
    bar.appendChild(selBtn('合并', '拼成一条（需 2 条以上）', !two, function () { selAct('mergeMessages', [ids()]); }));
    bar.appendChild(selBtn('总结', '让模型总结成一条摘要（需 2 条以上）', !two, function () { selAct('summarize', [ids()]); }));
    bar.appendChild(selBtn('取消', '退出多选', false, exitSel));
  }

  M.afterRender = renderSelBar;
})();
