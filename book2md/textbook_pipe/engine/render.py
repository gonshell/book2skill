#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_formulas.js 的 Python 端驱动 + md2html 预渲染版

用法：python md2html.py [册名 ...]   （不带参数 = 全部 5 册）

单体化手段：
  - 图片全部 base64 内联
  - KaTeX CSS + woff2 字体内联；公式由 Node 端 KaTeX 预渲染成 HTML 嵌入
  - 成品不依赖任何 JS / 网络 / 外部文件，双击即看
"""
import base64, html, os, re, subprocess, sys, json, tempfile

# ------------------------------------------------------------- 搬迁说明（2026-10-24）
# 搬迁自 gzsx-md/md2html.py，行为保持型参数化（docs/conventions.md 附录 A）：
#   1) KaTeX 资产随包分发（assets/render_formulas.js + assets/katex/，保持原相对布局）
#   2) ROOT/final 常量 → convert(source_dir) / run(source_dir, out_dir) 参数注入
#   3) Node 预渲染临时文件改用系统临时目录；Node 失败由 sys.exit 改为抛异常
#   4) stdout 归 CLI 的 JSON 信封，进度/统计走 stderr
_ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
KATEX_DIR = os.path.join(_ASSETS, "katex")   # KaTeX 0.16.11 快照（docs/install.md 锁定表）
NODE = "node"
RENDER_JS = os.path.join(_ASSETS, "render_formulas.js")
_SRC_DIR = None   # 运行时注入：final 目录（含 <book>/markdown.md 与 images/），convert() 设置
BOOKS = ["必修第一册", "必修第二册", "选择性必修第一册", "选择性必修第二册", "选择性必修第三册"]

IMG_RE = re.compile(r"!\[[^\]]*\]\(\s*([^)\s]+)\s*\)")
MATH_SPLIT = re.compile(r"(\$\$[^\n]+?\$\$|\$[^$\n]+?\$)")
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*)$")
TOC_RE = re.compile(r"^(第[0-9一二三四五六七八九十]+章\S*|\d+\.\d+\s*\S*|习题[\d.]+|复习参考题\s*\S*|小结\S*|数学建模\S*)")
PAGE_SEP_RE = re.compile(r"<!--\s*=+\s*原书物理页\s*(\d+)\s*-\s*(\d+)(?:\s*·\s*教材页码\s*([^\s]+))?\s*=+\s*-->")
ALT_RE = re.compile(r"^<!--\s*alt:\s*(.*?)\s*-->$")
BLANK_GIF = ("data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")

MISSING_IMGS = []
MATH = {}          # token -> (latex, display)
MATH_ORDER = []    # token 顺序


def tok(latex, display):
    t = "@@M%d@@" % len(MATH_ORDER)
    MATH[t] = (latex, display)
    MATH_ORDER.append(t)
    return t


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def embed_img(rel, cache, book):
    if rel in cache:
        return cache[rel]
    p = os.path.join(_SRC_DIR, book, rel)
    if os.path.exists(p):
        ext = os.path.splitext(p)[1].lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        b64 = base64.b64encode(open(p, "rb").read()).decode()
        tag = '<img alt="%s" src="data:%s;base64,%s" loading="lazy" />' % (
            html.escape(os.path.basename(rel), quote=True), mime, b64)
    else:
        MISSING_IMGS.append((book, rel))
        tag = '<img alt="图片缺失：%s" src="%s" />' % (html.escape(rel, quote=True), BLANK_GIF)
    cache[rel] = tag
    return tag


# 教材抽取产物中的原生行内标签白名单：上标/下标/下划线，均为无属性的纯语义标签。
# 曾对正文整体 esc，导致 <sup>②</sup> 一类原样露出成可见文本（化学书 74 处）。
# 只放行这三种严格形态，避免误伤数学里的 < > 比较运算（如 $a<b$）。
_SAFE_TAG_RE = re.compile(r"</?(?:sup|sub|u)>")


def prose_inline(seg, cache, book):
    keep = []

    def _stash(m):
        keep.append(m.group(0))
        return "@@H%d@@" % (len(keep) - 1)

    seg = _SAFE_TAG_RE.sub(_stash, seg)
    out, pos = [], 0
    for m in IMG_RE.finditer(seg):
        out.append(esc(seg[pos:m.start()]))
        out.append(embed_img(m.group(1), cache, book))
        pos = m.end()
    out.append(esc(seg[pos:]))
    s = "".join(out)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = s.replace("\\*", "*").replace("\\%", "%")
    if keep:
        s = re.sub(r"@@H(\d+)@@", lambda m: keep[int(m.group(1))], s)
    return s


def inline_html(text, cache, book):
    """数学段 → 预渲染令牌；其余转义 + 行内语法"""
    parts = []
    for seg in MATH_SPLIT.split(text):
        if not seg:
            continue
        if seg.startswith("$$"):
            parts.append(tok(seg[2:-2], True))
        elif seg.startswith("$"):
            parts.append(tok(seg[1:-1], False))
        else:
            parts.append(prose_inline(seg, cache, book))
    return "".join(parts)


# ---------------- 表格（数学感知的竖线切分） ----------------
def split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    cells, buf, in_math = [], "", False
    for c in s:
        if c == "$":
            in_math = not in_math
            buf += c
        elif c == "|" and not in_math:
            cells.append(buf)
            buf = ""
        else:
            buf += c
    cells.append(buf)
    return [c.strip() for c in cells]


def is_sep_row(cells):
    return len(cells) > 0 and all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c != "")


def table_html(rows, cache, book):
    has_head = len(rows) >= 2 and is_sep_row(rows[1])
    body_rows = rows[2:] if has_head else rows
    out = ["<table>"]
    if has_head:
        out.append("<thead><tr>")
        for c in rows[0]:
            out.append("<th>%s</th>" % inline_html(c, cache, book))
        out.append("</tr></thead>")
    out.append("<tbody>")
    for r in body_rows:
        out.append("<tr>")
        for c in r:
            out.append("<td>%s</td>" % inline_html(c, cache, book))
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


# ---------------- KaTeX CSS（字体内联） ----------------
def load_katex_css():
    css = open(os.path.join(KATEX_DIR, "katex.min.css"), encoding="utf-8").read()
    css = re.sub(r",url\(fonts/[A-Za-z0-9._-]+\.woff\) format\(\"woff\"\)", "", css)
    css = re.sub(r",url\(fonts/[A-Za-z0-9._-]+\.ttf\) format\(\"truetype\"\)", "", css)

    def _font(m):
        # m.group(1) 已含 "fonts/" 前缀，直接拼 KATEX_DIR；
        # 曾误写成 join(KATEX_DIR, "fonts", m.group(1)) → katex/fonts/fonts/... 双前缀，
        # 文件不存在导致 20 个 @font-face 全部没内联（HTML 实际非自包含）
        p = os.path.join(KATEX_DIR, m.group(1))
        if not os.path.exists(p):
            return m.group(0)
        return "url(data:font/woff2;base64,%s)" % base64.b64encode(open(p, "rb").read()).decode()
    return re.sub(r"url\((fonts/[A-Za-z0-9._-]+\.woff2)\)", _font, css)


CSS = """
:root{--ink:#1c1a17;--paper:#faf7f0;--card:#ffffff;--line:#e3ddd0;--accent:#8a5a2b;--muted:#8b8577}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:"Songti SC","STSong","Noto Serif CJK SC","Source Han Serif SC","SimSun",serif;
  font-size:17px;line-height:1.95;-webkit-font-smoothing:antialiased}
