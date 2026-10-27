// render_formulas.js — KaTeX 服务端预渲染（供 md2html.py 调用）
// 用法：node render_formulas.js <in.json> <out.json>
// in : {"@@M0@@": {"latex": "...", "display": false}, ...}
// out: {"@@M0@@": {"ok": true, "html": "<span class=\"katex\">…"}, ...}
const fs = require("fs");
const path = require("path");
const katex = require(path.join(__dirname, "katex", "katex.min.js"));

const [inFile, outFile] = process.argv.slice(2);
const payload = JSON.parse(fs.readFileSync(inFile, "utf8"));
const out = {};
let ok = 0, bad = 0;

for (const [token, item] of Object.entries(payload)) {
  const latex = item.latex;
  const display = !!item.display;
  try {
    const htmlStr = katex.renderToString(latex, {
      displayMode: display,
      throwOnError: false,
      strict: false,
      output: "html",
      trust: false,
    });
    const isErr = /katex-error/.test(htmlStr);
    out[token] = { ok: !isErr, html: htmlStr };
    isErr ? bad++ : ok++;
  } catch (e) {
    out[token] = { ok: false, html: '<span class="math-err">' +
      String(e.message || e).replace(/</g, "&lt;") + "</span>" };
    bad++;
  }
}
fs.writeFileSync(outFile, JSON.stringify(out));
console.log("KaTeX 渲染完成：成功 " + ok + "，失败 " + bad);
