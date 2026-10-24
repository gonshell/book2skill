# -*- coding: utf-8 -*-
"""scan3.py — 发现手段套件（2026-10-22 两轮用户截图报告后持续扩充）

覆盖结构校验与模式扫描的盲区：
  D1 退化重复检测：同 token 连续重复（跨行口径）——OCR 模型崩溃的指纹
  D2 数集记号词典：N/Z/Q/R/C 标准下标白名单之外的字符
  D3 符号误识专项：\\oint（环积分）、补集记号 \\int_{U}/\\mathbb{C}、\\textless/\\textgreater
  D4 图片完整性：引用可达、image/chart 裁片零遗漏、JPEG 结构有效
  D5 渲染完整性三项：行内游离 $$、奇数 $ 行、块内奇数 $
  D6 水印图检测（内容级）：灰度墨量 <1% 且饱和度 <2% 且（宽高比>3 或面积<6万像素）
     ——图存在、引用正常，但图里只有人教社水印（引用完整性检查查不出）
  D7 HTML 标签/实体泄漏：<table>/<td>/<div>/<span>、&gt;/&lt;/&amp;
  D8 \\quad\\text 退化垃圾：连续 >=5 个 \\quad \\text{N}
  D9 小节图标裸引用：紧跟 复习巩固/综合运用/拓广探索 标题但无 alt 的图片
"""
import os
import re
import sys

_SRC_DIR = None   # 运行时注入：final 目录（scan()/run() 设置）
BOOKS = ["必修第一册", "必修第二册", "选择性必修第一册", "选择性必修第二册", "选择性必修第三册"]
HAN = "".join(chr(c) for c in range(0x4E00, 0x9FA5))


def p(*a):
    print(*a, file=sys.stderr)  # 报告走 stderr（stdout 归 CLI JSON 信封）

def d1(md, book):
    """退化重复：同一 token 在单个公式段内部连续重复 >= 10 次（OCR 模型崩溃的指纹）。
    跨公式的重复（如列表里多个 $x\\in\\mathbb{R}$）合法，不计；
    公式内合法枚举（样本空间、组合数列表）最多约 8 次，故阈值取 10。"""
    hits = []
    tok = re.compile(r"\\(?:text|mathrm)\s*\{\s*([^{}]{1,6})\s*\}")
    spans = [(m.start(), m.group(0)) for m in re.finditer(r"\$\$[^$]*?\$\$", md, re.S)]
    spans += [(m.start(), m.group(0)) for m in re.finditer(r"\$[^$\n]+\$", md)]
    for pos, sp in spans:
        toks = [m.group(1) for m in tok.finditer(sp)]
        if len(toks) < 10:
            continue
        run = best = 1
        for k in range(1, len(toks)):
            run = run + 1 if toks[k] == toks[k-1] else 1
            best = max(best, run)
        if best >= 10:
            ln = md[:pos].count("\n") + 1
            hits.append("%s L%d：公式段内 %r 连续重复 %d 次（共 %d token）"
                        % (book, ln, toks[0], best, len(toks)))
    return hits


def d2(md, book):
    hits = []
    pat = re.compile(r"\\(?:mathbf|mathbb)\s*\{\s*([A-Z])\s*(\*|\+)?\s*\}\s*_\s*\{([^{}]*)\}")
    VALID = {"N": {"*", "+", ""}, "Z": {"", "-", "+"}, "Q": {"", "+", "-"},
             "R": {"", "+", "-"}, "C": {""}}
    for i, ln in enumerate(md.split("\n"), 1):
        for m in pat.finditer(ln):
            letter, sub = m.group(1), m.group(3)
            if re.search("[" + HAN + "]", sub) or (letter in VALID and sub.strip() not in VALID[letter]):
                hits.append("%s L%d：...%s..." % (book, i, ln.strip()[max(0, m.start()-30):m.end()+20]))
    return hits


