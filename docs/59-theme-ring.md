# 59 设置页温度 / 三套主题 / 提示环联动（M45–M47）

2026-10-23，用户 m03467：「可以了，当前挺好的；可以继续推进剩下的，当前风格就是默认，请逐步推进，逐步验证后git提交」。
对齐结论（ask_user_question 三项全选推荐）：

1. 温度：0–2 滑杆，默认 1.0；聊天与摘要共用，摘要另留 0.3 上限。
2. 主题：3 套——深空（默认，即当前风格）/ 暖夜（暗色偏暖）/ 浅色。
3. 通知环：只在小球态闪，面板开着不闪；颜色随状态：正常青 / 降级琥珀 / 出错红。

## M45 采样温度

- 配置：src/mascot_core/config.py 的 Settings 加 temperature: float = Field(default=1.0, ge=0.0, le=2.0)，
  并加入 HOT_FIELDS（改配置文件后热生效，不用重启）。
- provider：DeepSeekProvider 构造多一个 temperature 参数（0–2 夹回）；send_stream 的 payload 带 temperature；
  complete（摘要）用 min(self.temperature, 0.3)——用户把温度拉到 2 也不让总结飘。
- 运行时：get_settings 回 temperature；save_settings(model, key, temperature=None) 把温度 round 到 0.1、
  写进 config.toml 的 temperature，并同时改活的 provider.temperature 与 self.settings。
- 面板：设置卡片「温度」行 = range(0..2, step 0.1) + 右侧读数（.settings-val，tabular-nums 防跳动）；
  拖动即时显示，保存才落盘。
- 验证：payload 单测（monkeypatch urllib.request.urlopen）chat = 1.7、complete = 0.3；
  真机拖到 0.3 → config.toml 出现 temperature = 0.3 → 重启回填 0.3。

## M46 三套主题

- tokens.py：THEMES（space / warm / light 各 11 个颜色键）+ THEME_LABELS + theme_options() + theme_css(theme)
  （展开成「css 变量名 → 值」，含别名与派生 rgba）；css_variables(theme) 现在按主题生成。
- 旧别名统一映射（ALIAS_VARS）：line→border、card-solid→card、panel→card、fg→text、muted→text-dim。
  memos.css / messages.css / settings.css 早先写的 --line、--card-solid、--fg 等不再掉回硬编码深色。
- 面板启动即按 settings.theme 合成 HTML（load_panel_html(theme)）；设置页下拉选主题即时换肤
  （get_settings 一次回全三套 theme_vars，JS 往 :root 写变量），保存才写 config.toml 的 theme。
- settings.css 去掉全部硬编码深色（#0d151c / #091016 / rgba(110,231,240,…)），改走 token，浅色才看得清。
- base.css 顺手统一滚动条（::-webkit-scrollbar 8px，thumb 用 --border / hover --text-muted），
  暗色主题里不再出现系统白条。
- 验证：深空 → 浅色（即时切换，设置卡片变白、正文变深）→ 暖夜 → 保存 → config.toml theme = "warm"
  → 重启后面板仍是暖色；备忘视图在三套主题下颜色同样正确。

## M47 提示环联动

- 规则：_mark_alert 在 self._panel_shown 为真时直接返回——面板开着用户已看见消息，再闪是噪声；
  只在收成小球时亮 2.5s。
- 颜色：self._alert_tone ∈ ok / degraded / error；出错（发送异常）走 error，降级走 degraded，否则 ok。
  tokens.py 新增 PIXEL_RED（红家族）；clock.py 的 palette_for(stuck, error) 选色，
  render_clock / render_orbit_frame 多一个 alert_tone 参数，只影响提示环、不改球体配色。
- 验证：ctl to-ball 后 ctl send → 截图见球外青环（约 0.6–2.5s 内），3s 后消失；
  坏 key 实例收成小球再 ctl send → 球是琥珀（降级）而环是红（error），两条语义互不干扰。

## 坑

- 设置页的下拉是原生弹出窗，winput click 打不开选项（事件发给面板而不是弹出层）：
  先点 select，再用 winput key down/up + enter 选择。
- 换肤必须走 CSS 变量：任何一处硬编码颜色都会在浅色主题里变成「黑底黑字」。
- 提示环半径：待机球用 max(6, size/2-4)，环绕球用 ball_r+8；截图时窗口矩形会随环绕移动，
  必须先 wwin list 取当次 rect 再 crop，不能沿用上一轮坐标。
