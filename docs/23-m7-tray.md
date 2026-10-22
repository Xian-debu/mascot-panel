# 23 · M7 托盘图标与右键菜单

日期：2026-10-22　里程碑：M7（托盘）
状态：已实现并在真机验证。

## 1. 为什么现在做托盘

M5 之后程序只能靠命令行 `ctl stop` 退出：双击 exe 启动后没有窗口（面板是无边框置顶窗），
也没有入口。托盘是「常驻小程序」的最低交互成本方案，也是开机自启的前提——
自启后用户需要一个随手能暂停/退出/看状态的地方。

## 2. 实现结构

```
src/mascot_win/tray.py        # 纯 Win32：Shell_NotifyIconW + 自建 popup 窗口 + 菜单
src/mascot_win/win32.py       # 补常量/原型（Shell_NotifyIconW、CreatePopupMenu…）
src/mascot_app/runtime.py     # 菜单内容、命令队列、暂停语义、tip 文案
```

### 2.1 窗口选择

托盘回调必须有一个接收 `uCallbackMessage` 的窗口。这里创建一个**隐藏的顶层 popup 窗口**
（类名 `mascot_tray_<uuid8>`），而不是 message-only 窗口：
`TrackPopupMenu` 要求菜单拥有者是前景窗口，否则菜单点外面不会收起。窗口不显示，
也不进任务栏（无 WS_EX_APPWINDOW）。

### 2.2 NOTIFYICONDATAW 用 v3 布局

`cbSize` 必须是完整结构大小，字段顺序照文档：`szTip[128] / szInfo[256] / uTimeoutVersion /
szInfoTitle[64] / dwInfoFlags / guidItem / hBalloonIcon`。虽然当前不用气泡通知，
也用完整布局——少字段会让 `Shell_NotifyIconW` 静默失败（返回 FALSE 且 GetLastError 无提示）。

图标来源：`ExtractIconW(sys.executable, 0)`（exe 自带图标，打包后就是 mascot 的图标），
失败退回 `LoadIconW(IDI_APPLICATION)`，保证一定有图标。

### 2.3 菜单现构建

每次右键都调用 `build_menu()` 重新构建，勾选状态实时（暂停跟随/开机自启）。
菜单项 id 是进程内常量 1001–1005，不进任何协议。

### 2.4 双击

双击托盘 = 面板/小球互切：当前是小球就显示面板，否则收进小球（`_toggle_panel`）。
这让「看不见程序了」永远有一个恢复入口。

## 3. 暂停语义

`暂停跟随` 勾选后：

- 工作线程跳过 `_poll_pet` 与 `_place_panel`（不再跟随宠物窗口移动）；
- 小球动画继续跑（不是冻结画面，避免被误认为卡死）；
- `state.json` 的 `paused` 变 true，`ctl status` 与面板都能读到；
- 托盘 tip 变为 `天选姬 · 跟随中（已暂停跟随）`。

暂停不改变状态机状态：这是「跟踪输入被主观屏蔽」，不是新的运行态。

## 4. 开机自启的开关边界

托盘菜单的 `开机自启` 只对**打包 exe** 生效：开发态（`python.exe -m mascot_app.cli`）
写注册表只会写进 python.exe 路径，是垃圾配置。所以 `_toggle_autostart` 里判断
`sys.frozen`，非打包时记一条 warning 并 no-op；开发验证仍用
`mascot autostart on --exe <path>`。

## 5. 真机验证（verify_m7.py）

```
cd /mnt/c/Users/Public/mascot
./venv/Scripts/python.exe app/0.1.0/scripts/verify_m7.py
```

12 项全过（Windows 10 / 2560×1600 @150%）：

| 检查 | 结果 |
| --- | --- |
| follow_tracking | TX Mascot.exe 961,459 180×180 |
| tray_hwnd | 找到隐藏托盘窗口 |
| tray_double_click_to_ball | orbital |
| tray_double_click_to_panel | tracking |
| ctl_pause | paused=true |
| still_running_when_paused | 进程存活、状态持续刷新 |
| ctl_resume | paused=false |
| ctl_status_running / ctl_stop | true / wm_close |
| process_exit | 0 |

证据：`evidence/m7-tray-menu.png`（右键菜单：显示面板 / 收进小球 / 暂停跟随 / 开机自启 / 退出，
白色系统菜单，两条分隔线位置正确）。

## 6. 踩坑

1. **`Shell_NotifyIconW` 不在 user32**：它在 shell32。第一版声明在 `_user32` 上，
   真机启动直接 `function 'Shell_NotifyIconW' not found`（`ENV_UNSUPPORTED`，退出码 3）。
   修法：win32 增加 `_shell32`，`Shell_NotifyIconW`/`ExtractIconW` 都声明到 shell32。
2. **验收脚本读到上一轮 `state.json`**：单实例会让新进程立刻 `ALREADY_RUNNING` 退出，
   脚本却读着旧快照等 tracking。修法：verify 脚本启动前删 `state.json`/`control.json`。
3. **`TrackPopupMenu` 阻塞消息泵**：菜单开着时工作线程被占住（动画停、ctl 不响应）。
   目前的取舍是可接受的——菜单是模态交互，用户选完即恢复；但如果以后加长驻菜单要改成
   非阻塞方案。
4. **`PostMessageW` 没有公开封装**：验收脚本需要模拟托盘回调，补了
   `win32.post_message(hwnd, msg, wparam, lparam)`。

## 7. 遗留

- 图标是 exe 图标，不是独立设计的托盘图标（后续可加 16/20/24 多尺寸 .ico）。
- 菜单是系统白底，未适配深色；托盘气泡通知未用（docs/12 明确不做气泡通知）。
- 暂停时不重新扫描宠物窗口，恢复后第一帧可能停在宠物刚才的位置，下一轮 poll 归位。
- `ctl to-ball`/`to-panel` 仍然经 control.json；托盘走内存命令队列，两条路径并存但语义一致。
