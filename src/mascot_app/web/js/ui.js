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

    const pending = snap.outbox || 0;
    let banner = '';
    if (snap.degraded) {
      banner = snap.provider_detail
        ? '后端不可达（' + snap.provider_detail + '），消息暂时发不出去，其它功能正常'
        : '后端不可达，消息暂时无法收发（离线可用）';
      if (pending) { banner += ' · ' + pending + ' 条已排队，恢复后自动发'; }
    } else if (snap.error) {
      banner = '出错了：' + snap.error;
      if (pending) { banner += ' · ' + pending + ' 条已排队'; }
    } else if (pending) {
      banner = pending + ' 条消息还没发出去，网络恢复后会自动重发';
    }
    const el = $('banner');
    const sig = banner + '|' + (pending ? String(pending) : '0');
    if (el.dataset.sig !== sig) {
      el.dataset.sig = sig;
      el.textContent = '';
      if (banner) {
        const text = document.createElement('span');
        text.className = 'banner-text';
        text.textContent = banner;
        el.appendChild(text);
      }
      if (banner && pending) {
        const again = document.createElement('button');
        again.className = 'banner-retry';
        again.textContent = '重试';
        again.title = '立刻重发队列里的消息（网络恢复后也会自动发）';
        again.addEventListener('click', function (ev) {
          ev.stopPropagation();
          M.api.retrySend();
        });
        el.appendChild(again);
      }
    }
    el.className = 'banner' + (banner ? ' show' : '');

    /* M34：底部提示行已撤掉（用户反馈没有存在理由）；收进小球只走标题栏头像。 */
  };
})();