def d3(md, book):
    hits = []
    for i, ln in enumerate(md.split("\n"), 1):
        if "\\oint" in ln:
            hits.append("%s L%d：\\oint 环积分误识: %s" % (book, i, ln.strip()[:100]))
        for m in re.finditer(r"\\int\s*_\s*\{?\s*U\s*\}?|\\mathbb\s*\{\s*C\s*\}", ln):
            hits.append("%s L%d：补集记号误识: %s" % (book, i, ln.strip()[:100]))
        if "\\textless" in ln or "\\textgreater" in ln:
            hits.append("%s L%d：\\textless/\\textgreater 兼容性: %s" % (book, i, ln.strip()[:100]))
    return hits


def d4(book):
    hits = []
    d = os.path.join(_SRC_DIR, book, "images")
    md = open(os.path.join(_SRC_DIR, book, "markdown.md"), encoding="utf-8").read()
    refs = re.findall(r"!\[[^\]]*\]\(\s*([^)\s]+)\s*\)", md)
    missing = [r for r in refs if not os.path.exists(os.path.join(_SRC_DIR, book, r))]
    if missing:
        hits.append("%s：图片引用缺失 %d 处: %s" % (book, len(missing), missing[:5]))
    if os.path.isdir(d):
        files = set(os.listdir(d))
        refset = set(os.path.basename(r) for r in refs)
        fig_unref = sorted(f for f in files - refset if re.match(r"page_\d+_(image|chart)_", f))
        if fig_unref:
            hits.append("%s：真图/图表裁片未被引用 %d 个: %s" % (book, len(fig_unref), fig_unref[:5]))
    return hits


def d5(md, book):
    hits = []
    lines = md.split("\n")
    for i, ln in enumerate(lines, 1):
        if "$$" in ln and ln.strip() != "$$":
            hits.append("%s L%d：行内游离 $$" % (book, i))
    inblk = False
    for i, ln in enumerate(lines, 1):
        if ln.strip() == "$$":
            inblk = not inblk
        elif inblk and ln.count("$") % 2 == 1:
            hits.append("%s L%d：块内奇数 $" % (book, i))
    for i, ln in enumerate(lines, 1):
        if ln.strip() != "$$" and ln.count("$") % 2 == 1:
            hits.append("%s L%d：奇数 $ 行" % (book, i))
    return hits


def d6(book):
    """水印图：内容级检测（需 PIL）"""
    hits = []
    try:
        from PIL import Image
    except ImportError:
        return ["PIL 不可用，跳过 D6"]
    d = os.path.join(_SRC_DIR, book, "images")
    if not os.path.isdir(d):
        return hits
    for f in sorted(os.listdir(d)):
        fp = os.path.join(d, f)
        try:
            im = Image.open(fp).convert("RGB")
        except Exception:
            hits.append("%s：%s 解码失败" % (book, f))
            continue
        w, h = im.size
        small = im.resize((160, 60))
        px = list(small.getdata())
        n = len(px)
        ink = sum(1 for r, g, b in px if (r + g + b) / 3 < 200) / n
        if ink >= 0.01:
            continue
        sat = sum((0 if max(r, g, b) == 0 else (max(r, g, b) - min(r, g, b)) / max(r, g, b))
                  for r, g, b in px) / n
        if sat < 0.02 and (w / h > 3 or w * h < 60000):
            hits.append("%s：水印图 %s (%dx%d)" % (book, f, w, h))
    return hits


def d7(md, book):
    hits = []
    for i, ln in enumerate(md.split("\n"), 1):
        if re.search(r"<(?:table|tr|td|th|div|span|small)\b", ln):
            hits.append("%s L%d：HTML 标签泄漏: %s" % (book, i, ln.strip()[:100]))
        if re.search(r"&gt;|&lt;|&amp;|&quot;", ln):
            hits.append("%s L%d：HTML 实体残留: %s" % (book, i, ln.strip()[:100]))
    return hits


