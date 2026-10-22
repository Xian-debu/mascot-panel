# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir 打包配置。

要点：
- 面板 HTML/CSS/JS 是 package data，必须显式收进 mascot_app/web（否则运行期 resources 找不到）；
- pywebview 的 WebView2 原生库由 pyinstaller-hooks-contrib 的 hook-webview 收集；
- pythonnet/clr 是 WebView2 后端的运行期依赖，静态分析看不见，需显式 hiddenimports；
- console=True + 启动时 hide_console()：双击不闪黑框，命令行还能拿到 JSON。
"""

from pathlib import Path

PKG = Path(SPECPATH)  # packaging/
REPO = PKG.parent

a = Analysis(
    [str(PKG / "entry.py")],
    pathex=[str(REPO / "src")],
    binaries=[],
    datas=[(str(REPO / "src" / "mascot_app" / "web"), "mascot_app/web")],
    hiddenimports=[
        "clr",
        "pythonnet",
        "clr_loader",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "numpy", "PIL.ImageTk", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="mascot",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="mascot",
)
