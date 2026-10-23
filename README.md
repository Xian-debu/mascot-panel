# mascot · 天选姬桌宠（重构版）

把 Windows 上的「天选姬」像素桌宠，接上一个**始终置顶、开机即用**的 AI 聊天面板：
聊天、多会话、消息整理、备忘录、Markdown + LaTeX 渲染，全部收在一个 488×634 的小面板里，
收起后只留一只绕宠物公转的像素时钟球。

> 这不是华硕官方的天选姬，也不是它的修改版。本项目**不包含**任何天选姬美术资源：
> 它探测你机器上已经装好的宠物程序（窗口类名 / 进程名），在旁边跟随一个自己的面板。
> 宠物没开、或探测不到时，退化为右下角常驻的像素时钟球。

| 聊天（Markdown / 代码高亮 / 公式） | 备忘录 | 设置（主题 / 温度） |
| --- | --- | --- |
| ![聊天面板](docs/screenshots/panel-chat.png) | ![备忘录](docs/screenshots/panel-memo.png) | ![设置](docs/screenshots/panel-settings.png) |

## 特性

**聊天**
- 直连 DeepSeek（`deepseek-chat`），流式输出；key 只从环境变量 `DEEPSEEK_AUTH_TOKEN` 或设置页读取，不写进仓库。
- Markdown 渲染（标题 / 列表 / 引用 / 围栏代码 / 行内样式 / 链接），代码块**语法高亮**（python/js/ts/json/bash/sql/c/cpp/rust/go/java），LaTeX 公式用内置 KaTeX 渲染（`\(...\)`、`$...$`、`\[...\]`、`$$...$$`）。
- 后端不可达时横幅提示 + 「重试」；连不上会进**离线待发队列**（`outbox.json`），恢复后自动补发。

**会话**
- 多会话：新建 / 切换 / 重命名 / 删除 / 两段式确认的回收站（`trash.json`，可恢复或彻底删除）。
- 搜索（标题 + 正文，带命中片段）、导出 Markdown（`exports/`）、会话抽屉一键切换。
- 消息操作条（hover 出现）：复制、折叠、存为备忘、编辑（旧正文留作上一版本，可 `↩N` 来回切）、冻结（不发给 AI）、拖动排序、多选 → 批量冻结 / 合并 / 总结。

**备忘录**
- 与聊天同一套气泡样式，但只记文本；标题栏一键切换视图。
- 自建分组（新建 / 改名 / 删组）、置顶区、拖放归组、搜索、**单击条目 = 复制全文**。
- 三种入口：面板内新建、消息操作条「存为备忘」、全局热键快速记（默认 `Ctrl+Shift+M`，候选 `Ctrl+Alt+M` / `Ctrl+Alt+N`）。

**外观与交互**
- 三套主题：深空（默认）/ 暖夜 / 浅色，即时换肤并落盘。
- 采样温度 0–2 滑杆（聊天透传；摘要另封顶 0.3，防止总结发散）。
- 面板 ⇄ 时钟球两态；球绕宠物公转，提示环只在收球时闪，颜色随状态（正常青 / 降级琥珀 / 出错红）。
- 窗口圆角裁切，无灰边；开机自启（HKCU Run）；单实例；`ctl` 命令行远程控制。

## 快速开始

### 方式一：下载 Release（推荐）

1. 到 [Releases](../../releases) 下载最新 `mascot-0.1.0.exe`（单文件，无需安装 Python）。
2. 双击运行。首次启动会在 `%LOCALAPPDATA%\mascot` 下建状态目录，并弹出面板。
3. 打开面板右上齿轮 → 填 API Key → 保存；或事先设置环境变量 `DEEPSEEK_AUTH_TOKEN`。
4. 想开机自启：`mascot.exe autostart on`（卸载/关闭用 `autostart off`）。

> exe 未做代码签名，Windows SmartScreen 可能提示「未知发布者」，选择「更多信息 → 仍要运行」即可。

### 方式二：从源码运行（Windows）

```bash
git clone <this-repo> mascot && cd mascot
uv sync --group dev
uv run mascot doctor                   # 环境体检（JSON）
uv run mascot run --provider deepseek   # 前台启动，Ctrl+C 退出
```

要求：Windows 10/11、Python 3.11+、已安装 **Microsoft Edge WebView2 Runtime**（Win11 一般自带）。
非 Windows 可跑静态检查与纯逻辑，但 GUI 层（`src/mascot_win`）尚未移植。

### 打包成单文件 exe

```bash
bash scripts/build-win.sh      # 产物 C:/Users/Public/mascot/dist/mascot/mascot.exe
bash scripts/install-win.sh    # 装到 %LOCALAPPDATA%\mascot\app\<ver>，更新 current.txt
```

安装是「版本目录不可变 + current.txt 指针」：升级失败可用生成的 `rollback.bat` 回滚。

