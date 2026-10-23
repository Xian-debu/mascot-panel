/* Markdown + 公式渲染（M38）：块级标题/列表/引用/分隔线/表格/围栏代码，行内粗斜体/代码/链接/KaTeX 公式。
   为什么自己写：面板是内联进 HTML 的单文件，不能塞 marked+katex 两个大包；这里只覆盖模型实际会吐的语法。
   安全：所有文本走 textContent；唯一 innerHTML 是 KaTeX 自己的输出（trust:false，输入由它转义）。 */
(function () {
  const M = (window.Mascot = window.Mascot || {});
  const CJK = /[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef]/;
  /* 能被反斜杠转义的字符；刻意不含 $ ( ) [ ] —— 那些是公式定界符，先按公式解析。 */
  const ESCAPABLE = '*_~`#->|.';

  function text(s) { return document.createTextNode(s); }

  function joinLines(a, b) {
    if (!a) return b;
    if (!b) return a;
    return a + (CJK.test(a.slice(-1)) || CJK.test(b.charAt(0)) ? '' : ' ') + b;
  }

  function renderMath(tex, display) {
    /* 一律 span：display 数学块可能出现在段落里（模型常把 \[..\] 混在句子中间） */
    const el = document.createElement('span');
    el.className = display ? 'math-block' : 'math-inline';
    if (window.katex && typeof window.katex.renderToString === 'function') {
      try {
        el.innerHTML = window.katex.renderToString(tex, {
          displayMode: display, throwOnError: false, strict: false, trust: false, output: 'html',
        });
        return el;
      } catch (e) { /* 落到纯文本 */ }
    }
    el.textContent = tex;
    return el;
  }

  function codeEl(code) {
    const pre = document.createElement('pre');
    const copy = document.createElement('button');
    copy.className = 'copy';
    copy.textContent = '复制';
    copy.addEventListener('click', function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      navigator.clipboard.writeText(code.textContent || '');
      copy.textContent = '已复制';
      setTimeout(function () { copy.textContent = '复制'; }, 1200);
    });
    const box = document.createElement('code');
    box.textContent = code;
    pre.appendChild(copy);
    pre.appendChild(box);
    return pre;
  }

  function findClose(s, from, token) {
    let i = from;
    while (i < s.length) {
      if (s.charAt(i) === '\\' && s.charAt(i + 1) === token.charAt(0)) { i += 2; continue; }
      if (s.startsWith(token, i)) return i;
      i++;
    }
    return -1;
  }

  /* 行内：扫描一遍切段；粗/斜里可以再嵌公式、代码、链接。 */
  function inline(s, into) {
    let buf = '';
    function flush() { if (buf) { into.appendChild(text(buf)); buf = ''; } }

    let i = 0;
    while (i < s.length) {
      const ch = s.charAt(i);
      const two = s.substr(i, 2);

      if (two === '$$') {
        const end = findClose(s, i + 2, '$$');
        if (end > i + 2) { flush(); into.appendChild(renderMath(s.slice(i + 2, end), false)); i = end + 2; continue; }
      }
      if (two === '\\[') {
        const end = findClose(s, i + 2, '\\]');
        if (end > i + 2) { flush(); into.appendChild(renderMath(s.slice(i + 2, end), true)); i = end + 2; continue; }
      }
      if (two === '\\(') {
        const end = findClose(s, i + 2, '\\)');
        if (end > i + 2) { flush(); into.appendChild(renderMath(s.slice(i + 2, end), false)); i = end + 2; continue; }
      }
      if (ch === '$') {
        const next = s.charAt(i + 1);
        if (next && next !== '$' && !/\s/.test(next)) {
          let j = i + 1;
          let end = -1;
          while (j < s.length) {
            if (s.charAt(j) === '\\') { j += 2; continue; }
            if (s.charAt(j) === '$') {
              if (!/\d/.test(s.charAt(j + 1)) && !/\s/.test(s.charAt(j - 1))) end = j;
              break;
            }
            if (s.charAt(j) === '\n') break;
            j++;
          }
          if (end > i + 1) { flush(); into.appendChild(renderMath(s.slice(i + 1, end), false)); i = end + 1; continue; }
        }
      }
      /* 反斜杠转义放在公式之后：\( 是公式开头，不是"转义的左括号" */
      if (ch === '\\' && ESCAPABLE.indexOf(s.charAt(i + 1)) >= 0) {
        buf += s.charAt(i + 1); i += 2; continue;
      }
      if (ch === '`') {
        const end = s.indexOf('`', i + 1);
        if (end > i + 1 && s.slice(i + 1, end).indexOf('\n') < 0) {
          flush();
          const c = document.createElement('code');
          c.textContent = s.slice(i + 1, end);
          into.appendChild(c);
          i = end + 1; continue;
        }
      }
      if (ch === '[') {
        const m = /^\[([^\]\n]+)\]\(\s*([^)\s]+)\s*\)/.exec(s.slice(i));
        if (m && /^(https?:|mailto:)/i.test(m[2])) {
          flush();
          const a = document.createElement('a');
          a.href = m[2];
          a.textContent = m[1];
          a.rel = 'noopener noreferrer';
          a.addEventListener('click', function (ev) {
            ev.preventDefault();
            if (M.api && M.api.openUrl) M.api.openUrl(m[2]);
            else window.open(m[2], '_blank');
          });
          into.appendChild(a);
          i += m[0].length; continue;
        }
      }
      if (two === '**' || two === '__') {
        const end = findClose(s, i + 2, two);
        if (end > i + 2) {
          flush();
          const b = document.createElement('strong');
          inline(s.slice(i + 2, end), b);
          into.appendChild(b);
          i = end + 2; continue;
        }
      }
      if (two === '~~') {
        const end = s.indexOf('~~', i + 2);
        if (end > i + 2) {
          flush();
          const d = document.createElement('del');
          inline(s.slice(i + 2, end), d);
          into.appendChild(d);
          i = end + 2; continue;
        }
      }
      if (ch === '*' || ch === '_') {
        const end = findClose(s, i + 1, ch);
        const inner = end > i + 1 ? s.slice(i + 1, end) : '';
        if (inner && !/^\s|\s$/.test(inner) && inner.indexOf('\n') < 0) {
          flush();
          const em = document.createElement('em');
          inline(inner, em);
          into.appendChild(em);
          i = end + 1; continue;
        }
      }
      buf += ch;
      i++;
    }
    flush();
  }

  function para(lines, into) {
    const p = document.createElement('p');
    inline(lines.reduce(joinLines, ''), p);
    into.appendChild(p);
  }

  function isBlockStart(line) {
    return /^\s*(~~~|\$\$|\\\[)/.test(line) || /^\s{0,3}#{1,6}\s/.test(line) ||
      /^\s{0,3}>/.test(line) || /^\s*([-*+]|\d+[.)])\s+/.test(line) ||
      /^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(line) || /^\s*\|/.test(line) || /^\s*`{3,}/.test(line);
  }

  function renderInto(src, into) {
    const lines = String(src).replace(/\r\n?/g, '\n').split('\n');
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (!line.trim()) { i++; continue; }

      let m = /^\s*(`{3,}|~{3,})\s*([A-Za-z0-9_+-]*)\s*$/.exec(line);
      if (m) {
        const fence = m[1].charAt(0);
        const buf = [];
        i++;
        while (i < lines.length && !new RegExp('^\\s*' + fence + '{3,}\\s*$').test(lines[i])) {
          buf.push(lines[i]); i++;
        }
        i++;
        into.appendChild(codeEl(buf.join('\n')));
        continue;
      }

      if (/^\s*\$\$/.test(line) || /^\s*\\\[/.test(line)) {
        const open = /^\s*\$\$/.test(line) ? '$$' : '\\[';
        const close = open === '$$' ? '$$' : '\\]';
        let body = line.replace(/^\s*(\$\$|\\\[)/, '');
        let closed = body.indexOf(close) >= 0;
        if (closed) {
          body = body.slice(0, body.indexOf(close));
        } else {
          i++;
          while (i < lines.length) {
            const l = lines[i];
            const at = l.indexOf(close);
            if (at >= 0) { body += '\n' + l.slice(0, at); closed = true; i++; break; }
            body += '\n' + l; i++;
          }
        }
        if (closed) { into.appendChild(renderMath(body.trim(), true)); continue; }
      }

      m = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/.exec(line);
      if (m) {
        const h = document.createElement('h' + m[1].length);
        inline(m[2], h);
        into.appendChild(h);
        i++; continue;
      }

      if (/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(line)) {
        into.appendChild(document.createElement('hr'));
        i++; continue;
      }

      if (/^\s{0,3}>/.test(line)) {
        const buf = [];
        while (i < lines.length && (/^\s{0,3}>/.test(lines[i]) || (buf.length && lines[i].trim() && !isBlockStart(lines[i])))) {
          buf.push(lines[i].replace(/^\s{0,3}>\s?/, ''));
          i++;
        }
        const bq = document.createElement('blockquote');
        renderInto(buf.join('\n'), bq);
        into.appendChild(bq);
        continue;
      }

      if (/^\s*([-*+]|\d+[.)])\s+/.test(line)) {
        const ordered = /^\s*\d+[.)]\s+/.test(line);
        const list = document.createElement(ordered ? 'ol' : 'ul');
        while (i < lines.length) {
          const lm = /^\s*([-*+]|\d+[.)])\s+(.*)$/.exec(lines[i]);
          if (!lm) break;
          const li = document.createElement('li');
          const buf = [lm[2]];
          i++;
          while (i < lines.length && lines[i].trim() && !/^\s*([-*+]|\d+[.)])\s+/.test(lines[i]) && !isBlockStart(lines[i])) {
            buf.push(lines[i].trim()); i++;
          }
          inline(buf.reduce(joinLines, ''), li);
          list.appendChild(li);
        }
        into.appendChild(list);
        continue;
      }

      if (line.indexOf('|') >= 0 && i + 1 < lines.length && /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(lines[i + 1])) {
        const cells = function (l) {
          return l.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map(function (c) { return c.trim(); });
        };
        const table = document.createElement('table');
        const head = document.createElement('thead');
        const hr = document.createElement('tr');
        cells(line).forEach(function (c) {
          const th = document.createElement('th');
          inline(c, th);
          hr.appendChild(th);
        });
        head.appendChild(hr);
        table.appendChild(head);
        const tb = document.createElement('tbody');
        i += 2;
        while (i < lines.length && lines[i].indexOf('|') >= 0 && lines[i].trim()) {
          const tr = document.createElement('tr');
          cells(lines[i]).forEach(function (c) {
            const td = document.createElement('td');
            inline(c, td);
            tr.appendChild(td);
          });
          tb.appendChild(tr);
          i++;
        }
        table.appendChild(tb);
        into.appendChild(table);
        continue;
      }

      const buf = [];
      while (i < lines.length && lines[i].trim() && (buf.length === 0 || !isBlockStart(lines[i]))) {
        buf.push(lines[i].trim());
        i++;
      }
      para(buf, into);
    }
  }

  M.renderMarkdown = function (container, src) {
    container.classList.add('md');
    renderInto(src, container);
    return container;
  };
  M.renderInline = function (el, src) { inline(String(src || ''), el); return el; };
})();
