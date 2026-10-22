/* 消息流：时间分桶、同角色不重复署名、代码块可复制、长消息折叠。 */
(function () {
  const M = (window.Mascot = window.Mascot || {});
  const $ = function (id) { return document.getElementById(id); };
  const FOLD_LINES = 12;
  let lastSignature = '';

  function pad(n) { return n < 10 ? '0' + n : '' + n; }

  function bucketLabel(ts) {
    const d = new Date(ts * 1000);
    if (!ts) return '';
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    const hm = pad(d.getHours()) + ':' + pad(d.getMinutes());
    if (sameDay) return '今天 ' + hm;
    const y = new Date(now.getTime() - 86400000);
    if (d.toDateString() === y.toDateString()) return '昨天 ' + hm;
    return (d.getMonth() + 1) + '-' + d.getDate() + ' ' + hm;
  }

  /* 极简 markdown：只认围栏代码块与行内代码，其余按纯文本处理（不 innerHTML）。 */
  function buildBody(text) {
    const frag = document.createDocumentFragment();
    const parts = String(text).split(/```/);
    parts.forEach(function (part, i) {
      if (!part) return;
      if (i % 2 === 1) {
        const pre = document.createElement('pre');
        const code = document.createElement('code');
        code.textContent = part.replace(/^[a-zA-Z0-9_-]+\n/, '');
        const copy = document.createElement('button');
        copy.className = 'copy';
        copy.textContent = '复制';
        copy.addEventListener('click', function () {
          navigator.clipboard.writeText(code.textContent || '');
          copy.textContent = '已复制';
          setTimeout(function () { copy.textContent = '复制'; }, 1200);
        });
        pre.appendChild(copy);
        pre.appendChild(code);
        frag.appendChild(pre);
      } else {
        part.split(/\n/).forEach(function (line, k) {
          if (k > 0) frag.appendChild(document.createTextNode('\n'));
          const chunks = line.split(/`([^`]+)`/);
          chunks.forEach(function (chunk, j) {
            if (!chunk) return;
            if (j % 2 === 1) {
              const c = document.createElement('code');
              c.textContent = chunk;
              frag.appendChild(c);
            } else {
              frag.appendChild(document.createTextNode(chunk));
            }
          });
        });
      }
    });
    return frag;
  }

  function messageEl(msg, sameRoleAsPrev) {
    const el = document.createElement('article');
    el.className = 'msg ' + (msg.role === 'user' ? 'user' : 'assistant') + (msg.pending ? ' pending' : '');
    if (!sameRoleAsPrev) {
      const who = document.createElement('span');
      who.className = 'who';
      who.textContent = msg.role === 'user' ? '我' : '天选姬';
      el.appendChild(who);
    }
    const body = document.createElement('div');
    body.className = 'body';
    body.appendChild(buildBody(msg.text || ''));
    el.appendChild(body);

    const lines = String(msg.text || '').split('\n').length;
    if (lines > FOLD_LINES) {
      el.classList.add('folded');
      const btn = document.createElement('button');
      btn.className = 'expand';
      btn.textContent = '展开全部 ' + lines + ' 行';
      btn.addEventListener('click', function () {
        const folded = el.classList.toggle('folded');
        btn.textContent = folded ? '展开全部 ' + lines + ' 行' : '收起';
      });
      el.appendChild(btn);
    }
    return el;
  }

  M.renderMessages = function (messages) {
    const list = messages || [];
    const signature = list.map(function (m) { return (m.id || '') + ':' + (m.text || '').length + ':' + (m.pending ? 1 : 0); }).join('|');
    if (signature === lastSignature) return;
    lastSignature = signature;

    const stream = $('stream');
    const atBottom = stream.scrollHeight - stream.scrollTop - stream.clientHeight < 40;
    stream.textContent = '';

    if (!list.length) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = '还没有消息。\n说句话试试——离线时也会先显示在本地。';
      stream.appendChild(empty);
      return;
    }

    let prevBucket = '';
    let prevRole = '';
    list.forEach(function (msg) {
      const bucket = bucketLabel(msg.ts);
      if (bucket && bucket !== prevBucket) {
        const div = document.createElement('div');
        div.className = 'bucket';
        div.textContent = bucket;
        stream.appendChild(div);
        prevBucket = bucket;
        prevRole = '';
      }
      stream.appendChild(messageEl(msg, msg.role === prevRole));
      prevRole = msg.role;
    });

    if (atBottom) stream.scrollTop = stream.scrollHeight;
  };
})();
