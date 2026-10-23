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
    openUrl: function (url) { return M.hasBridge() ? window.pywebview.api.open_url(url) : Promise.resolve(null); },
    getSettings: function () { return M.hasBridge() ? window.pywebview.api.get_settings() : Promise.resolve(null); },
    saveSettings: function (model, key, temperature) { return M.hasBridge() ? window.pywebview.api.save_settings(model, key, temperature) : Promise.resolve(null); },
    draft: function () { return M.hasBridge() ? window.pywebview.api.draft() : Promise.resolve({ text: '' }); },
    saveDraft: function (text) { return M.hasBridge() ? window.pywebview.api.save_draft(text) : Promise.resolve(null); },
    newSession: function () { return M.hasBridge() ? window.pywebview.api.new_session() : Promise.resolve(null); },
    switchSession: function (sid) { return M.hasBridge() ? window.pywebview.api.switch_session(sid) : Promise.resolve(null); },
    renameSession: function (sid, title) { return M.hasBridge() ? window.pywebview.api.rename_session(sid, title) : Promise.resolve(null); },
    deleteSession: function (sid) { return M.hasBridge() ? window.pywebview.api.delete_session(sid) : Promise.resolve(null); },
    /* 搜索（C1）：标题或正文命中 */
    searchSessions: function (q) { return M.hasBridge() ? window.pywebview.api.search_sessions(q) : Promise.resolve(null); },
    /* 重试（C3）：重发上一条失败的消息 */
    retrySend: function () { return M.hasBridge() ? window.pywebview.api.retry_send() : Promise.resolve(null); },
    /* 回收站（C4）：列表 / 恢复 / 彻底删 */
    listTrash: function () { return M.hasBridge() ? window.pywebview.api.list_trash() : Promise.resolve(null); },
    restoreSession: function (id) { return M.hasBridge() ? window.pywebview.api.restore_session(id) : Promise.resolve(null); },
    purgeSession: function (id) { return M.hasBridge() ? window.pywebview.api.purge_session(id) : Promise.resolve(null); },
    /* 导出（C2）：当前会话 → Markdown */
    exportSession: function (sid) { return M.hasBridge() ? window.pywebview.api.export_session(sid || '') : Promise.resolve(null); },
    /* 消息操作（B2）：全部按 msg_id 定位 */
    freezeMessage: function (id) { return M.hasBridge() ? window.pywebview.api.freeze_message(id) : Promise.resolve(null); },
    bulkFreeze: function (ids, frozen) { return M.hasBridge() ? window.pywebview.api.bulk_freeze(ids, frozen) : Promise.resolve(null); },
    collapseMessage: function (id) { return M.hasBridge() ? window.pywebview.api.collapse_message(id) : Promise.resolve(null); },
    editMessage: function (id, text) { return M.hasBridge() ? window.pywebview.api.edit_message(id, text) : Promise.resolve(null); },
    switchVersion: function (id) { return M.hasBridge() ? window.pywebview.api.switch_version(id) : Promise.resolve(null); },
    moveMessage: function (id, dir) { return M.hasBridge() ? window.pywebview.api.move_message(id, dir) : Promise.resolve(null); },
    mergeMessages: function (ids) { return M.hasBridge() ? window.pywebview.api.merge_messages(ids) : Promise.resolve(null); },
    summarize: function (ids) { return M.hasBridge() ? window.pywebview.api.summarize(ids) : Promise.resolve(null); },
    reorder: function (id, index) { return M.hasBridge() ? window.pywebview.api.reorder(id, index) : Promise.resolve(null); },
    /* 备忘录（M43） */
    listMemos: function () { return M.hasBridge() ? window.pywebview.api.memo_list() : Promise.resolve(null); },
    memoAdd: function (text, title, group) { return M.hasBridge() ? window.pywebview.api.memo_add(text, title || '', group || '') : Promise.resolve(null); },
    memoEdit: function (id, text, title) { return M.hasBridge() ? window.pywebview.api.memo_edit(id, text || '', title || '') : Promise.resolve(null); },
    memoDelete: function (id) { return M.hasBridge() ? window.pywebview.api.memo_delete(id) : Promise.resolve(null); },
    memoPin: function (id) { return M.hasBridge() ? window.pywebview.api.memo_pin(id) : Promise.resolve(null); },
    memoMove: function (id, group) { return M.hasBridge() ? window.pywebview.api.memo_move(id, group || '') : Promise.resolve(null); },
    memoGroupAdd: function (name) { return M.hasBridge() ? window.pywebview.api.memo_group_add(name) : Promise.resolve(null); },
    memoGroupRename: function (id, name) { return M.hasBridge() ? window.pywebview.api.memo_group_rename(id, name) : Promise.resolve(null); },
    memoGroupDelete: function (id) { return M.hasBridge() ? window.pywebview.api.memo_group_delete(id) : Promise.resolve(null); },
    memoFromMessage: function (id) { return M.hasBridge() ? window.pywebview.api.memo_from_message(id) : Promise.resolve(null); },
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
