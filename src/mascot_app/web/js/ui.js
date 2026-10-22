/* 外壳渲染：状态灯、状态文案、横幅、底部提示。 */
(function () {
  const M = (window.Mascot = window.Mascot || {});
  const $ = function (id) { return document.getElementById(id); };

  /* 状态 → 灯：idle 呼吸 / tracking|orbital 流动 / degraded 红点 */
  const LIGHT = { idle: 'idle', idle_open: 'idle', tracking: 'working', orbital: 'working', degraded: 'error' };
  const LABEL = { idle: '待机', idle_open: '待机', tracking: '跟随中', orbital: '小球', degraded: '降级' };

  M.paintShell = function (snap) {
    const state = snap.state || 'idle';
    $('dot').className = 'dot ' + (LIGHT[state] || 'idle');
    $('state').textContent = LABEL[state] || state;
    $('state').title = snap.reason || '';

    let banner = '';
    if (snap.degraded) {
      banner = snap.provider_detail
        ? '后端不可达（' + snap.provider_detail + '），消息暂时发不出去，其它功能正常'
        : '后端不可达，消息暂时无法收发（离线可用）';
    } else if (snap.error) {
      banner = '出错了：' + snap.error;
    }
    const el = $('banner');
    el.textContent = banner;
    el.className = 'banner' + (banner ? ' show' : '');

    $('hint').textContent =
      state === 'orbital' ? '点小球回到面板' : state === 'idle_open' ? '宠物没开也能聊' : '点小球可收进屏幕边缘';
  };
})();