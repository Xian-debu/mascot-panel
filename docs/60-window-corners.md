# 60 面板窗口圆角（M48）

2026-10-23，用户 m03785：「这个对话框的圆角旁边的灰色直角可能是设计上的问题，请修复一下」。

## 现象

面板 CSS 是圆角卡片（--r-panel = 14 逻辑像素），窗口本身是矩形、frameless + transparent。
WebView2 的透明背景会透出 WinForms 窗体的底色，于是四个圆角外侧那几块三角区域
显示成浅灰（约 #c0c0c0）——看上去就是「圆角旁边挂了灰色直角」。

## 做法

窗口区域裁成圆角矩形（src/mascot_win/win32.py 的 round_corners）：

- GetWindowRect 拿物理尺寸，GetDpiForWindow 把 14 逻辑像素换成物理半径（150% → 21px）；
- CreateRoundRectRgn(0, 0, w+1, h+1, r*2, r*2) 建区域，SetWindowRgn(hwnd, rgn, True)；
- 成功后区域归系统所有，不要再 DeleteObject；
- 在 Runtime._ensure_panel_hwnd 里拿到面板句柄后调用一次（窗口 fixed size，不会变）。

为什么不走 DWM：DWMWA_WINDOW_CORNER_PREFERENCE 的系统圆角半径固定（8 逻辑像素），
和 14px 对不上，半径 8~14 之间那条灰边照样留着。窗口区域是 1-bit 的、边界没有抗锯齿，
21px 半径下能看到轻微阶梯，但远好于灰色直角。

## 验证

- 开发副本（状态目录 mascot-memo1state）重启后截图放大 6 倍看四角：灰色三角消失，边缘是区域锯齿；
- 1:1 全图检查圆角处没有灰边、也没有把卡片边框切掉；
- 面板拖动/显示隐藏/换主题都不受影响（区域跟着窗口句柄走）。

## 坑

- 区域裁剪只影响绘制与命中测试，不影响 GetWindowRect / wwin list 拿到的尺寸，所以既有的定位逻辑不用改；
- 圆角半径必须和 CSS 的 --r-panel 同步：以后改 tokens.RADIUS 时这里会自动跟着变（调用处传入 RADIUS["r-panel"]）。
