/* 消息流：时间分桶、同角色不重复署名、代码块可复制、长消息折叠。 */
(function () {
  const M = (window.Mascot = window.Mascot || {});
  const $ = function (id) { return document.getElementById(id); };
  const FOLD_LINES = 12;
  let lastSignature = null;
  let lastArgs = null;

  function pad(n) { return n < 10 ? '0' + n : '' + n; }

  /* 便宜的字符串指纹：消息正文可能很长，签名里只放哈希（编辑后长度不变也能重绘）。 */
  function hash(s) {
    let h = 5381;
    const str = String(s || '');
    for (let i = 0; i < str.length; i++) h = ((h << 5) + h + str.charCodeAt(i)) | 0;
    return h;
  }

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
              /* **粗体**：合并消息/摘要里的角色标记要用它，别把星号直接露出来 */
              chunk.split(/\*\*([^*]+)\*\*/).forEach(function (seg, k) {
                if (!seg) return;
                if (k % 2 === 1) {
                  const b = document.createElement('strong');
                  b.textContent = seg;
                  frag.appendChild(b);
                } else {
                  frag.appendChild(document.createTextNode(seg));
                }
              });
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
    if (lines > FOLD_LINES && !msg.collapsed) {
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
    /* B2：消息操作条（复制/折叠/编辑/冻结/版本/上移下移）由 msgops.js 挂上来 */
    if (M.decorateMessage) M.decorateMessage(el, msg);
    return el;
  }

  M.renderMessages = function (messages, streaming, sessionId, force) {
    lastArgs = [messages, streaming, sessionId];
    if (!force && M.isEditing && M.isEditing()) {
      /* 就地编辑中不重绘：正在敲的字不能被下一次快照清掉；保存/取消后 refreshMessages */
      lastSignature = null;
      return;
    }
    const list = messages || [];
    const live = streaming && streaming.active ? String(streaming.text || '') : '';
    const signature = (sessionId || '') + '#' + list.map(function (m) {
      return (m.id || '') + ':' + hash(m.text) + ':' + (m.pending ? 1 : 0) + ':' +
        (m.frozen ? 1 : 0) + ':' + (m.collapsed ? 1 : 0) + ':' + (m.versions || 0);
    }).join('|') + '#' + live.length + ':' + hash(live) + '#' + ((M.selectionSig && M.selectionSig()) || '');
    if (signature === lastSignature) return;
    lastSignature = signature;

    const stream = $('stream');
    const atBottom = stream.scrollHeight - stream.scrollTop - stream.clientHeight < 40;
    stream.textContent = '';

    if (!list.length && !live) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      const star = document.createElement('div');
      star.className = 'empty-star';
      const title = document.createElement('p');
      title.className = 'empty-title';
      title.textContent = '在的，说点什么吧';
      const hint = document.createElement('span');
      hint.className = 'empty-hint';
      hint.textContent = 'Enter 发送 · Shift+Enter 换行';
      empty.appendChild(star);
      empty.appendChild(title);
      empty.appendChild(hint);
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

    if (live) {
      const el = document.createElement('article');
      el.className = 'msg assistant streaming';
      const body = document.createElement('div');
      body.className = 'body';
      body.appendChild(buildBody(live));
      const caret = document.createElement('span');
      caret.className = 'caret';
      body.appendChild(caret);
      el.appendChild(body);
      stream.appendChild(el);
    } else if (streaming && streaming.active) {
      /* 已经发出、还没收到第一个分片：显示"思考中"占位 */
      const el = document.createElement('article');
      el.className = 'msg assistant streaming';
      const body = document.createElement('div');
      body.className = 'body';
      const dots = document.createElement('span');
      dots.className = 'thinking';
      dots.textContent = '思考中';
      body.appendChild(dots);
      el.appendChild(body);
      stream.appendChild(el);
    }

    if (atBottom) stream.scrollTop = stream.scrollHeight;
    /* 多选浮动条等"依附于消息列表"的 UI，在每次重绘后同步一次 */
    if (M.afterRender) M.afterRender();
  };

  /* 本地状态变了（选中/编辑/操作回执）立刻重绘一次，不必等下一轮轮询。 */
  M.refreshMessages = function () {
    if (!lastArgs) return;
    lastSignature = null;
    /* force：编辑态也要能重绘，否则 startEdit 一按就再也画不出编辑框 */
    M.renderMessages(lastArgs[0], lastArgs[1], lastArgs[2], true);
  };
})();
