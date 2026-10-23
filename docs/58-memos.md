# 58 备忘录（M43 / M44）

用户 m02879：重复文本多、每次翻找复制粘贴费劲，要一个「备忘录」——沿用消息气泡的样式，
但只用来记文本；文本多要分门别类、好查找；优势是「始终在顶端显示 + 开机自启动」。
设计四项已与用户对齐（全选推荐项）：

1. 入口：**标题栏切换视图**（会话 ⇄ 备忘），不新增窗口，复用抽屉/搜索框/列表样式。
2. 分组：**单层自建组 + 未分组 + 置顶区**（参考 `/root/dsh-session-groups` 的交互）。
3. 复制：**单击条目 = 复制全文并提示「已复制」**，hover 才出「编辑 / 置顶 / 删除」。
4. 来源：面板内新建、消息操作条「存为备忘」、全局热键快速记，三条都做。

## M43 数据层与运行时

- 新 `src/mascot_core/memos.py`（纯逻辑、无 IO，`now` 由调用方传入）：
  常量 `VERSION=1 / MAX_MEMOS=500 / MAX_GROUPS=50 / MAX_TITLE=60 / MAX_TEXT=8000`；
  `MemoGroup(gid,name,created_at)`、`Memo(mid,text,title,group,pinned,created_at,updated_at)`；
  `MemoStore` 提供 `add/edit/delete/toggle_pin/move/add_group/rename_group/delete_group` 与
  `grouped()`（置顶区最前、自建组按创建序、末尾固定「未分组」区，`id=""`）。
- 标题规则：不填标题时自动取正文首个非空行（`auto_title`，去掉 `#>-*+` 前缀、截 60 字）。
  这条是 4e96a19 补的——最初只有面板里填了标题才有标题，快速记入口进来的条目全是空标题。
- 落盘：`<状态目录>/memos.json`，写前把上一版复制成 `memos.json.bak`，tmp + `os.replace` 原子替换。
- runtime 桥：`memo_list/memo_add/memo_edit/memo_delete/memo_pin/memo_move/memo_group_add/
  memo_group_rename/memo_group_delete/memo_from_message`，快照加 `memo_count`；
  `memo_from_message(msg_id)` 从当前会话按 `msgops.find_index` 取正文（消息操作条入口）。

## M43 面板视图

- 标题栏新增记事本图标 `#memo-toggle`；`div#memoview` 与编辑器遮罩 `div#memo-mask` 都在 `panel.html`。
- `js/memos.js` 负责视图切换（给 `body` 加 `.view-memo`，用 `hidden` 关掉 stream/selbar/composer）、
  分区渲染、拖放归组、单击复制、搜索平铺、编辑器、分组内联重命名/两段式删除。
- 模块顺序：`runtime.py` 的 `CSS_MODULES` 加 `memos.css`、`JS_MODULES` 在 `msgops.js` 后加 `memos.js`。

### 这一轮踩到的坑（都已修）

1. `.memoview{display:flex}` / `.memo-mask{display:flex}` 盖掉了 `hidden` 属性 → 聊天视图下备忘视图和编辑器也常显。
   解法：`base.css` 末尾全局 `[hidden]{display:none!important}`（面板里凡是 `display:flex` 的容器都得能被 `hidden` 关掉）。
2. 备忘视图下每轮轮询把标题刷回会话名 → `sessions.js` 里包一层 `if (!(M.isMemoView && M.isMemoView()))`。
3. 行副标题固定「分组 · 日期」信息量不足 → 有正文时副行显示正文预览；`preview()` 在 body 与 title 相同
   时返回空串（原先会显示「（仅标题）」噪声），并剥掉正文开头残留的「：/-—」。
4. 新建分组的内联条回车不生效、标签「新分组名」竖排 → 抽出 `commit()/drop()` 并绑回车/Esc；
   CSS 让标签 `flex:0 0 auto;white-space:nowrap`。
5. 组头的「改名/删组」只在 hover 显示，真机截图里根本找不到入口 → `.memo-sec-acts` 默认 `opacity:.4`。
6. 标题栏加按钮后「跟随中」被挤成竖排 → `.chip/.dot` 加 `flex:0 0 auto`，`.bar` 的 gap 收到 6px，
   `.sess-toggle` 限宽 124px。

## M43 真机验收（开发副本，状态目录 C:/Users/Public/mascot-memo1state）

分区正确（置顶 ★ / 自建组 / 未分组）、单击行拿到全文（`Get-Clipboard` 校验）并提示「已复制」、
新备忘 Ctrl+Enter 保存且自动标题、拖行到组头即归组（`memos.json` 的 `group` 变成目标组 id）、
＋分组内联创建（回车有效）、搜索「地址」得「2 个结果 / 共 4」、组头改名、删组后条目退回未分组、
切回会话视图标题与输入框恢复、杀进程重启数据全在。
消息操作条「存为备忘」（`msgops.js` 的 `ICONS.memo`，书签形状，排在复制/折叠之后）也验证过：
点一下 `memos.json` 立刻多一条，标题自动取消息首句。

## M44 全局热键快速记

- `runtime.py`：`_create_tray()` 末尾 `_start_hotkey()` → daemon 线程 `mascot-hotkey` →
  `RegisterHotKey` + `GetMessageW` 循环捕 `WM_HOTKEY(0x0312)`；命中后 `open_quick_memo()`
  （`post(Event.CLICK_BALL)` 把面板叫出来，0.45s 后 `panel.evaluate_js("window.MemoQuickOpen()")`）。
- `memos.js` 导出 `window.MemoQuickOpen`：切到备忘视图 → 开新建卡片 → 焦点落到正文。粘上内容 Ctrl+Enter 即存。
- **候选组合键逐个尝试**（`HOTKEY_CANDIDATES`）：Ctrl+Alt+M → Ctrl+Shift+M → Ctrl+Alt+N，谁先成功用谁。
  本机 Ctrl+Alt+M 被占用（`err=0` 是 GetLastError 未开启 `use_last_error` 的假值，别被它误导），
  最终注册成功的是 **Ctrl+Shift+M**。
- 踩坑：worker 里最初写 `from mascot_win import win32, wt` —— `wt` 其实是 `ctypes.wintypes`（不是 `mascot_win` 的模块），
  ImportError 让线程**静默死掉**，日志里一条 hotkey 都没有。改成 `import ctypes.wintypes as wt` 后才看到注册失败日志。
  → 教训：线程里的 import 一定要包 try/except 并 log，否则失败无声无息。
- 设计偏差（已向用户说明）：这个热键是「把面板叫出来并直接落到新建备忘」，不是「不打开面板」的迷你捕获窗；
  真正 panel-less 需要再做一个分层小窗。

## 接口速查

- 状态文件：`<状态目录>/memos.json`（`{"version":1,"groups":[...],"memos":[...]}`）+ `.bak`
- 桥方法：`M.api.listMemos / memoAdd / memoEdit / memoDelete / memoPin / memoMove / memoGroupAdd /
  memoGroupRename / memoGroupDelete / memoFromMessage`
- 热键：注册成功的组合记在日志 `hotkey: <组合> 已注册`
