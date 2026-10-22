# M6b 环绕整帧（彗尾 + 命中圆）

日期：2026-10-22 夜。目标：把“球在宠物外面绕”的观感补回来——
原版是**窗口随球移动的整帧绘制**（球 + 彗尾在同一张位图里），我们 M6a 只有球。

## 1. 为什么要一个大窗口

彗尾必须和球在同一帧、同一坐标系里，否则两层窗口会互相遮挡/撕裂。
因此环绕态窗口不再贴着球，而是**以宠物中心为中心的大方窗**，整帧绘制：

```
ball_r  = max(30, int(pet.w * ball_ratio))          # 0.34 → 180px 宠物得 61
orbit_r = max(150, pet.w // 2 + ball_r + gap)        # 90 + 61 + 10 = 161
window  = 2 * (orbit_r + ball_r + pad)               # 2*(161+61+6) = 456
```

`mascot_core.geometry.orbit_layout()` 是纯函数，三个数全可单测；
`ball_ratio` 语义从“轨道比例”改为“球半径比例”（与原版 `BALL_RATIO` 对齐）。

## 2. 点击穿透：WM_NCHITTEST + 命中圆

整帧窗口 456×456，但只有球该接点击，其它区域必须让给桌面/浏览器。原版用
per-pixel alpha + `SetCapture` 兜底；本版用窗口消息层解决，事件更早、更可靠：

| 条件 | 返回 | 效果 |
| --- | --- | --- |
| `click_through=True`（面板态） | `HTTRANSPARENT` | 整窗穿透 |
| 有命中圆，点在圆内 | `HTCLIENT` | 球可点/可拖 |
| 有命中圆，点在圆外 | `HTTRANSPARENT` | 穿透到下层 |
| 无命中圆（诊断态） | `HTCLIENT` | 整窗可点 |

命中圆由运行时每帧 `set_hit_circle(ball_cx, ball_cy, ball_r + 4)` 更新，
半径 +4 是给像素化边缘留的容错。

**坑（值得记）**：`WM_NCHITTEST` 里不能用 `GetWindowRect()` 判断窗口位置。
移动用的是 `SWP_ASYNCWINDOWPOS`（异步、不阻塞 UI 线程），消息到达时系统矩形
可能还是旧值，平台测试稳定复现 `assert -1 == 1`（球心被判成穿透）。
改为记录**我们自己 move 过去的坐标** `self._pos`，命中判断只做纯算术，
既没竞态也省一次系统调用。

## 3. 尺寸变化

窗口尺寸随宠物大小变化（用户换分辨率/换宠物皮肤）。`render()` 发现图像尺寸
≠ 当前窗口尺寸时用 `SetWindowPos(SWP_NOMOVE|SWP_NOZORDER|SWP_NOACTIVATE)` 改大小，
**不再**用 LANCZOS 缩放（会糊掉像素边缘，且违背“一次绘制=一次呈现”）。

## 4. 验证

- 单测：`orbit_layout` 三例（180px 宠物 / 60px 下限 / 尺寸单调）。
- 平台测试：`test_layered_window_hit_circle_controls_click_through` —— 真窗口 + 真
  `SendMessageW(WM_NCHITTEST)`，断言球心/半径内 HTCLIENT、角落/球外 HTTRANSPARENT。
- 真机：Linux 全绿（ruff 0 / pyright 0）；Windows `pytest app/0.1.0/tests` 全绿；
  demo 实跑截图 `evidence/m6b-orbital.png`（球 + 彗尾 + 宠物同屏）。
- 帧率仍为 10 fps（与原版 `FPS = 10` 一致）；单帧 456×456 的 PIL 绘制在本机
  （i7 + 集显）无掉帧。

## 5. 已知缺口 / 下一步

- 穿透粒度是“球的外接圆”，球体透明角落仍会挡住下层 ~4px 区域（原版是逐像素）。
  实际体验几乎无感，暂不引入 per-pixel mask。
- 环绕态不能拖拽改轨道半径（原版可拖拽调速）；`settings.ball_ratio` 目前只能改配置。
- 球与面板之间没有过渡动画（硬切）。
- 面板立绘仍是占位（M6c），旧渐变球 `render_ball` 已无运行时调用，可择机删除。
