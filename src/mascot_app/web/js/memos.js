/* 备忘录视图（M43）：分组 + 置顶 + 搜索 + 单击复制。
 *
 * 设计要点（与用户对齐的结论）：
 *   - 标题栏切换「会话 ⇄ 备忘」，不新增窗口；
 *   - 单层自建分组 + 未分组 + 置顶区，组可折叠、可改名、可删除；
 *   - 单击条目 = 复制全文（这是最高频动作），hover 才出编辑/置顶/删除；
 *   - 数据全由 Python 持有（memos.json），JS 只画和筛选。
 */
(function () {
  const M = (window.Mascot = window.Mascot || {});
  const $ = function (id) { return document.getElementById(id); };

  const state = {
    view: 'chat', // 'chat' | 'memo'
    data: null, // {groups, sections, total}
    sig: '',
    q: '',
    collapsed: {}, // gid -> true（仅内存，重启回到全部展开）
    editingId: '',
    editingGroup: '',
    confirmingId: '',
    confirmingGroup: '',
    flash: '',
    flashTimer: null,
    loaded: false,
  };

  function hasBridge() {
    return M.hasBridge && M.hasBridge();
  }

  function nowText() {
    return state.flash;
  }

  function setFlash(text) {
    state.flash = text || '';
    if (state.flashTimer) clearTimeout(state.flashTimer);
    if (text) {
      state.flashTimer = setTimeout(function () {
        state.flash = '';
        state.flashTimer = null;
        paintHint();
      }, 1600);
    }
    paintHint();
  }

  /* 复制：WebView2 里 navigator.clipboard 有时被策略挡，退回 execCommand。 */
  function copyText(text) {
    return new Promise(function (resolve) {
      const done = function (ok) { resolve(ok); };
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(function () { done(true); }, function () {
            done(fallbackCopy(text));
          });
          return;
        }
      } catch (err) { /* 落到兜底 */ }
      done(fallbackCopy(text));
    });
  }

  function fallbackCopy(text) {
    try {
      const box = document.createElement('textarea');
      box.value = text;
      box.style.position = 'fixed';
      box.style.left = '-9999px';
      document.body.appendChild(box);
      box.select();
      const ok = document.execCommand('copy');
      document.body.removeChild(box);
      return ok;
    } catch (err) {
      return false;
    }
  }

  function call(fn) {
    return Promise.resolve(fn()).then(function (res) {
      if (res && res.ok === false && res.reason) {
        setFlash(reasonText(res.reason));
      }
      return reload();
    }).catch(function () {
      setFlash('操作失败');
    });
  }

  function reasonText(reason) {
    const map = {
      EMPTY: '内容不能为空',
      NOT_FOUND: '这条已经不在了',
      NO_CHANGE: '没有改动',
      BAD_NAME: '名字不能为空或重名',
      NO_MOVE: '已经在那一组了',
      BUSY: '正在回复，稍后再试',
    };
    return map[reason] || '操作失败';
  }

  function reload() {
    if (!hasBridge() || !M.api.listMemos) return Promise.resolve();
    return M.api.listMemos().then(function (res) {
      if (res && res.ok) {
        state.data = res;
        state.loaded = true;
        state.sig = '';
        render();
      }
      return res;
    }).catch(function () {});
  }

  function sections() {
    const data = state.data;
    if (!data) return [];
    return data.sections || [];
  }

  function groupName(gid) {
    const groups = (state.data && state.data.groups) || [];
    for (let i = 0; i < groups.length; i += 1) {
      if (groups[i].id === gid) return groups[i].name;
    }
    return '';
  }

  function match(text, q) {
    return String(text || '').toLowerCase().indexOf(q) >= 0;
  }

  /* 搜索结果：平铺成一组，命中片段高亮交给浏览器光标即可（不引 innerHTML）。 */
  function searchResults(q) {
    const out = [];
    sections().forEach(function (sec) {
      (sec.items || []).forEach(function (item) {
        const hay = (item.title || '') + '\n' + (item.text || '');
        if (match(hay, q)) out.push({ item: item, group: sec.name });
      });
    });
    return out;
  }

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function btn(cls, text, title, onClick) {
    const b = document.createElement('button');
    b.className = cls;
    b.textContent = text;
    if (title) b.title = title;
    b.addEventListener('click', function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      onClick(ev);
    });
    return b;
  }

  function preview(item) {
    const body = String(item.text || '').replace(/\s+/g, ' ').trim();
    const title = String(item.title || '').trim();
    if (!title) return body.slice(0, 60);
    if (body.indexOf(title) === 0) {
      /* 正文只是标题的重复时副行留空（不要再显示「仅标题」噪声） */
      return body.slice(title.length).replace(/^[\s:：\-—]+/, '').trim().slice(0, 60);
    }
    return body.slice(0, 60);
  }

  function rowEl(item, groupLabel) {
    const row = el('div', 'memo-row');
    row.dataset.id = item.id;
    row.draggable = true;
    if (item.pinned) row.classList.add('is-pinned');

    const main = el('div', 'memo-main');
    const name = el('div', 'memo-name', item.title || preview(item));
    main.appendChild(name);
    const sub = el('div', 'memo-sub');
    /* 有标题时副行放正文预览（便于在列表里认出内容），正文与标题相同时退回分组+日期 */
    const body = preview(item);
    const meta = [item.title ? body : (groupLabel || ''), String(new Date(item.updated_at * 1000).toLocaleDateString())];
    sub.textContent = meta.filter(Boolean).join(' · ');
    main.appendChild(sub);
    row.appendChild(main);

    const acts = el('div', 'memo-acts');
    if (state.editingId === item.id) {
      acts.appendChild(btn('memo-act', '取消', '退出编辑', function () { closeEditor(); }));
    } else {
      acts.appendChild(btn('memo-act', '编辑', '编辑这条备忘', function () { openEditor(item); }));
      acts.appendChild(btn('memo-act', item.pinned ? '取消置顶' : '置顶', '置顶后排在所有分组之前', function () {
        call(function () { return M.api.memoPin(item.id); });
      }));
      if (state.confirmingId === item.id) {
        acts.appendChild(btn('memo-act danger', '确认删', '彻底删除', function () {
          state.confirmingId = '';
          call(function () { return M.api.memoDelete(item.id); });
        }));
        acts.appendChild(btn('memo-act', '取消', '', function () {
          state.confirmingId = '';
          state.sig = '';
          render();
        }));
      } else {
        acts.appendChild(btn('memo-act', '删除', '删除这条备忘', function () {
          state.confirmingId = item.id;
          state.sig = '';
          render();
        }));
      }
    }
    row.appendChild(acts);

    /* 单击 = 复制全文（用户对齐的主路径） */
    main.addEventListener('click', function (ev) {
      if (state.editingId) return;
      ev.preventDefault();
      copyText(item.text || '').then(function (ok) {
        setFlash(ok ? '已复制' : '复制失败，长按选择文本');
      });
    });

    /* 拖进分组：拖动开始记录 id，分组头/未分组区接收 */
    row.addEventListener('dragstart', function (ev) {
      ev.dataTransfer.setData('text/plain', item.id);
      ev.dataTransfer.effectAllowed = 'move';
      row.classList.add('dragging');
    });
    row.addEventListener('dragend', function () { row.classList.remove('dragging'); });

    return row;
  }

  function sectionEl(sec) {
    const wrap = el('div', 'memo-sec');
    wrap.dataset.gid = sec.id;
    const head = el('div', 'memo-sec-head');
    const isGroup = !!sec.id && sec.id !== '\u0000pinned';

    const caret = el('span', 'memo-caret', state.collapsed[sec.id] ? '▸' : '▾');
    head.appendChild(caret);
    if (state.editingGroup === sec.id && isGroup) {
      const input = document.createElement('input');
      input.className = 'memo-rename';
      input.value = sec.name;
      input.addEventListener('keydown', function (ev) {
        ev.stopPropagation();
        if (ev.key === 'Escape') { state.editingGroup = ''; state.sig = ''; render(); }
        if (ev.key === 'Enter') {
          const name = input.value.trim();
          state.editingGroup = '';
          if (name && name !== sec.name) call(function () { return M.api.memoGroupRename(sec.id, name); });
          else { state.sig = ''; render(); }
        }
      });
      head.appendChild(input);
      setTimeout(function () { input.focus(); input.select(); }, 0);
    } else {
      head.appendChild(el('span', 'memo-sec-name', sec.name));
    }
    head.appendChild(el('span', 'memo-sec-count', String((sec.items || []).length)));

    const acts = el('div', 'memo-sec-acts');
    if (isGroup) {
      acts.appendChild(btn('memo-act', '改名', '重命名分组（F2）', function () {
        state.editingGroup = sec.id;
        state.sig = '';
        render();
      }));
      if (state.confirmingGroup === sec.id) {
        acts.appendChild(btn('memo-act danger', '确认删组', '分组删除后条目退回未分组', function () {
          state.confirmingGroup = '';
          call(function () { return M.api.memoGroupDelete(sec.id); });
        }));
        acts.appendChild(btn('memo-act', '取消', '', function () {
          state.confirmingGroup = '';
          state.sig = '';
          render();
        }));
      } else {
        acts.appendChild(btn('memo-act', '删组', '删除分组（条目退回未分组）', function () {
          state.confirmingGroup = sec.id;
          state.sig = '';
          render();
        }));
      }
    }
    head.appendChild(acts);
    head.addEventListener('click', function (ev) {
      if (ev.target && ev.target.tagName === 'INPUT') return;
      if (ev.target && ev.target.classList.contains('memo-act')) return;
      state.collapsed[sec.id] = !state.collapsed[sec.id];
      state.sig = '';
      render();
    });

    /* 拖进这一组 */
    head.addEventListener('dragover', function (ev) {
      if (!isGroup) return; // 置顶区不接受投放：置顶用按钮
      ev.preventDefault();
      ev.dataTransfer.dropEffect = 'move';
      head.classList.add('drop-target');
    });
    head.addEventListener('dragleave', function () { head.classList.remove('drop-target'); });
    head.addEventListener('drop', function (ev) {
      if (!isGroup) return;
      ev.preventDefault();
      head.classList.remove('drop-target');
      const id = ev.dataTransfer.getData('text/plain');
      if (id) call(function () { return M.api.memoMove(id, sec.id); });
    });

    wrap.appendChild(head);

    if (!state.collapsed[sec.id]) {
      const list = el('div', 'memo-items');
      (sec.items || []).forEach(function (item) {
        list.appendChild(rowEl(item, isGroup ? '' : sec.id === '' ? '' : sec.name));
      });
      if (!(sec.items || []).length) {
        const empty = el('div', 'memo-empty', isGroup ? '拖动条目到这里，或用「新备忘」选这一组' : '还没有备忘');
        list.appendChild(empty);
      }
      wrap.appendChild(list);
    }
    /* 未分组区也接受投放（拖出分组） */
    if (sec.id === '') {
      head.addEventListener('dragover', function (ev) {
        ev.preventDefault();
        head.classList.add('drop-target');
      });
      head.addEventListener('dragleave', function () { head.classList.remove('drop-target'); });
      head.addEventListener('drop', function (ev) {
        ev.preventDefault();
        head.classList.remove('drop-target');
        const id = ev.dataTransfer.getData('text/plain');
        if (id) call(function () { return M.api.memoMove(id, ''); });
      });
    }
    return wrap;
  }

  function render() {
    const list = $('memo-list');
    if (!list) return;
    if (!state.loaded) {
      list.textContent = '';
      list.appendChild(el('div', 'memo-empty', '读取中…'));
      paintHint();
      return;
    }
    const q = state.q.trim().toLowerCase();
    const sig = [
      'v1',
      q,
      state.editingId,
      state.editingGroup,
      state.confirmingId,
      state.confirmingGroup,
      JSON.stringify(state.collapsed),
      state.data ? state.data.total : -1,
      (sections() || []).map(function (s) {
        return s.id + ':' + s.name + ':' + (s.items || []).map(function (i) {
          return i.id + i.updated_at + (i.pinned ? 'p' : '');
        }).join(',');
      }).join('|'),
    ].join('~');
    if (sig === state.sig) return;
    state.sig = sig;

    list.textContent = '';
    if (q) {
      const hits = searchResults(q);
      if (!hits.length) {
        list.appendChild(el('div', 'memo-empty', '没有匹配「' + state.q.trim() + '」的备忘'));
      } else {
        const box = el('div', 'memo-hits');
        hits.forEach(function (hit) { box.appendChild(rowEl(hit.item, hit.group)); });
        list.appendChild(box);
      }
      paintHint(hits.length);
      return;
    }

    const secs = sections();
    let any = false;
    secs.forEach(function (sec) {
      if (!sec.id && !(sec.items || []).length && secs.length > 1) {
        // 未分组空时仍画出来：它是拖出分组的落点
      }
      list.appendChild(sectionEl(sec));
      if ((sec.items || []).length) any = true;
    });
    if (!secs.length) {
      list.appendChild(el('div', 'memo-empty', '还没有备忘，点「＋ 新备忘」记一条'));
    }
    paintHint();
    if (!any && secs.length) {
      // 全空也保持分组头可见（上面已经画了）
    }
  }

  function paintHint(hits) {
    const hint = $('memo-hint');
    if (!hint) return;
    if (state.flash) { hint.textContent = state.flash; hint.classList.add('is-flash'); return; }
    hint.classList.remove('is-flash');
    const total = state.data ? state.data.total : 0;
    if (state.q.trim()) {
      hint.textContent = (hits === undefined ? (searchResults(state.q.trim().toLowerCase()).length) : hits) + ' 个结果 / 共 ' + total;
    } else {
      hint.textContent = total + ' 条备忘';
    }
  }

  function setView(view) {
    state.view = view === 'memo' ? 'memo' : 'chat';
    const memo = state.view === 'memo';
    const shell = document.body;
    if (shell) shell.classList.toggle('view-memo', memo);
    const view_ = $('memoview');
    if (view_) view_.hidden = !memo;
    ['stream', 'selbar'].forEach(function (id) {
      const node = $(id);
      if (node) node.hidden = memo;
    });
    const composer = document.querySelector('.composer');
    if (composer) composer.hidden = memo;
    const toggle = $('memo-toggle');
    if (toggle) toggle.classList.toggle('active', memo);
    const title = $('sess-title');
    if (title && memo) title.textContent = '备忘录';
    if (!memo) {
      const snap = M.store && M.store.snapshot;
      if (title && snap) title.textContent = snap.current_title || '新的对话';
    }
    if (memo) reload();
  }

  M.toggleMemoView = function () {
    setView(state.view === 'memo' ? 'chat' : 'memo');
  };
  M.isMemoView = function () { return state.view === 'memo'; };
  M.renderMemos = function () {
    /* 快照轮询只用来同步「条数」徽标；列表本身按需 reload（改动后必刷） */
    const snap = M.store && M.store.snapshot;
    if (!snap) return;
    if (state.view === 'memo' && typeof snap.memo_count === 'number') {
      if (state.data) state.data.total = snap.memo_count;
    }
  };

  /* ---- 编辑器 ---------------------------------------------------------- */

  function fillGroups(current) {
    const sel = $('memo-group');
    if (!sel) return;
    sel.textContent = '';
    const opt0 = document.createElement('option');
    opt0.value = '';
    opt0.textContent = '未分组';
    sel.appendChild(opt0);
    ((state.data && state.data.groups) || []).forEach(function (g) {
      const opt = document.createElement('option');
      opt.value = g.id;
      opt.textContent = g.name;
      sel.appendChild(opt);
    });
    sel.value = current || '';
  }

  function openEditor(item, group) {
    if (!state.loaded) reload();
    state.editingId = item ? item.id : '';
    fillGroups(item ? item.group : group || '');
    const title = $('memo-card-title');
    if (title) title.textContent = item ? '编辑备忘' : '新备忘';
    const t = $('memo-title');
    const body = $('memo-text');
    if (t) t.value = item ? item.title || '' : '';
    if (body) body.value = item ? item.text || '' : '';
    const mask = $('memo-mask');
    if (mask) mask.hidden = false;
    if (body) setTimeout(function () { body.focus(); }, 30);
    state.sig = '';
    render();
  }

  function closeEditor() {
    state.editingId = '';
    const mask = $('memo-mask');
    if (mask) mask.hidden = true;
    state.sig = '';
    render();
  }

  function saveEditor() {
    const t = $('memo-title');
    const body = $('memo-text');
    const sel = $('memo-group');
    const text = body ? body.value.trim() : '';
    if (!text) { setFlash('正文不能为空'); if (body) body.focus(); return; }
    const title = t ? t.value.trim() : '';
    const gid = sel ? sel.value : '';
    const editing = state.editingId;
    Promise.resolve(
      editing
        ? M.api.memoEdit(editing, text, title).then(function (res) {
            if (res && res.ok && gid !== '') return M.api.memoMove(editing, gid);
            return res;
          })
        : M.api.memoAdd(text, title, gid)
    ).then(function (res) {
      if (res && res.ok === false && res.reason) {
        setFlash(reasonText(res.reason));
        return;
      }
      setFlash(editing ? '已保存' : '已新建');
      closeEditor();
      reload();
    }).catch(function () { setFlash('保存失败'); });
  }

  function newGroup() {
    const name = $('memo-newname');
    const input = document.createElement('input');
    /* 用编辑器卡片复用一次输入：不引 window.prompt（WebView2 里常被挡） */
    state.editingGroup = '__new__';
    const list = $('memo-list');
    if (!list) return;
    const bar = el('div', 'memo-newgroup-bar');
    bar.appendChild(el('span', 'memo-sec-name', '新分组名'));
    const field = document.createElement('input');
    field.className = 'memo-rename';
    field.value = name || '';
    field.placeholder = '例如：常用话术';
    bar.appendChild(field);
    const commit = function () {
      const v = field.value.trim();
      if (!v) { field.focus(); return; }
      bar.remove();
      state.editingGroup = '';
      call(function () { return M.api.memoGroupAdd(v); }).then(function () { setFlash('已新建分组'); });
    };
    const drop = function () {
      bar.remove();
      state.editingGroup = '';
    };
    bar.appendChild(btn('memo-act', '创建', '回车也能创建', commit));
    bar.appendChild(btn('memo-act', '取消', 'Esc 取消', drop));
    field.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') { ev.preventDefault(); commit(); }
      else if (ev.key === 'Escape') { ev.preventDefault(); drop(); }
    });
    list.insertBefore(bar, list.firstChild);
    setTimeout(function () { field.focus(); }, 30);
    if (input) input.remove();
  }

  M.initMemos = function () {
    const toggle = $('memo-toggle');
    if (toggle) toggle.addEventListener('click', function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      M.toggleMemoView();
    });
    const add = $('memo-new');
    if (add) add.addEventListener('click', function (ev) {
      ev.preventDefault();
      openEditor(null, '');
    });
    const grp = $('memo-newgroup');
    if (grp) grp.addEventListener('click', function (ev) {
      ev.preventDefault();
      newGroup();
    });
    const q = $('memo-q');
    if (q) {
      q.addEventListener('input', function () {
        state.q = q.value || '';
        state.sig = '';
        render();
      });
      q.addEventListener('keydown', function (ev) {
        ev.stopPropagation();
        if (ev.key === 'Escape') { q.value = ''; state.q = ''; state.sig = ''; render(); }
      });
    }
    const save = $('memo-save');
    if (save) save.addEventListener('click', function (ev) { ev.preventDefault(); saveEditor(); });
    const cancel = $('memo-x');
    if (cancel) cancel.addEventListener('click', function (ev) { ev.preventDefault(); closeEditor(); });
    const card = $('memo-mask');
    if (card) card.addEventListener('click', function (ev) {
      if (ev.target === card) closeEditor();
    });
    const body = $('memo-text');
    if (body) body.addEventListener('keydown', function (ev) {
      ev.stopPropagation();
      if (ev.key === 'Escape') closeEditor();
      if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); saveEditor(); }
    });
    const title = $('memo-title');
    if (title) title.addEventListener('keydown', function (ev) { ev.stopPropagation(); });
    /* 标题里按 F2 直接改名分组：沿用列表里的内联输入 */
    document.addEventListener('keydown', function (ev) {
      if (state.view !== 'memo') return;
      if (ev.key !== 'F2') return;
      const sec = document.querySelector('.memo-sec[data-gid]');
      if (sec && sec.dataset.gid && sec.dataset.gid.indexOf('\u0000') !== 0) {
        state.editingGroup = sec.dataset.gid;
        state.sig = '';
        render();
      }
    });
  };
})();
