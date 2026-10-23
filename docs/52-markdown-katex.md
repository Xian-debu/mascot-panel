# M38 文本渲染：Markdown + LaTeX 公式

> 用户原话（m01564）：「我发现一个新问题，就是文本渲染，你可以自己看一下就知道我在说什么了。」
> 现象：DeepSeek 回复里的 `## 二、直观理解`、`---`、`\(V\)`、`\[ \iint_V \nabla \cdot \mathbf{F} \, dV \]` 全是裸文本。

## 1. 结论

面板里每条消息的正文现在走自带的 Markdown 渲染器，公式由内置的 KaTeX 0.16.11 排版：

- 块级：标题（#～######）、无序/有序列表、引用（可嵌套）、分隔线 `---`、围栏代码块（右上角"复制"）、管道表格、整块公式。
- 行内：粗体 `**x**` / `__x__`、斜体 `*x*` / `_x_`、删除线 `~~x~~`、行内代码、`[文字](https://…)`、公式。
- 公式定界符四种都认：`\(…\)`、`\[…\]`、`$$…$$`、`$…$`（`$…$` 收紧规则：开符号后不能是空格、闭符号后不能紧跟数字，避免把价格 `$5 和 $6` 当公式）。

## 2. 为什么自己写解析器

- 面板是 **字符串 HTML 喂给 WebView** 的（`about:blank` 源），没有 `file://` 或 `http://` 文档根，任何相对路径资源都取不到。
- 所以：KaTeX 的 JS/CSS 打进仓库，CSS 里的 `url(fonts/*.woff2)` 在组装时替换成 base64 data URI（20 个字重字体，成品 HTML 约 706KB）。woff/ttf 兜底删掉，省体积。
- 同理 markdown 用自写解析器（`web/js/markdown.js`，约 380 行）：不引入 marked/markdown-it + DOMPurify，因为我们要的只是"聊天正文"这一档，且**不用 innerHTML 拼模型输出**（DOM 节点手搭，XSS 面小）。

## 3. 实现要点

- `runtime.py`：`VENDOR_CSS_PLACEHOLDER` / `katex_css()` / `katex_js()`；`load_panel_html()` 组装时内联；`open_url()` 桥只放行 `http(s)`/`mailto`，链接交给系统浏览器（面板内导航会把整个 UI 顶掉）。
- `markdown.js`：`M.renderMarkdown(container, src)`；块级切分 → 每块交给对应渲染器；段落内部 `joinLines` 给中英之间补空格（视觉更接近原版）。行内扫描用优先级数组：公式（4 种）→ 行内代码 → 转义 → 链接 → 粗体 → 删除线 → 斜体。
- `markdown.css`：`.msg .body.md` 取消 `white-space: pre-wrap`（否则换行会被吃成两倍行距）；`.math-block` 横向可滚；行内公式 `font-size: 1.03em` 与中文等高。
- `chat.js`：`buildBody(container, text)` → 有渲染器就渲染，没有就 `textContent` 兜底；**删掉了"按源码行数自动折叠"**（渲染后行数对不上，会把整段吞掉），要折叠用操作条按钮（`collapsed` 落盘）。

## 4. 踩过的坑

1. **转义判断不能排在公式前面**：`\(V\)` 里的 `(` 被当成"转义的括号"，公式整段失效。现在四个公式分支在前，`ESCAPABLE` 里也刻意不含 `$ ( ) [ ]`。
2. **段落里不能塞 div**：KaTeX 的 display 模式最初包 `<div>`，嵌在 `<p>` 里浏览器会自动拆段落 → 一律 `<span>`，块级效果交给 CSS `display:block`。
3. **未闭合的整块公式会吞掉整条消息**：`$$…` 没写结尾时曾一路吃到文末，现在检测不到闭合就退回普通段落。
4. **自动折叠与渲染冲突**：见上，长消息交给流滚动，别猜行数。
5. 引用块里的裸 `\nabla` 不渲染（没有定界符就不该当公式），这是符合预期的行为，不是 bug。

## 5. 验收（真机，开发副本 `MASCOT_STATE_DIR=C:/Users/Public/mascot-b3state`）

- 斯托克斯定理会话：标题、行内 \(V\)/\(S=\partial V\)/\(\mathbf{F}\)、行间 \(\iiint_V \nabla\cdot\mathbf{F}\,dV=\iint_S \mathbf{F}\cdot\mathbf{n}\,dS\) 全部排版正确（真 KaTeX 字体出图）。
- 块级测试会话：列表、加粗、行内代码、引用、分隔线、表格正常。
- 代码 + 链接会话：python 围栏块带"复制"，链接点开走系统浏览器。
- 真实对话：问"用三行讲一下导数的几何意义，包含一个公式" → 流式输出里有序列表和行内公式逐字渲染，无闪烁。
