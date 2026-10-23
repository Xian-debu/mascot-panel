/* 代码块语法高亮（M42）：自写轻量分词器，不引入 highlight.js
   （面板 HTML 要内联全部资源，多一个 200KB 的包不划算）。
   支持 python/js/ts/json/bash/sql/c/cpp/rust/go/java/yaml/toml/css/html 等常见语言，
   未知语言退回纯文本。输出 <span class="hl-xx">，全程 textContent，不拼 innerHTML。 */
(function () {
  const M = (window.Mascot = window.Mascot || {});
  /* 反引号刻意用码点拼，避免本文件被模板字符串/转义规则影响 */
  const BT = String.fromCharCode(96);

  const KEYWORDS = {
    python:
      'and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield match case',
    js: 'async await break case catch class const continue debugger default delete do else export extends false finally for from function if import in instanceof let new null of return static super switch this throw true try typeof undefined var void while yield',
    ts: 'abstract any as async await boolean break case catch class const constructor continue declare default delete do else enum export extends false finally for from function if implements import in instanceof interface let namespace new null number of private protected public readonly return static string super switch this this throw true try type typeof undefined var void while yield',
    json: 'true false null',
    bash: 'break case cd continue do done echo elif else esac eval exec exit export false fi for function if in local printf read return set shift source then time trap true unset until while',
    sql: 'add all alter and as asc avg by case cast count create delete desc distinct drop else end exists from group having in index inner insert into is join key left like limit max min not null offset on or order outer primary references right select set sum table then union unique update values view when where',
    c: 'auto break case char const continue default do double else enum extern float for goto if inline int long register restrict return short signed sizeof static struct switch typedef union unsigned void volatile while',
    cpp: 'auto bool break case catch char class const constexpr continue default delete do double else enum explicit extern false float for friend goto if inline int long namespace new noexcept nullptr operator private protected public return short signed sizeof static struct switch template this throw true try typedef typename union unsigned using virtual void volatile while',
    rust: 'as async await break const continue crate dyn else enum extern false fn for if impl in let loop match mod move mut pub ref return self static struct super trait true type unsafe use where while',
    go: 'break case chan const continue default defer else fallthrough for func go goto if import interface map nil package range return select struct switch true false type var',
    java: 'abstract boolean break byte case catch char class const continue default do double else enum extends final finally float for if implements import int interface long new null private protected public static return short super switch this throw throws try void volatile while',
  };

  /* [注释风格, 关键字组]；注释风格：hash / slash / dash / css / html */
  const LANGS = {
    python: ['hash', 'python'], py: ['hash', 'python'], python3: ['hash', 'python'], py3: ['hash', 'python'],
    js: ['slash', 'js'], javascript: ['slash', 'js'], jsx: ['slash', 'js'], node: ['slash', 'js'], mjs: ['slash', 'js'],
    ts: ['slash', 'ts'], typescript: ['slash', 'ts'], tsx: ['slash', 'ts'],
    json: ['slash', 'json'], json5: ['slash', 'json'],
    bash: ['hash', 'bash'], sh: ['hash', 'bash'], shell: ['hash', 'bash'], zsh: ['hash', 'bash'], console: ['hash', 'bash'],
    sql: ['dash', 'sql'], mysql: ['dash', 'sql'], psql: ['dash', 'sql'], sqlite: ['dash', 'sql'],
    c: ['slash', 'c'], h: ['slash', 'c'],
    cpp: ['slash', 'cpp'], 'c++': ['slash', 'cpp'], cc: ['slash', 'cpp'], hpp: ['slash', 'cpp'], cxx: ['slash', 'cpp'],
    rust: ['slash', 'rust'], rs: ['slash', 'rust'],
    go: ['slash', 'go'], golang: ['slash', 'go'],
    java: ['slash', 'java'], cs: ['slash', 'java'], csharp: ['slash', 'java'], kt: ['slash', 'java'], kotlin: ['slash', 'java'], swift: ['slash', 'java'], scala: ['slash', 'java'],
    yaml: ['hash', ''], yml: ['hash', ''], toml: ['hash', ''], ini: ['hash', ''], conf: ['hash', ''], dotenv: ['hash', ''],
    dockerfile: ['hash', ''], makefile: ['hash', ''], mk: ['hash', ''],
    css: ['css', ''], scss: ['css', ''], less: ['css', ''],
    html: ['html', ''], xml: ['html', ''], svg: ['html', ''], vue: ['html', ''],
  };

  const RE_WS = /[ \t]+/y;
  const RE_NUM = /(?:0[xX][0-9a-fA-F_]+|\d[\d_]*(?:\.[\d_]+)?(?:[eE][+-]?\d+)?)/y;
  const RE_ID = /[A-Za-z_$][\w$]*/y;
  const RE_PUNCT = /[^\sA-Za-z0-9_$]+/y;
  const RE_TAG = /<\/?[A-Za-z][\w:-]*|\/?>/y;

  function scan(code, family, kwName) {
    const out = [];
    const kws = KEYWORDS[kwName] ? new Set(KEYWORDS[kwName].split(' ')) : null;
    let plain = '';
    let i = 0;
    function push(txt, cls) {
      if (plain) { out.push([plain, '']); plain = ''; }
      if (txt) { out.push([txt, cls || '']); }
    }
    function toEol(from) {
      const j = code.indexOf('\n', from);
      return j < 0 ? code.length : j;
    }
    while (i < code.length) {
      const c = code.charAt(i);
      if (family === 'html') {
        if (code.startsWith('<!--', i)) {
          const j = code.indexOf('-->', i + 4);
          const e = j < 0 ? code.length : j + 3;
          push(code.slice(i, e), 'com'); i = e; continue;
        }
        RE_TAG.lastIndex = i;
        const tm = RE_TAG.exec(code);
        if (tm) { push(tm[0], 'kw'); i += tm[0].length; continue; }
      }
      if (family === 'slash' && code.startsWith('/*', i)) {
        const j = code.indexOf('*/', i + 2);
        const e = j < 0 ? code.length : j + 2;
        push(code.slice(i, e), 'com'); i = e; continue;
      }
      if (family === 'css' && code.startsWith('/*', i)) {
        const j = code.indexOf('*/', i + 2);
        const e = j < 0 ? code.length : j + 2;
        push(code.slice(i, e), 'com'); i = e; continue;
      }
      if (family === 'slash' && code.startsWith('//', i)) { const e = toEol(i); push(code.slice(i, e), 'com'); i = e; continue; }
      if (family === 'dash' && code.startsWith('--', i)) { const e = toEol(i); push(code.slice(i, e), 'com'); i = e; continue; }
      if ((family === 'hash' || family === 'bashish') && c === '#') { const e = toEol(i); push(code.slice(i, e), 'com'); i = e; continue; }
      if (family === 'hash' && c === '#') { const e = toEol(i); push(code.slice(i, e), 'com'); i = e; continue; }
      if (c === '"' || c === "'" || c === BT) {
        let j = i + 1;
        while (j < code.length) {
          const d = code.charAt(j);
          if (d === '\\') { j += 2; continue; }
          if (d === c) { j += 1; break; }
          if (d === '\n' && c !== BT) { break; }
          j += 1;
        }
        if (j > code.length) { j = code.length; }
        push(code.slice(i, j), 'str'); i = j; continue;
      }
      RE_WS.lastIndex = i;
      const wm = RE_WS.exec(code);
      if (wm) { plain += wm[0]; i += wm[0].length; continue; }
      if (c >= '0' && c <= '9') {
        RE_NUM.lastIndex = i;
        const nm = RE_NUM.exec(code);
        if (nm) { push(nm[0], 'num'); i += nm[0].length; continue; }
      }
      RE_ID.lastIndex = i;
      const im = RE_ID.exec(code);
      if (im) {
        const word = im[0];
        let cls = '';
        if (kws && kws.has(word)) { cls = 'kw'; }
        else if (code.charAt(i + word.length) === '(') { cls = 'fn'; }
        push(word, cls); i += word.length; continue;
      }
      RE_PUNCT.lastIndex = i;
      const pm = RE_PUNCT.exec(code);
      if (pm) { push(pm[0], 'op'); i += pm[0].length; continue; }
      plain += c; i += 1;
    }
    if (plain) { out.push([plain, '']); }
    return out;
  }

  /* 归一化语言名：只认我们认识的那些，其余返回 ''（调用方按纯文本处理）。 */
  M.highlightLang = function (raw) {
    const s = String(raw || '').trim().toLowerCase();
    return Object.prototype.hasOwnProperty.call(LANGS, s) ? s : '';
  };

  /* 把 code 高亮写进 el；返回是否真的高亮（false = 调用方自己填 textContent）。 */
  M.highlightInto = function (el, code, lang) {
    const name = M.highlightLang(lang);
    if (!name) { return false; }
    const spec = LANGS[name];
    const toks = scan(String(code == null ? '' : code), spec[0], spec[1]);
    const frag = document.createDocumentFragment();
    for (let k = 0; k < toks.length; k += 1) {
      const t = toks[k];
      if (!t[1]) { frag.appendChild(document.createTextNode(t[0])); continue; }
      const sp = document.createElement('span');
      sp.className = 'hl-' + t[1];
      sp.textContent = t[0];
      frag.appendChild(sp);
    }
    el.textContent = '';
    el.appendChild(frag);
    return true;
  };
})();