## 数据与配置

状态目录优先级：`MASCOT_STATE_DIR` → `%LOCALAPPDATA%\mascot` → `~/.mascot`。

| 文件 | 内容 |
| --- | --- |
| `config.toml` | 配置（模型、温度、主题、超时、历史条数……） |
| `sessions.json` | 全部会话与消息（单一真源，写前留 `.bak/.bak1/.bak2`） |
| `memos.json` | 备忘录与分组 |
| `trash.json` | 会话回收站（最多 30 条） |
| `outbox.json` | 离线待发队列 |
| `exports/` | 导出的 Markdown |
| `logs/mascot.log` | 结构化日志（JSON 行） |

常用命令（exe 与源码共用一个入口）：

```bash
mascot ctl status             # 运行中实例的状态
mascot ctl to-ball            # 收成小球
mascot ctl to-panel           # 打开面板
mascot ctl send --text "你好"  # 让运行中的实例发一条消息
mascot ctl dnd on|off         # 免打扰
mascot ctl stop               # 退出
mascot config path|show|get|set|unset
mascot versions list|prune    # 已安装版本目录
```

## 开源组件与致谢

运行时：pywebview（BSD-3）、Pillow（HPND）、pydantic-settings（MIT）、psutil（BSD-3）、
Microsoft Edge WebView2 Runtime；前端内置 KaTeX 0.16.11（MIT）；构建用 PyInstaller。
逐项许可证与素材说明见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。
聊天与摘要由 **DeepSeek API** 提供，需用户自备 key。

## 已知问题

1. **仅 Windows**：分层窗口（WS_EX_LAYERED + UpdateLayeredWindow）、宠物探测、窗口圆角都走 Win32；macOS/Linux 需重写 `src/mascot_win`。
2. **宠物探测依赖窗口类名 `TX Mascot` / 进程名 `TX Mascot.exe` 等**：天选姬版本变化或换机器可能探测不到 → 自动退化为小球态（可用）。
3. **没有自动化测试**：项目约定是「真机自用验收」，纯逻辑靠临时脚本核对 + 静态检查（ruff / pyright）。这是当前最大的工程债。
4. **只支持 DeepSeek**：provider 层留了接口，但只实现了一家；换模型要改 `src/mascot_app/providers`。
5. **前端 Markdown 是自研轻量实现**：不支持表格、脚注、嵌套列表、图片、HTML 内联；KaTeX 只覆盖常用公式。
6. 窗口圆角用 `SetWindowRgn`（1-bit 区域，无抗锯齿），150% 缩放下放大看有轻微阶梯；系统级 DWM 圆角是固定 8px，和设计值 14px 对不上所以没用。
7. **全局热键可能被占用**：按 `Ctrl+Alt+M` → `Ctrl+Shift+M` → `Ctrl+Alt+N` 顺序尝试，全被占用则快速记不可用（日志有 WARNING）。
8. **单实例 + 无文件锁**：同一状态目录同时跑两个进程不受支持（互斥体只保证单实例，不保护并发写）。
9. 高 DPI 只在 150% 下做过真机验证；其它缩放比例可能出现像素对齐瑕疵。
10. 多会话/备忘搜索是线性扫描，上限 200 会话 / 500 备忘，数据量大时首屏会变慢。
11. 面板固定尺寸（488×634 物理像素），不可拉伸；多显示器 + 混合 DPI 未验证。

## 后续改进方向

- 补自动化测试：`mascot_core`（会话、备忘、回收站、离线队列、消息操作）都是纯逻辑，最容易先覆盖。
- 平台层抽象：把 `mascot_win` 抽成接口，补 macOS（或 Linux X11）实现。
- provider 插件化：OpenAI 兼容端点、本地 ollama、模型切换下拉。
- Markdown 渲染换成 marked + DOMPurify（保留 KaTeX），补表格/嵌套列表。
- 备忘与聊天的导入导出（JSON / Markdown）、跨设备同步（可选，需先想清楚密钥）。
- 面板可调宽度、字号档位；无障碍（键盘可达 + 屏幕阅读器标签）。
- 打包签名 + 自动更新（现在 `update` 只能从本地目录/zip 升级）。

## 开发约定

- 一步一提交，subject `<范围>: <做了什么>`；行为变更要写真机验证结果。
- 颜色/字号/圆角只允许定义在 `src/mascot_core/tokens.py`（三套主题共用）。
- 不硬编码用户路径、盘符、端口；所有可变项走 `Settings`。
- 静态检查：`uv run ruff check src`、`uv run pyright`。
- 详细进度与设计决策见 `docs/`（`14-progress.md` 是里程碑流水，`docs/demo.md` 是操作演示）。

## 许可证

代码以 **MIT** 发布，见 [LICENSE](LICENSE)。第三方组件与素材见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。
