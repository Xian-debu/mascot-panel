# M27 跟随态拖出来的面板记住「相对宠物」的偏移

## 动机

M24 让面板可以拖标题栏并记住位置，但记的是**绝对屏幕坐标**。宠物（TX-Pet）会跟着用户跑，
面板却钉在原地——用户把面板拖到宠物右边，宠物一挪，面板就掉队了。
plan §8 的 P1「跟随框记住拖拽偏移（落盘而非 localStorage）」就是这个意思。

M27 把位置记忆分两种：

- **无宠物（idle）**：还是绝对坐标（`panel_pos`），拖到哪就钉在哪，符合「宠物没开时面板是独立窗口」的直觉；
- **有宠物（tracking/orbital）**：同时记相对宠物窗口的偏移（`panel_offset`），之后宠物怎么走，
  面板就跟到同一个相对位置。

## 改法

`src/mascot_app/runtime.py`：

- 新增 `load_panel_offset()` / `save_panel_offset(offset)`，复用已有的 `_load_pos/_save_pos`
  （写在 `runtime.json` 的 `panel_offset` 键，`None` 时删除该键）；
- `__init__` 里 `self._panel_offset = load_panel_offset()`；
- `_place_panel()` 在「脏位置落盘」之后、绝对位置分支之前插入一段：
  宠物存在且有 `_panel_offset` 时，目标位置 = `pet.x + dx, pet.y + dy`，再 `_clamp_panel` 夹进工作区；
- `_adopt_panel_pos()`（用户拖完标题栏时调用）：有宠物就更新 `_panel_offset = pos - pet.xy` 并打
  `panel_offset` 日志；没宠物就清掉偏移（打 `panel_offset_cleared`），等宠物回来用默认跟随位置；
- 落盘时机不变（`_panel_dirty` 稳定后一次写），只是同时写两个键；
- `_reset_panel_pos()`（托盘「面板回到默认位置」/`ctl reset-panel`）两个键一起清。

绝对位置仍然写：万一宠物消失，面板还能停在用户最后看到的位置附近。

## 验收（`scripts/verify_m27.py`）

难点是「有宠物」：真实 TX-Pet 不一定开着，所以验收脚本用 `ctypes` 注册了一个类名
`MascotFakePet` 的可见窗口（`WS_POPUP` + 后台 PeekMessage 泵），把
`MASCOT_PET_WINDOW_CLASS` 指向它——`PetTracker` 是按类名子串匹配的，于是运行时
真把假宠物当成跟随目标（state 变 `tracking`），面板走真实跟随逻辑。

Windows 实测（10 项判定，全 true）：

| 项 | 实测 |
| --- | --- |
| `state_tracking` | true（发现假宠物） |
| `panel_rect_initial` | `530,110 488×634`（默认跟随位） |
| `panel_moved` | true（真鼠标拖标题栏） |
| `panel_rect_after_drag` | `370,250` |
| `panel_offset_saved` | `[50,10]`（= 370-320, 250-240） |
| `panel_pos_saved` | `[370,250]` |
| `panel_rect_after_pet_move` | `550,370`（宠物 +180/+120，面板同步） |
| `panel_followed_pet` | true（偏差 ≤6px） |
| `panel_offset_cleared` / `panel_pos_cleared` | true（`ctl reset-panel` 后两个键都没了） |
| `panel_rect_after_reset` | `710,230`（回到默认跟随位） |
| `exit_code` | 0 |

回归：`verify_m13/m24/m25/m26` 全 exit 0、`ok: true`；Linux `pytest 179 passed / 1 skipped`、
ruff 0、pyright 0。新增单测 `test_panel_offset_roundtrip_and_noop_for_bad_data`，
并把 `test_reset_panel_clears_saved_position` 扩到两个键。

## 坑

1. **假宠物窗口必须可见且有尺寸**：`PetTracker` 只枚举 `is_visible` 且 `w>0,h>0` 的窗口，
   `WS_POPUP` 不带 `WS_VISIBLE` 时不会出现（脚本里显式 `ShowWindow(SW_SHOW)`）。
2. **必须泵消息**：窗口不处理消息时 `SetWindowPos` 后的重绘/可见性检查会不稳定，
   脚本起了一个后台线程跑 `PeekMessage/TranslateMessage/DispatchMessage`。
3. **两条位置路径不能互相打架**：跟随分支必须在绝对位置分支**之前**判断，否则拖过的面板仍然钉死；
   反过来没宠物时要清掉偏移，不然宠物回来会突然跳到旧相对位置。
4. **验收要检查「偏移不变」而不是「面板动了」**：只断言面板坐标变化会被 clamp 或默认跟随蒙混过去。

## 遗留

- 偏移只对「用户拖过」的面板生效；没拖过的面板仍用 `follow_offset` 配置里的默认相对位置。
- 多显示器 / 分辨率变化时仍按绝对像素，不做比例迁移（见已知缺口）。
- 宠物窗口尺寸变化时偏移按左上角算，不考虑居中/贴边美学。
