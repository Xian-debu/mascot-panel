# 61 单实例僵尸与启动接管（M49）

2026-10-25，用户 m04234：「双击 C:\Users\ZYX\AppData\Local\mascot\app\0.1.0\mascot.exe 没有反应，
大概一个小时前突然报错然后退出了，现在起不来」。

## 现象

- 双击 exe 毫无反应（没有窗口、没有报错框）；进程列表里却有一个两小时前启动的 mascot.exe 活着。
- 那个进程 11 个线程全部 Wait、CPU 正常、有 WebView2 子进程，但枚举它名下窗口只有：
  mascot-panel（vis=False）、.NET/GDI+ 辅助窗口、控制台窗口 —— **小球窗口不存在**，托盘也早没了。
- logs/mascot.log 最后一条停在「state orbital CLICK_CLOCK」，之后没有任何行、没有 traceback。

## 根因（两层）

1. **工作线程静默死亡**：Runtime._worker 的 while 循环体没有 try/except，
   任何一次异常（定位/渲染/轮询）都会直接跳出循环，走 finally 把托盘和小球 destroy 掉、self._ball 置 None，
   然后线程结束。daemon 线程的 traceback 在无控制台的 PyInstaller 窗口程序里没人看得见，日志里也没有。
   结果：面板早在收小球时就藏了、小球刚被销毁 → 桌面上什么都没有，但 pywebview 主线程还在消息循环，
   进程不死、命名互斥体一直被占。
2. **启动路径无脑 exit 3**：cmd_run 里互斥体被占就直接 _fail("ALREADY_RUNNING", ..., EXIT_ENV) 退 3。
   从资源管理器双击没有控制台，那段 JSON 没人看得到 —— 用户看到的就是「双击毫无反应」。

## 修复

### 1. 工作线程崩溃 = 进程退出（runtime.py）

- 原来的 _worker 改名为 _worker_loop；新的 _worker 包一层 try/except BaseException：
  记 log.exception，然后 _fatal_exit()。
- _fatal_exit(reason)：log.critical + 拆托盘/小球 + os._exit(1)。
  进程退出，命名互斥体随之释放，下一次启动一定能接管。

### 2. 窗口资源自检（runtime.py）

- 工作循环每 5 秒 _check_windows_health()：小球句柄或（面板显示时的）面板句柄
  win32.is_window() 失效 → _fatal_exit。宁可重启，也不留「没界面还占着互斥体」的僵尸。

### 3. 启动时识别僵尸并接管（cli.py + win32.py）

- win32.py 新增 is_window / is_hung（IsWindow / IsHungAppWindow，显式 argtypes）。
- cmd_run 抢互斥体失败后：
  - _instance_health(pid)：pid 文件 → psutil 核对进程 + 枚举该 pid 的**可见**顶层窗口 + IsHungAppWindow；
  - 健康（有可见窗口且不卡）→ 写 control.json 发 to_panel（等同 ctl to-panel）把面板叫出来，
    仍按原语义返回 ALREADY_RUNNING（exit 3，附 activated=true 与 pid）；
  - 僵尸（无可见窗口 / 卡死）→ log.warning 记录证据，_terminate_stale(pid) 结束它，
    最多等 5 秒重新抢互斥体；抢到就继续正常启动，抢不到才失败。
- 无控制台（sys.stdout is None）且接管失败时，用 MessageBoxW 告诉用户「请在任务管理器结束 mascot.exe」，
  不再静默退出。

## 验证（本机真机）

1. 结束遗留僵尸（pid 17192）→ 双击恢复。
2. 开发副本（venv python -m mascot_app.cli，真实状态目录）：
   - 第二次启动 → exit 3，JSON 带 activated=true，日志 already_running，面板立刻可见；
   - 用 P/Invoke 把该实例全部窗口 ShowWindow(SW_HIDE) 伪造僵尸 → 再启动：
     日志 "zombie: pid=... 无可见窗口（windows=0 hung=False），结束它并接管" → "结束成功" →
     新进程托盘/热键初始化、面板可见、mascot.pid 更新为新 pid。
3. 安装版 0.1.1：双击启动 + 二次双击唤出面板 + 数据（会话「你好」、备忘 14 条）完好。

## 坑

- 判僵尸不能用 MainWindowHandle：隐藏窗口的进程 MainWindowHandle=0，正常小球态也可能为 0
  （面板关着、小球是 layered 窗口）。必须按 pid 枚举顶层窗口 + IsWindowVisible。
- IsHungAppWindow 只对**可见**窗口有意义；没有可见窗口时直接判僵尸，不看 hung。
- pid 文件不参与判重（历史设计），所以僵尸判定必须自己读 pid 文件 + 核对 cmdline/exe，避免 pid 复用误杀。
- 结束进程用 psutil（terminate → wait 3s → kill），不要按名字全局杀 mascot.exe（会误杀安装版/开发版另一个实例）。