def d8(md, book):
    hits = []
    pat = re.compile(r"(?:\\quad\s*\\text\s*\{\s*[^{}]{1,6}\s*\}){5,}")
    for m in pat.finditer(md):
        ln = md[:m.start()].count("\n") + 1
        hits.append("%s L%d：\\quad\\text 退化垃圾 长=%d" % (book, ln, len(m.group(0))))
    return hits


def d9(md, book):
    """小节图标裸引用：紧跟 复习巩固/综合运用/拓广探索 标题但无 alt 的图片。
    注意：真插图也可能排在类别标题前（如习题末图），故只 flag <100px 的小图
    （页边图标全部 <=72px，真插图最小约 145px，间隔明确）。"""
    hits = []
    lines = md.split("\n")
    imgdir = os.path.join(_SRC_DIR, book, "images")
    for i in range(len(lines)):
        m = re.fullmatch(r"!\[\]\(images/([^)]+)\)", lines[i].strip())
        if not m:
            continue
        fp = os.path.join(imgdir, m.group(1))
        tiny = False
        if os.path.exists(fp):
            try:
                from PIL import Image
                w, h = Image.open(fp).size
                tiny = max(w, h) < 100
            except ImportError:
                tiny = True
        if not tiny:
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j < len(lines) and re.match(r"#+\s*(复习巩固|综合运用|拓广探索)", lines[j].strip()):
            hits.append("%s L%d：小节图标无 alt: %s" % (book, i + 1, lines[i].strip()[:60]))
    return hits


def d10(md, book):
    """悬空引用：md 引用了但文件不存在（文件删除不可重做，曾因流水线重跑复发）"""
    hits = []
    base = os.path.join(_SRC_DIR, book)
    for m in re.finditer(r"!\[[^\]]*\]\(\s*([^)\s]+)\s*\)", md):
        r = m.group(1)
        if not os.path.exists(os.path.join(base, r)):
            hits.append("%s L%d：悬空引用 %s" % (book, md[:m.start()].count("\n") + 1, r))
    return hits


def run(source_dir=None, books=None):
    """D1–D10 探测器套件（行为保持版入口，自 main() 参数化）。

    source_dir: final 目录（含 <book>/markdown.md 与 <book>/images/）
    返回 {"per_detector": {名称: 命中数}, "total": 总数}；报告走 stderr。
    """
    global _SRC_DIR
    if not source_dir:
        raise ValueError("run() 需要 source_dir（参数化注入）")
    _SRC_DIR = source_dir
    books = books or BOOKS
    grand = 0
    per = {}
    for name, fn in [("D1 退化重复", d1), ("D2 数集记号词典", d2),
                     ("D3 符号误识专项", d3), ("D4 图片引用完整性", d4),
                     ("D5 渲染完整性", d5), ("D6 水印图内容检测", d6),
                     ("D7 HTML 标签/实体泄漏", d7), ("D8 quad-text 退化垃圾", d8),
                     ("D9 小节图标 alt", d9), ("D10 悬空引用", d10)]:
        p("===== %s =====" % name)
        total = 0
        for b in books:
            md = open(os.path.join(_SRC_DIR, b, "markdown.md"), encoding="utf-8").read()
            hits = fn(book=b) if fn in (d4, d6) else fn(md, b)
            total += len(hits)
            for h in hits[:15]:
                p("  " + h)
        p("  小计：%d 处" % total)
        p()
        per[name] = total
        grand += total
    p("########## 总计 %d 处 ##########" % grand)
    return {"per_detector": per, "total": grand}


if __name__ == "__main__":
    import argparse
    _p = argparse.ArgumentParser(description="D1–D10 探测器套件（tbp scan 的内核）")
    _p.add_argument("--source", required=True, help="final 目录")
    _p.add_argument("books", nargs="*", help="册名列表，缺省为默认五册")
    _a = _p.parse_args()
    run(source_dir=_a.source, books=_a.books or None)