.page{max-width:880px;margin:0 auto;padding:48px 40px 120px;background:var(--card);
  box-shadow:0 0 24px rgba(60,50,30,.08);min-height:100vh}
header.bk{border-bottom:3px double var(--line);padding-bottom:22px;margin-bottom:10px}
header.bk .kicker{font-size:13px;letter-spacing:.35em;color:var(--muted)}
header.bk h1{font-size:30px;margin:8px 0 4px;letter-spacing:.06em}
header.bk .sub{font-size:13px;color:var(--muted)}
nav.toc{background:#f6f1e6;border:1px solid var(--line);border-radius:10px;
  padding:14px 20px;margin:18px 0 40px}
nav.toc summary{cursor:pointer;font-size:15px;font-weight:700;letter-spacing:.15em;color:var(--accent)}
nav.toc ol{margin:12px 0 4px;columns:2;column-gap:36px;padding-left:1.6em;font-size:14px;line-height:2}
nav.toc a{color:var(--ink);text-decoration:none;border-bottom:1px dotted #c9bfa8}
nav.toc a:hover{color:var(--accent)}
h1,h2,h3,h4{line-height:1.5;letter-spacing:.02em}
h2{font-size:23px;margin:64px 0 18px;padding-bottom:8px;border-bottom:1px solid var(--line)}
h2::before{content:"§ ";color:var(--accent);font-weight:400}
h3{font-size:19px;margin:36px 0 12px}
h3::before{content:"◆ ";color:var(--accent);font-size:.7em;vertical-align:2px}
h4{font-size:17px;margin:24px 0 8px}
p{margin:14px 0;text-align:justify}
ul,ol{padding-left:1.8em;margin:12px 0}
li{margin:6px 0}
strong{font-weight:700}
.page-marker{text-align:center;font-size:12px;color:#b3ac9c;letter-spacing:.3em;
  margin:56px 0 40px;display:flex;align-items:center;gap:14px}
.page-marker::before,.page-marker::after{content:"";flex:1;border-top:1px dashed #d8d0bd}
img{max-width:100%;height:auto;display:block;margin:18px auto;border-radius:2px}
figure{margin:26px 0;text-align:center}
.formula{margin:22px 0;padding:6px 4px;text-align:center;overflow-x:auto;overflow-y:hidden}
.formula .katex-display{margin:0}
.katex{font-size:1.06em}
.katex-display{overflow-x:auto;overflow-y:hidden;padding:2px 0}
table{border-collapse:collapse;width:100%;margin:22px 0;font-size:15px;line-height:1.7}
th,td{border:1px solid var(--line);padding:9px 12px;text-align:center;vertical-align:middle}
th{background:#f3edde;font-weight:700}
tbody tr:nth-child(even){background:#fbf9f3}
td:empty{height:2.4em}
pre.code{margin:18px 0;padding:13px 18px;background:#f6f4ee;border:1px solid var(--line);
  border-left:3px solid var(--accent);border-radius:4px;font-family:Consolas,"Courier New",monospace;
  font-size:13.5px;line-height:1.75;overflow-x:auto;white-space:pre;color:#3a3630}
footer.bk{margin-top:90px;padding-top:18px;border-top:1px solid var(--line);
  font-size:12px;color:var(--muted);text-align:center;letter-spacing:.2em}
a.top{position:fixed;right:26px;bottom:26px;width:42px;height:42px;border-radius:50%;
  background:var(--accent);color:#fff;text-decoration:none;display:flex;align-items:center;
  justify-content:center;font-size:20px;box-shadow:0 3px 10px rgba(0,0,0,.25);opacity:.85}
a.top:hover{opacity:1}
@media print{
  body{background:#fff}.page{box-shadow:none;max-width:none;padding:0}
  nav.toc,a.top{display:none}h2{page-break-after:avoid}
  .formula,table,img{page-break-inside:avoid}
}
@media (max-width:640px){.page{padding:26px 16px 80px}nav.toc ol{columns:1}body{font-size:16px}}
"""

# 知识库版样式：白底、中性色、无纸质感、无装饰，便于嵌入知识库与打印。
# 与阅读版的区别不只是配色——.kb-alt（公式线性文本）只在此版出现。
KB_CSS = """
:root{--ink:#1f2328;--muted:#57606a;--line:#d0d7de;--accent:#0969da;--card:#f6f8fa}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:#fff;color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans CJK SC","PingFang SC","Microsoft YaHei",sans-serif;
  font-size:16px;line-height:1.78;-webkit-font-smoothing:antialiased}
.page{max-width:880px;margin:0 auto;padding:26px 22px 70px}
header.bk{border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:20px}
.kicker{font-size:12px;letter-spacing:.16em;color:var(--muted)}
h1{font-size:25px;margin:6px 0 4px;font-weight:700}
.sub{font-size:12.5px;color:var(--muted)}
h2{font-size:20px;margin:32px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--line);font-weight:650}
h3{font-size:17px;margin:24px 0 10px;font-weight:650}
h4{font-size:15.5px;margin:18px 0 8px;font-weight:650}
p{margin:10px 0}
.formula{margin:14px 0;padding:10px 8px;background:var(--card);border:1px solid var(--line);
  border-radius:6px;overflow-x:auto;text-align:center}
.kb-alt{margin:1px 0 16px;font-size:12px;line-height:1.55;color:var(--muted);text-align:center;
  font-family:ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",monospace;word-break:break-all}
.kb-alt::before{content:"⌖ ";opacity:.5}
img{max-width:100%;height:auto;border:1px solid var(--line);border-radius:4px}
figure{margin:16px 0;text-align:center}
figcaption{font-size:12.5px;color:var(--muted);margin-top:6px}
table{border-collapse:collapse;width:100%;margin:14px 0;font-size:14.5px;display:block;overflow-x:auto}
th,td{border:1px solid var(--line);padding:6px 10px;text-align:left}
th{background:var(--card);font-weight:650}
nav.toc{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 16px;margin-bottom:22px}
nav.toc summary{cursor:pointer;font-size:14px;font-weight:700;color:var(--accent)}
nav.toc ol{margin:10px 0 4px;columns:2;column-gap:28px;padding-left:1.5em;font-size:13.5px;line-height:1.95}
nav.toc a{color:var(--ink);text-decoration:none}
nav.toc a:hover{color:var(--accent);text-decoration:underline}
pre.code{margin:14px 0;padding:12px 14px;background:var(--card);border:1px solid var(--line);border-radius:6px;
  font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:13px;line-height:1.65;
  overflow-x:auto;white-space:pre}
a.top{display:none}
footer.bk{border-top:1px solid var(--line);margin-top:34px;padding-top:12px;
  font-size:12.5px;color:var(--muted);text-align:center}
@media (max-width:640px){.page{padding:16px 12px 48px}nav.toc ol{columns:1}}
@media print{body{background:#fff}.page{max-width:none;padding:0}nav.toc,a.top{display:none}
  h2{page-break-after:avoid}.formula,table,img{page-break-inside:avoid}.kb-alt{display:none}}
"""


def _kb_alt_clean(t):
    """KB 可见公式文本清理：去环境前缀（{aligned} 等）与对齐/行止符。
    只作用于 KB 版的可见小字；title 属性保留原始线性文本不改。"""
    t = re.sub(r"^\{[a-z]+\*?\}", "", t)        # {aligned} {cases} {array} {gathered}
    t = t.replace("\\\\&", " ").replace("\\\\", " ")   # \\& 对齐列分隔、\\ 行止
    t = t.replace("&", " ").replace("~", " ")
    return re.sub(r"\s{2,}", " ", t).strip()


def convert(book, variant="reader", source_dir=None):
    """variant: "reader" = 纸质阅读版；"kb" = 知识库版
    KB 版差异：① alt 转可见小字（防知识库导入时丢 HTML 注释，且可被全文检索）
              ② 去页码分隔线（原书页码映射保留在 page_map.md）
              ③ 白底中性样式，便于嵌入知识库 / 打印"""
    global _SRC_DIR
    if source_dir is None:
        raise ValueError("convert 需要 source_dir（由 run() 注入 final 目录）")
    _SRC_DIR = source_dir
    src = os.path.join(source_dir, book, "markdown.md")
    lines = open(src, encoding="utf-8").read().replace("\r\n", "\n").split("\n")
    imgcache = {}
    body = []
    toc = []
    stats = {"img": 0, "formula": 0, "table": 0, "heading": 0, "page": 0, "code": 0}

    para, lst, tbl = [], [], []

    def flush_para():
        if para:
            body.append("<p>%s</p>" % inline_html(" ".join(para), imgcache, book))
            para.clear()

    def flush_list():
        if lst:
            ordered, start = lst[0][0], lst[0][1]
            tag = "ol" if ordered else "ul"
            attr = ' start="%d"' % start if ordered and start != 1 else ""
            items = "".join("<li>%s</li>" % inline_html(t, imgcache, book) for _, _, t in lst)
            body.append("<%s%s>%s</%s>" % (tag, attr, items, tag))
            lst.clear()

    def flush_table():
        if tbl:
            stats["table"] += 1
            body.append(table_html(tbl, imgcache, book))
            tbl.clear()

    def flush_all():
        flush_para(); flush_list(); flush_table()

    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()

        if not s:
            flush_all(); i += 1; continue

        # —— 块公式 $$ … $$ ——
        if s == "$$":
            j = i + 1
            while j < n and lines[j].strip() != "$$":
                j += 1
            content = "\n".join(l.strip() for l in lines[i + 1:j] if l.strip())
            stats["formula"] += 1
            body.append('<div class="formula">%s</div>' % tok(content, True))
            i = j + 1
            continue
        m = re.fullmatch(r"\$\$(.+)\$\$", s)
        if m:
            stats["formula"] += 1
            body.append('<div class="formula">%s</div>' % tok(m.group(1), True))
            i += 1
            continue

        # —— 代码围栏（R 语言输出等程序输出）→ 等宽代码块 ——
        if s.startswith("```"):
            j = i + 1
            frows = []
            while j < n and not lines[j].strip().startswith("```"):
                frows.append(lines[j].rstrip())
                j += 1
            if any(r.strip() for r in frows):
                stats["code"] += 1
                body.append('<pre class="code">%s</pre>' % "\n".join(esc(r) for r in frows))
            i = j + 1
            continue

        # —— 表格行 ——
        if s.startswith("|"):
            flush_para(); flush_list()
            tbl.append(split_row(s))
            i += 1
            continue
        flush_table()

        # —— 标题 ——
        m = HEAD_RE.match(s)
        if m:
            flush_para(); flush_list()
            level = len(m.group(1))
            text = m.group(2).strip()
            stats["heading"] += 1
            hid = "h%d" % stats["heading"]
            if level <= 2 and TOC_RE.match(text):
                toc.append((hid, text))
            body.append("<h%d id=\"%s\">%s</h%d>" % (level, hid, inline_html(text, imgcache, book), level))
            i += 1
            continue

        # —— 块分隔注释 → 原书页码标记 ——
        m = PAGE_SEP_RE.search(s)
        if m:
            if variant == "kb":
                i += 1          # KB 版：页码分隔线整体跳过
                continue
            flush_all()
            a, b, tp = m.group(1), m.group(2), m.group(3)
            label = "原书第 %s–%s 页" % (a, b)
            if tp and not tp.startswith("None"):
                label += " · 教材页 %s" % tp
            body.append('<div class="page-marker">%s</div>' % label)
            stats["page"] += 1
            i += 1
            continue

        # —— alt 注释：挂到上一条公式 ——
        m = ALT_RE.match(s)
        if m:
            for k in range(len(body) - 1, -1, -1):
                if 'class="formula"' in body[k]:
                    alt = html.escape(m.group(1), quote=True)
                    body[k] = body[k].replace('<div class="formula"',
                                              '<div class="formula" title="%s"' % alt, 1)
                    if variant == "kb":
                        # KB 版：公式线性文本转可见小字。HTML 注释在知识库导入时
                        # 常被整段丢弃，只有可见文本能进全文检索索引
                        body.append('<p class="kb-alt">%s</p>'
                                    % html.escape(_kb_alt_clean(m.group(1)), quote=True))
                    break
            i += 1
            continue
        if s.startswith("<!--"):
            i += 1
            continue

        # —— 图片独占行 → figure ——
        if IMG_RE.fullmatch(s):
            flush_all()
            body.append("<figure>%s</figure>" % embed_img(IMG_RE.match(s).group(1), imgcache, book))
            i += 1
            continue

        # —— 列表 ——
        m = re.match(r"^[-*]\s+(.*)$", s)
        if m:
            flush_para()
            if lst and lst[-1][0]:
                flush_list()
            lst.append((False, 1, m.group(1)))
            i += 1
            continue
        m = re.match(r"^(\d{1,2})[.、]\s*(.*)$", s)
        if m:
            flush_para()
            num = int(m.group(1))
            if lst and not lst[-1][0]:
                flush_list()
            if lst and num != lst[-1][1] + 1 and len(lst) > 1:
                flush_list()
            if not lst:
                start = num
            lst.append((True, num, m.group(2)))
            i += 1
            continue
        # 列表续行
        if lst and not tbl:
            lst[-1] = (lst[-1][0], lst[-1][1], lst[-1][2] + " " + s)
            i += 1
            continue

        # —— 普通段落行 ——
        flush_list()
        para.append(s)
        i += 1

    flush_all()
    stats["img"] = len(imgcache)

    toc_html = ""
    if toc:
        # 目录条目同样过 inline_html——标题里的公式要渲染（曾用 esc() 导致
        # "5.6.2 函数 $y=A\sin(\omega x+\varphi)$ 的图象" 在目录里显示裸 LaTeX）
        items = "".join('<li><a href="#%s">%s</a></li>' % (hid, inline_html(t, imgcache, book))
                        for hid, t in toc)
        toc_html = ('<nav class="toc"><details open><summary>目 录</summary>'
                    "<ol>%s</ol></details></nav>" % items)

    css = load_katex_css()
    doc = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s · 人教 A 版数学</title>
<style>%(css)s
%(bookcss)s</style>
</head>
<body>
<a class="top" href="#" title="回到顶部">↑</a>
<div class="page">
<header class="bk">
  <div class="kicker">人教 A 版 · 普通高中教科书 · 数学</div>
  <h1>%(title)s</h1>
  <div class="sub">%(chars)s 字符 · %(img)d 幅插图 · %(formula)d 个公式 · %(flavor)s</div>
</header>
%(toc)s
<main>
%(body)s
</main>
<footer class="bk">— 全书完 —</footer>
</div>
</body>
</html>
""" % {
        "title": book, "css": css,
        "bookcss": KB_CSS if variant == "kb" else CSS,
        "flavor": "知识库版 · 公式已预渲染" if variant == "kb" else "单体离线版",
        "toc": toc_html, "body": "\n".join(body),
        "chars": "{:,}".format(sum(len(x) for x in lines)),
        "img": stats["img"], "formula": stats["formula"],
    }
    return doc, stats


def render_all():
    """Node 端 KaTeX 预渲染当前 MATH 中的公式"""
    payload = {t: {"latex": lt, "display": d} for t, (lt, d) in MATH.items()}
    jin = os.path.join(tempfile.gettempdir(), "tbp_math_in.json")
    jout = os.path.join(tempfile.gettempdir(), "tbp_math_out.json")
    json.dump(payload, open(jin, "w", encoding="utf-8"), ensure_ascii=False)
    r = subprocess.run([NODE, RENDER_JS, jin, jout], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError("Node 渲染失败：%s" % r.stderr[:500])
    if r.stdout.strip():
        print("   " + r.stdout.strip(), file=sys.stderr)
    return json.load(open(jout, encoding="utf-8"))


def run(books=None, variant="reader", source_dir=None, out_dir=None):
    """行为保持版入口（自 main() 参数化）。

    source_dir: final 目录（含 <book>/markdown.md 与 <book>/images/）
    out_dir:    输出目录（写 <out_dir>/<book>.html，kb/reader 由 variant 区分）
    返回 {"missing": [(book, rel)…], "errors": [(book, latex)…], "out": {book: 路径}}；
    进度/统计走 stderr（stdout 留给 CLI 的 JSON 信封）。
    """
    books = books or BOOKS
    if not source_dir or not out_dir:
        raise ValueError("run() 需要 source_dir 与 out_dir（参数化注入）")
    os.makedirs(out_dir, exist_ok=True)
    print("转换目标：%s（%s）" % ("、".join(books),
                              "知识库版" if variant == "kb" else "阅读版"), file=sys.stderr)

    all_missing, all_errs, outs = [], [], {}
    for b in books:
        # 逐册流水线：解析 → 渲染 → 替换 → 落盘 → 释放，控制峰值内存
        doc, st = convert(b, variant, source_dir)
        print("[%s] 解析完成：图 %d · 公式 %d · 表 %d · 标题 %d · 页标 %d · 代码块 %d" % (
            b, st["img"], st["formula"], st["table"], st["heading"], st["page"], st["code"]), file=sys.stderr)
        rendered = render_all()
        errs = [t for t, v in rendered.items()
                if not v.get("ok") or "katex-error" in v.get("html", "")]
        for t in list(MATH):
            if t in doc:
                doc = doc.replace(t, rendered[t]["html"])
        out = os.path.join(out_dir, b + ".html")
        open(out, "w", encoding="utf-8").write(doc)
        outs[b] = out
        print("[%s] → %s  %.1f MB（公式 %d，渲染错误 %d）" % (
            b, os.path.basename(out), os.path.getsize(out) / 1048576.0,
            len(MATH), len(errs)), file=sys.stderr)
        for t in errs[:10]:
            print("   ERR %s → %s" % (t, MATH[t][0][:70]), file=sys.stderr)
        all_errs += [(b, MATH[t][0]) for t in errs]
        all_missing += [(b, r_) for r_ in MISSING_IMGS]
        MATH.clear()
        MATH_ORDER.clear()
        del doc, rendered

    for f in ("_math_in.json", "_math_out.json"):
        p = os.path.join(tempfile.gettempdir(), f)
        if os.path.exists(p):
            os.remove(p)

    if all_missing:
        print("!! 缺失图片 %d 处：" % len(all_missing), file=sys.stderr)
        for b, r_ in all_missing[:20]:
            print("   %s %s" % (b, r_), file=sys.stderr)
    else:
        print("图片引用全部命中，无缺失。", file=sys.stderr)
    if all_errs:
        print("!! KaTeX 渲染错误合计 %d 个（页面中以红色标出）：" % len(all_errs), file=sys.stderr)
        for b, lt in all_errs[:20]:
            print("   [%s] %s" % (b, lt[:70]), file=sys.stderr)
    else:
        print("KaTeX 全部渲染成功，0 错误。", file=sys.stderr)
    return {"missing": all_missing, "errors": all_errs, "out": outs}


if __name__ == "__main__":
    import argparse
    _p = argparse.ArgumentParser(description="双版本 HTML 渲染（tbp run 的内核）")
    _p.add_argument("--kb", action="store_true", help="知识库版（缺省为阅读版）")
    _p.add_argument("--source", required=True, help="final 目录（含 <book>/markdown.md）")
    _p.add_argument("--out", required=True, help="输出目录")
    _p.add_argument("books", nargs="*", help="册名列表，缺省为默认五册")
    _a = _p.parse_args()
    run(books=_a.books or None, variant="kb" if _a.kb else "reader",
        source_dir=_a.source, out_dir=_a.out)
