# M1 平台 spike 实测（Windows 10 / 2560×1600 @150%）

> 目的：在写业务之前，先证明"最难的四处"在本机成立。
> 运行：`C:/Users/Public/mascot/venv/Scripts/python.exe app/0.1.0/scripts/spike_m1.py --seconds 7 --screenshot ...`
> 证据：`evidence/m1-spike.png`（面板 + 球同时出现在桌面上，见下）

## 结果（一次真实运行）

| 检查点 | 结果 |
|---|---|
| DPI 声明 | `per_monitor_v2`；屏幕物理 2560×1600；DPI 144（150%），`scale=1.5` |
| 单实例 | 首次 acquire=true，第二次 acquire=false（命名互斥体生效） |
| 目标发现 | 找到**正在运行的真宠物**：进程 `TX Mascot.exe`，类名 `HwndWrapper[TX Mascot.exe;;<guid>]`，矩形 `(1616, 272, 180, 180)` 物理像素 |
| 自绘球窗口 | 96×96 分层窗口，7 秒内渲染 518 帧，alpha 正确，可点击穿透 |
| WebView2 面板 | 340×460 透明无边框置顶窗口，存活 7.44s 正常退出；运行时版本 155.0.4283.62 |
| 同进程共存 | 主线程跑 pywebview 消息循环，工作线程跑 Win32 分层窗口 + 自己的消息泵，互不阻塞 |

## 得到的关键事实

1. **宠物窗口是 WPF 的 `HwndWrapper[...]`**，类名带每启动随机的 GUID，**不能**用类名精确匹配；
   用 `进程名 == TX Mascot.exe` 或类名包含 `TX Mascot` 才是稳定的。默认配置已加入该进程名。
2. DWM 扩展边框给出的矩形是物理像素，与 `GetWindowRect` 在本机一致；后续仍优先用 DWM。
3. `UpdateLayeredWindow` 要求**预乘 alpha**；不预乘会出现"亮边/黑边"。已在 `LayeredWindow.render` 内处理。
4. 64 位下 **所有 Win32 句柄必须显式声明 argtypes/restype**。spike 期间两次真实崩溃都源于此：
   - `DefWindowProcW` 未声明 → LPARAM 溢出（日志刷屏但不致命）；
   - `GetModuleHandleW` 未声明 → 返回值被截成 32 位 → `RegisterClassW` 访问冲突（进程级崩溃）。
   `win32._declare_64bit_safe_prototypes()` 现在统一收口。
5. pywebview 在本机可用：pythonnet 3.2.1 + clr-loader 0.3.1，WinForms/EdgeChromium 后端正常；
   WebView2 运行时已装（155.x）。

## 架构结论（对规划的回填）

- 面板（富文本/聊天）走 pywebview，**必须占用主线程**；球（每帧位图）走自绘分层窗口，
  放在工作线程。两者之间只通过 `queue.Queue` 传事件 —— 与 docs/10 §7.1 的结论一致，
  但"所有窗口同一 UI 线程"在 pywebview 上无法成立，实际是"主线程 = 面板，工作线程 = 球 + 状态机"，
  跨线程不碰对方的 HWND，只投递消息。这条差异已记为 D-15。
- 状态机与几何/命中全部留在 `mascot_core`（Linux 可测）；平台层只做"发现/画/移动"。

## 复跑方式

```bash
# WSL 侧部署
cd /root/mascot && WIN_ROOT=/mnt/c/Users/Public/mascot bash scripts/deploy-win.sh
# Windows 侧
cd /mnt/c/Users/Public/mascot
./venv/Scripts/python.exe -m pip install -q --no-deps --force-reinstall app/0.1.0
./venv/Scripts/python.exe -m pytest app/0.1.0/tests -m platform -q
./venv/Scripts/python.exe app/0.1.0/scripts/spike_m1.py --seconds 7
```

平台测试 5 条（`tests/platform/test_win32.py`）全部通过：DPI/屏幕、互斥体、窗口枚举、宠物跟随、分层窗口渲染。
