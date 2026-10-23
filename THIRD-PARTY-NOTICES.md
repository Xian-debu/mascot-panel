# 第三方组件与素材说明

本仓库（mascot）自身代码以 MIT 协议发布，但运行与构建用到以下第三方组件。
打包发布的 exe 里也包含它们，分发时请保留各自的许可证声明。

## 运行时依赖

| 组件 | 版本 | 许可证 | 用途 |
| --- | --- | --- | --- |
| [pywebview](https://github.com/r0x0r/pywebview) | >=6.2 | BSD-3-Clause | 面板前端宿主（Windows 上走 WebView2 / EdgeChromium） |
| [Pillow](https://python-pillow.org/) | >=12 | HPND（PIL Software License） | 像素时钟球、状态灯、提示环的位图渲染 |
| [pydantic-settings](https://github.com/pydantic/pydantic-settings) | >=2.4 | MIT | config.toml 的类型化读写 |
| [psutil](https://github.com/giampaolo/psutil) | >=6 | BSD-3-Clause | 进程探测（判断桌宠/自身实例状态） |
| Microsoft Edge WebView2 Runtime | 系统自带/微软分发 | 微软许可（免费可再分发） | pywebview 在 Windows 上的实际渲染引擎 |

## 前端内置资源

| 组件 | 版本 | 许可证 | 位置 |
| --- | --- | --- | --- |
| [KaTeX](https://katex.org/) | 0.16.11 | MIT | src/mascot_app/web/vendor/katex/（katex.min.js、katex.min.css、字体 woff2、LICENSE） |

Markdown 渲染、代码高亮、消息操作等前端逻辑为本仓库自研，未引入 marked / highlight.js 等库。

## 构建工具

| 组件 | 许可证 | 说明 |
| --- | --- | --- |
| [PyInstaller](https://pyinstaller.org/) | GPL-2.0 + 特殊例外（允许打包私有/开源程序） | 生成单文件 exe，仅构建期使用 |
| [uv](https://github.com/astral-sh/uv) | MIT/Apache-2.0 | 依赖解析与虚拟环境 |
| [ruff](https://github.com/astral-sh/ruff) / [pyright](https://github.com/microsoft/pyright) | MIT | 静态检查，仅开发期使用 |

## 外部服务

- **DeepSeek API**（https://api.deepseek.com）：聊天与摘要由用户自己的 API key 调用，
  本仓库不包含任何 key，也不代理/转发用户请求。服务条款见 DeepSeek 官方文档。

## 美术素材

- 本仓库**不包含**任何「天选姬」美术资源（像素立绘、宠物程序）。
  桌宠形象来自用户机器上已安装的华硕天选姬程序，本程序只做窗口/进程探测与聊天面板，
  不复制、不修改、不再分发其素材。截图中的宠物形象版权归原权利人（华硕电脑）所有。
