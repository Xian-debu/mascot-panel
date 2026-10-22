# mascot — 天选姬桌宠（重构版）

跟随框（聊天面板）+ 环绕球（像素时钟）二合一的 Windows 桌宠。本仓库是 **2026-10 全面重构**的新产物，
旧实现 `E:\TX-Pet`（483 行单文件壳 + 919 行单文件 SPA，无版本控制）**冻结保留**，本仓库与其零共享代码。

> 规划与决策记录在 `/root/mascot-admin`（管理仓库）。本仓库只承载产品代码。
> 当前阶段：**M31/M32 路线转向**（降级放行交互 + 直连 DeepSeek，不再依赖本机 8890；key 只读环境变量 `DEEPSEEK_AUTH_TOKEN`）。
> 此前能力：像素时钟球 + 环绕彗尾 + 面板品牌位 + 托盘 + 免打扰 + 冷启动 0.7s + legacy/auto 聊天后端 + 流式增量与停止生成 + config 写回与 dnd/暂停记忆 + 宠物没开时右下角常驻像素时钟球，可拖动、记忆位置、拖到边缘自动吸附、右键菜单可复位 + 独立面板 + 对话跨重启保留与 ctl clear-history + config 写回保留注释/未知键/表 + 版本目录列举/回收与真回滚 + 改配置热重载 + 历史条数可配置（history_limit 热生效）+ health 独立短超时（降级横幅 1.9s）+ clear-history 连后端 history 一起屏蔽 + 本地目录/zip 就地升级（mascot.exe update）+ 面板启动时真的隐藏、可拖标题栏、跟随态按相对宠物偏移跟随、拖过记住位置并可复位（托盘/菜单/ctl reset-panel）+ 待机球单击开面板、双击回右下角（双击时间窗 click_window_ms 可配置，0 = 单击立即开面板）+ 环绕球双击暂停/恢复公转 + 新消息到达时小球亮像素提示环（状态灯），见 docs/20–47。
> 交付形态：单 exe 双入口（双击=GUI，带参数=CLI，`mascot doctor/run/ctl/autostart`）；
> M5 打包/安装/自启/回滚见 docs/19-m5-delivery.md。

## 它是什么

天选姬（游戏本自带像素宠物）在桌面上走动时，旁边跟随一个 340×460 的聊天面板；
点面板上的时钟图标 → 面板变成一颗像素时钟球，绕宠物公转（可拖拽调速，点击回到面板）。

## 结构

```
src/mascot_core/    纯逻辑（无 Win32、可 Ubuntu CI 单测）
  geometry.py         跟随偏移、球轨道、屏幕边界 clamp
  hit.py              命中测试纯函数
  state.py            状态机（idle/tracking/orbital/degraded）+ 原因码
  config.py           pydantic-settings 配置（TOML + 环境变量）
  tokens.py           设计令牌 → CSS 变量 + PIL 调色板（唯一颜色真源）
  contract.py         ChatProvider 协议与 DTO
src/mascot_win/     Windows 平台层（仅 windows-latest 测）
src/mascot_render/  渲染（PIL 画球/状态灯 + 快照画廊）
src/mascot_app/     组装与 CLI（run / doctor / ctl），web/panel.html 面板前端
tests/unit/         纯逻辑单测         tests/snapshot/  像素基线
tests/platform/     Win32 平台测试     tests/contract/  provider 契约
scripts/            deploy-win.sh（Windows 开发副本）、build-win.sh/install-win.sh/uninstall-win.sh（打包/安装/卸载）、
                    verify_m2.py/verify_m4.py/verify_m7.py/verify_m9.py/verify_m10.py/verify_m11.py/
                    verify_m12.py/verify_m13.py/verify_m14.py/verify_m15.py/verify_m16.py/verify_m17.py/verify_m18.py/verify_m19.py/verify_m20.py/verify_m21.py/verify_m22.py/verify_m23.py/verify_m24.py/verify_m25.py/verify_m26.py/verify_m27.py/verify_m28.py/verify_m29.py/verify_m30.py、
                    dev-chat-backend.py/dev-legacy-backend.py、make_baselines.py、measure_start.py
packaging/          PyInstaller 入口与 spec（entry.py / mascot.spec）
```

## 快速开始

```bash
uv sync --group dev
uv run mascot doctor          # 环境体检（JSON）
uv run pytest                 # 纯逻辑 + 快照基线（Linux/Windows 均可）
uv run ruff check . && uv run pyright
```

Windows 侧运行（开发期）：

```bash
scripts/deploy-win.sh         # 同步到 C:/Users/Public/mascot/app/<ver>/ 并冒烟
```

## 依赖（2026-10-22 冻结）

运行期：`pywebview>=6.2,<7`（WebView2 壳）、`pillow>=12`（像素渲染）、`pydantic-settings>=2.4`（配置）、`psutil>=6`（进程探测）。
开发期：`pytest`、`ruff`、`pyright`。锁文件 `uv.lock` 入库。

## 约定

- 一步一提交，subject：`<范围>: <做了什么>`，body 写"为什么 + 实测数字"。
- 纯逻辑必须有单测；平台相关代码必须能在无桌面的 CI 上跳过而不失败。
- 颜色/字号/圆角只允许定义在 `mascot_core.tokens`，HTML 与 PIL 都从它派生（`test_token_contract` 把关）。
- 改了绘制就重跑 `scripts/make_baselines.py` 并提交新基线。
- 不硬编码用户路径、盘符、发行版名、端口。
- 详见 `AGENTS.md`。