/* 会话抽屉（B1）：顶部会话名 + 下拉列表，新建/切换/重命名/删除都在这里。 */
(function () {
  const M = (window.Mascot = window.Mascot || {});
  const $ = function (id) { return document.getElementById(id); };

  let open = false;
  let editingId = null;
  let confirmingId = null;
  let flashUntil = 0;
  let flashText = '';
  let lastSig = '';
  let lastSnapshot = null;
  let query = '';
  let results = null;
  let seq = 0;
  let timer = 0;
  /* 回收站（C4）：mode 在「会话列表」和「回收站」之间切换，复用同一个列表 */
  let mode = 'sessions';
  let trashItems = null;
  let purgingId = null;

  function pad(n) { return n < 10 ? '0' + n : '' + n; }

  /* 相对时间：今天只给 HH:MM，昨天/更早给日期（抽屉一行放不下完整时间）。 */
  function when(ts) {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    const now = new Date();
    const hm = pad(d.getHours()) + ':' + pad(d.getMinutes());
    if (d.toDateString() === now.toDateString()) return hm;
    const y = new Date(now.getTime() - 86400000);
    if (d.toDateString() === y.toDateString()) return '昨天 ' + hm;
    return d.getMonth() + 1 + '-' + d.getDate();
  }

  function flash(text) {
    flashText = text;
    flashUntil = Date.now() + 1600;
    paintHint(lastSnapshot);
  }

  function paintHint(snap) {
    const hint = $('drawer-hint');
    if (Date.now() < flashUntil) { hint.textContent = flashText; return; }
    if (mode === 'trash') {
      hint.textContent = trashItems ? '回收站 · ' + trashItems.length + ' 个' : '回收站';
      return;
    }
    const total = ((snap && snap.sessions) || []).length;
    if (query) {
      hint.textContent = results ? results.length + ' 个结果 / 共 ' + total + ' 个' : '搜索中…';
      return;
    }
    hint.textContent = total + ' 个会话';
  }

  function rowEl(row, isCurrent) {
    const li = document.createElement('li');
    li.className = 'sess-row' + (isCurrent ? ' current' : '') + (editingId === row.id ? ' editing' : '');
    li.dataset.id = row.id;

    if (editingId === row.id) {
      const input = document.createElement('input');
      input.className = 'sess-edit';
      input.value = row.title || '';
      input.maxLength = 40;
      input.addEventListener('click', function (ev) { ev.stopPropagation(); });
      input.addEventListener('keydown', function (ev) {
        ev.stopPropagation();
        if (ev.key === 'Enter') commitRename(row.id, input.value);
        if (ev.key === 'Escape') { editingId = null; repaint(); }
      });
      input.addEventListener('blur', function () {
        if (editingId === row.id) commitRename(row.id, input.value);
      });
      li.appendChild(input);
      setTimeout(function () { input.focus(); input.select(); }, 0);
      return li;
    }

    const main = document.createElement('button');
    main.className = 'sess-main';
    main.title = isCurrent ? '当前会话' : '切换到该会话';
    const title = document.createElement('span');
    title.className = 'sess-name';
    title.textContent = row.title || '新的对话';
    const meta = document.createElement('span');
    meta.className = 'sess-meta';
    const bits = [];
    if (row.count) bits.push(row.count + ' 条');
    if (row.updated_at) bits.push(when(row.updated_at));
    if (row.snippet) bits.push(row.snippet);
    else if (row.preview) bits.push(row.preview);
    meta.textContent = bits.join(' · ') || '空会话';
    main.appendChild(title);
    main.appendChild(meta);
    main.addEventListener('click', function (ev) {
      ev.stopPropagation();
      if (isCurrent) { toggle(false); return; }
      M.api.switchSession(row.id).then(function (res) {
        if (res && res.ok === false) flash(res.reason === 'BUSY' ? '正在收发，稍后再切' : '切换失败');
        else toggle(false);
      });
    });
    li.appendChild(main);

    const acts = document.createElement('span');
    acts.className = 'sess-acts';

    if (confirmingId === row.id) {
      const yes = document.createElement('button');
      yes.className = 'sess-act danger';
      yes.textContent = '删除';
      yes.title = '确认删除这个会话';
      yes.addEventListener('click', function (ev) {
        ev.stopPropagation();
        confirmingId = null;
        M.api.deleteSession(row.id).then(function (res) {
          if (res && res.ok === false) flash(res.reason === 'BUSY' ? '正在收发，稍后再删' : '删除失败');
          repaint();
        });
      });
      const no = document.createElement('button');
      no.className = 'sess-act';
      no.textContent = '取消';
      no.addEventListener('click', function (ev) {
        ev.stopPropagation();
        confirmingId = null;
        repaint();
      });
      acts.appendChild(yes);
      acts.appendChild(no);
    } else {
      const ren = document.createElement('button');
      ren.className = 'sess-act';
      ren.textContent = '改名';
      ren.title = '重命名会话';
      ren.addEventListener('click', function (ev) {
        ev.stopPropagation();
        editingId = row.id;
        repaint();
      });
      const del = document.createElement('button');
      del.className = 'sess-act';
      del.textContent = '删除';
      del.title = '删除会话（会先问一次）';
      del.addEventListener('click', function (ev) {
        ev.stopPropagation();
        confirmingId = row.id;
        repaint();
      });
      acts.appendChild(ren);
      acts.appendChild(del);
    }
    li.appendChild(acts);
    return li;
  }

  /* 回收站一行：恢复 / 彻底删除（彻底删除要再点一次确认）。 */
  function trashRow(item) {
    const li = document.createElement('li');
    li.className = 'sess-row trash-row';
    li.dataset.id = item.id;

    const main = document.createElement('div');
    main.className = 'sess-main';
    const title = document.createElement('span');
    title.className = 'sess-name';
    title.textContent = item.title || '新的对话';
    const meta = document.createElement('span');
    meta.className = 'sess-meta';
    const bits = [];
    if (item.count) bits.push(item.count + ' 条');
    if (item.deleted_at) bits.push('删除于 ' + when(item.deleted_at));
    meta.textContent = bits.join(' · ') || '空会话';
    main.appendChild(title);
    main.appendChild(meta);
    li.appendChild(main);

    const acts = document.createElement('span');
    acts.className = 'sess-acts';
    if (purgingId === item.id) {
      const yes = document.createElement('button');
      yes.className = 'sess-act danger';
      yes.textContent = '彻底删除';
      yes.title = '删除后无法恢复';
      yes.addEventListener('click', function (ev) {
        ev.stopPropagation();
        purgingId = null;
        M.api.purgeSession(item.id).then(function (res) {
          if (res && res.ok === false) flash('删除失败');
          loadTrash();
        });
      });
      const no = document.createElement('button');
      no.className = 'sess-act';
      no.textContent = '取消';
      no.addEventListener('click', function (ev) {
        ev.stopPropagation();
        purgingId = null;
        repaint();
      });
      acts.appendChild(yes);
      acts.appendChild(no);
    } else {
      const back = document.createElement('button');
      back.className = 'sess-act';
      back.textContent = '恢复';
      back.title = '恢复到会话列表并切换过去';
      back.addEventListener('click', function (ev) {
        ev.stopPropagation();
        M.api.restoreSession(item.id).then(function (res) {
          if (res && res.ok === false) {
            flash(res.reason === 'BUSY' ? '正在收发，稍后再恢复' : '恢复失败');
            return;
          }
          flash('已恢复');
          mode = 'sessions';
          trashItems = null;
          loadTrash();
        });
      });
      const gone = document.createElement('button');
      gone.className = 'sess-act';
      gone.textContent = '删除';
      gone.title = '彻底删除（会先问一次）';
      gone.addEventListener('click', function (ev) {
        ev.stopPropagation();
        purgingId = item.id;
        repaint();
      });
      acts.appendChild(back);
      acts.appendChild(gone);
    }
    li.appendChild(acts);
    return li;
  }

  function loadTrash() {
    M.api.listTrash().then(function (res) {
      trashItems = (res && res.items) || [];
      repaint();
    }, function () {
      trashItems = [];
      repaint();
    });
  }

  function commitRename(sid, title) {
    const clean = String(title || '').trim();
    editingId = null;
    if (!clean) { repaint(); return; }
    M.api.renameSession(sid, clean).then(function (res) {
      if (res && res.ok === false) flash('改名校验失败');
      repaint();
    });
  }

  function repaint() {
    lastSig = '';
    if (lastSnapshot) M.renderSessions(lastSnapshot);
  }

  function toggle(force) {
    open = typeof force === 'boolean' ? force : !open;
    const drawer = $('drawer');
    if (open) drawer.removeAttribute('hidden');
    else {
      drawer.setAttribute('hidden', '');
      editingId = null;
      confirmingId = null;
      mode = 'sessions';
      trashItems = null;
      purgingId = null;
      if (query || results) {
        query = '';
        results = null;
        const box = $('sess-q');
        if (box) box.value = '';
      }
    }
    $('sess-toggle').classList.toggle('open', open);
    repaint();
  }

  M.renderSessions = function (snap) {
    if (!snap) return;
    lastSnapshot = snap;
    const rows = snap.sessions || [];
    const current = snap.current_session || '';
    $('sess-title').textContent = snap.current_title || '新的对话';
    $('sess-toggle').title = '会话：' + rows.length + ' 个（点击展开）';
    paintHint(snap);
    if (!open) return;

    if (mode === 'trash') {
      const items = trashItems || [];
      const tsig = 'trash|' + (purgingId || '') + '|' + items.map(function (it) {
        return [it.id, it.title, it.count, it.deleted_at].join('~');
      }).join(',');
      if (tsig === lastSig) return;
      lastSig = tsig;
      const tlist = $('sess-list');
      tlist.textContent = '';
      items.forEach(function (item) { tlist.appendChild(trashRow(item)); });
      if (!items.length) {
        const empty = document.createElement('li');
        empty.className = 'sess-empty';
        empty.textContent = '回收站是空的';
        tlist.appendChild(empty);
      }
      return;
    }

    const shown = results || rows;
    const sig = current + '|' + query + '|' + (editingId || '') + '|' + (confirmingId || '') + '|' +
      shown.map(function (r) {
        return [r.id, r.title, r.count, r.updated_at, r.preview, r.snippet || ''].join('~');
      }).join(',');
    if (sig === lastSig) return;
    lastSig = sig;

    const list = $('sess-list');
    list.textContent = '';
    shown.forEach(function (row) { list.appendChild(rowEl(row, row.id === current)); });
    if (!shown.length && query) {
      const empty = document.createElement('li');
      empty.className = 'sess-empty';
      empty.textContent = '没有匹配「' + query + '」的会话';
      list.appendChild(empty);
    }
  };

  function runSearch() {
    const mine = ++seq;
    if (!query) { results = null; repaint(); return; }
    M.api.searchSessions(query).then(function (res) {
      if (mine !== seq) return;
      results = (res && res.results) || [];
      repaint();
    }, function () {
      if (mine !== seq) return;
      results = [];
      repaint();
    });
  }

  M.initSessions = function () {
    $('sess-toggle').addEventListener('click', function (ev) {
      ev.stopPropagation();
      toggle();
    });
    const box = $('sess-q');
    if (box) {
      box.addEventListener('click', function (ev) { ev.stopPropagation(); });
      box.addEventListener('input', function () {
        query = box.value.trim();
        window.clearTimeout(timer);
        timer = window.setTimeout(runSearch, 140);
      });
      box.addEventListener('keydown', function (ev) {
        ev.stopPropagation();
        if (ev.key === 'Escape') { box.value = ''; query = ''; results = null; repaint(); }
      });
    }
    $('trash-sess').addEventListener('click', function (ev) {
      ev.stopPropagation();
      if (mode === 'trash') {
        mode = 'sessions';
        trashItems = null;
        lastSig = '';
        repaint();
        return;
      }
      mode = 'trash';
      query = '';
      results = null;
      purgingId = null;
      const box = $('sess-q');
      if (box) box.value = '';
      lastSig = '';
      loadTrash();
    });
    $('export-sess').addEventListener('click', function (ev) {
      ev.stopPropagation();
      flash('导出中…');
      M.api.exportSession('').then(function (res) {
        if (res && res.ok) flash('已导出 ' + res.name);
        else flash(res && res.reason === 'EMPTY' ? '空会话，没内容可导' : '导出失败');
      });
    });
    $('new-sess').addEventListener('click', function (ev) {
      ev.stopPropagation();
      M.api.newSession().then(function (res) {
        if (res && res.ok === false) flash(res.reason === 'BUSY' ? '正在收发，稍后再建' : '新建失败');
        else toggle(false);
      });
    });
    document.addEventListener('click', function (ev) {
      if (!open) return;
      if (ev.target.closest('#drawer') || ev.target.closest('#sess-toggle')) return;
      toggle(false);
    });
  };
})();
