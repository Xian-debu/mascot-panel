/* 标题栏的星座风 SVG 时钟头像：12 个刻度点，靠近时针/分针的刻度会呼吸发光。
   设计源：旧版 static/pet-clock.js；颜色全部走 CSS 变量，JS 只改结构与半径。 */
(function () {
  const M = (window.Mascot = window.Mascot || {});
  const NS = 'http://www.w3.org/2000/svg';

  function el(name, attrs) {
    const node = document.createElementNS(NS, name);
    Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    return node;
  }

  M.mountClock = function (host, onClick) {
    if (!host) return null;
    const svg = el('svg', { viewBox: '0 0 100 100', class: 'pet-clock-svg' });

    const defs = el('defs');
    const filter = el('filter', { id: 'clock-glow' });
    filter.appendChild(el('feGaussianBlur', { stdDeviation: '2.5', result: 'blur' }));
    const merge = el('feMerge');
    merge.appendChild(el('feMergeNode', { in: 'blur' }));
    merge.appendChild(el('feMergeNode', { in: 'SourceGraphic' }));
    filter.appendChild(merge);
    defs.appendChild(filter);
    svg.appendChild(defs);

    svg.appendChild(el('circle', { cx: 50, cy: 50, r: 47, class: 'ring' }));

    const ticks = [];
    for (let i = 0; i < 12; i++) {
      const a = (i * 30 - 90) * Math.PI / 180;
      const cx = (50 + 43 * Math.cos(a)).toFixed(2);
      const cy = (50 + 43 * Math.sin(a)).toFixed(2);
      const halo = el('circle', { cx: cx, cy: cy, r: 8, class: 'halo', filter: 'url(#clock-glow)' });
      const dot = el('circle', { cx: cx, cy: cy, r: 2, class: 'tick' });
      svg.appendChild(halo);
      svg.appendChild(dot);
      ticks.push({ dot: dot, halo: halo });
    }

    const hourHand = el('line', { x1: 50, y1: 50, x2: 50, y2: 34, class: 'hand-hour' });
    const minHand = el('line', { x1: 50, y1: 50, x2: 50, y2: 24, class: 'hand-min' });
    const jewel = el('circle', { cx: 50, cy: 50, r: 3, class: 'jewel' });
    svg.appendChild(hourHand);
    svg.appendChild(minHand);
    svg.appendChild(jewel);

    host.innerHTML = '';
    host.appendChild(svg);
    host.addEventListener('click', function () { if (onClick) onClick(); });

    let timer = 0;
    function update() {
      const now = new Date();
      const h = now.getHours() % 12;
      const m = now.getMinutes();
      const s = now.getSeconds();
      const hourAngle = h * 30 + m * 0.5 + s * 0.0083;
      const minAngle = m * 6 + s * 0.1;
      hourHand.setAttribute('transform', 'rotate(' + hourAngle + ', 50, 50)');
      minHand.setAttribute('transform', 'rotate(' + minAngle + ', 50, 50)');

      const hourTick = Math.round(hourAngle / 30) % 12;
      const minTick = Math.round(minAngle / 30) % 12;
      const phase = Date.now() / 573;
      for (let i = 0; i < 12; i++) {
        const t = ticks[i];
        let cls = 'tick';
        let r = 2;
        let halo = 0;
        if (i === hourTick && i === minTick) {
          cls = 'tick tick-both'; r = 4.5; halo = 0.65 + 0.35 * Math.sin(phase);
        } else if (i === hourTick) {
          cls = 'tick tick-hour'; r = 4; halo = 0.15 + 0.45 * (0.5 + 0.5 * Math.sin(phase));
        } else if (i === minTick) {
          cls = 'tick tick-min'; r = 3; halo = 0.08 + 0.27 * (0.5 + 0.5 * Math.sin(phase + Math.PI));
        }
        t.dot.setAttribute('class', cls);
        t.dot.setAttribute('r', r);
        t.halo.setAttribute('opacity', halo.toFixed(2));
      }
    }

    update();
    timer = setInterval(update, 1000);
    return { stop: function () { clearInterval(timer); } };
  };
})();
