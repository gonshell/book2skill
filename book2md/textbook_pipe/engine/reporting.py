# -*- coding: utf-8 -*-
"""gzsx 全量转换后处理。

对 final/{册}/markdown.md 执行：
1. 页眉噪音清理（教材页眉残留、孤立数字行）
2. 公式双表示：为每个 LaTeX 公式追加线性文本 alt 注释（RAG/embedding 友好）
3. 页码映射表：从 blocks 的 middle_json 提取 物理页→教材页码 全表
4. 全局目录树：提取各册标题层级
5. 质检报告：统计已知错识模式（标注给人工复核，不自动改）

用法: python postprocess.py

搬迁说明（2026-10-24）：自 gzsx-md/postprocess.py 行为保持迁入（→ engine/reporting.py，docs/conventions.md 附录 A）；
ROOT 由环境变量 TBP_SOURCE_ROOT 覆盖（默认 cwd），BOOKS 不再读 sys.argv（argv 解析归 CLI 层）。
"""
import json, os, re, glob, sys
from collections import Counter

# 路径根：环境变量可覆盖；后续由 CLI/workspace 配置注入（docs/spec-cli.md §2），禁硬编码绝对路径
ROOT = os.environ.get("TBP_SOURCE_ROOT", os.path.abspath("."))
BLOCKS = os.path.join(ROOT, "blocks")
FINAL = os.path.join(ROOT, "final")
BOOKS = ["选择性必修第三册", "选择性必修第二册", "选择性必修第一册", "必修第二册", "必修第一册"]

GREEK = {
    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\theta": "θ",
    r"\pi": "π", r"\phi": "φ", r"\varphi": "φ", r"\lambda": "λ",
    r"\mu": "μ", r"\omega": "ω", r"\Delta": "Δ", r"\Sigma": "Σ",
}
SYM = {
    r"\times": "×", r"\div": "÷", r"\leq": "≤", r"\geq": "≥",
    r"\leqslant": "≤", r"\geqslant": "≥", r"\neq": "≠", r"\approx": "≈",
    r"\sim": "~", r"\perp": "⊥", r"\parallel": "∥", r"\in": "∈",
    r"\notin": "∉", r"\subset": "⊂", r"\cup": "∪", r"\cap": "∩",
    r"\emptyset": "∅", r"\infty": "∞", r"\pm": "±", r"\cdot": "·",
    r"\circ": "°", r"\ldots": "…", r"\cdots": "…",
}


def latex_to_plain(tex):
    """LaTeX → 线性纯文本（给 embedding 用的辅助表示，不追求完美）。"""
    s = tex
    # \frac{A}{B} 两层处理（嵌套先内后外，最多迭代 4 轮）
    for _ in range(4):
        s2 = re.sub(r"\\d?frac\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", r"(\1)/(\2)", s)
        if s2 == s:
            break
        s = s2
    s = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"sqrt(\1)", s)
    s = re.sub(r"\\sqrt\s*(\d)", r"sqrt[\1]", s)
    # \text{...} \mathrm{...} 等装饰命令取内容
    s = re.sub(r"\\(?:text|mathrm|mathbf|mathit|mathcal|operatorname|boldsymbol|scriptstyle)\s*\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\overrightarrow\s*\{([^{}]*)\}", r"vec(\1)", s)
    s = re.sub(r"\\overline\s*\{([^{}]*)\}", r"bar(\1)", s)
    s = re.sub(r"\\widehat\s*\{([^{}]*)\}", r"hat(\1)", s)
    s = re.sub(r"\\sum_\{([^{}]*)\}\^\{([^{}]*)\}", r"sum(\1 to \2)", s)
    s = re.sub(r"\\int_\{([^{}]*)\}\^\{([^{}]*)\}", r"int(\1 to \2)", s)
    s = re.sub(r"\\prod_\{([^{}]*)\}\^\{([^{}]*)\}", r"prod(\1 to \2)", s)
    # 上下标
    s = re.sub(r"\^\{([^{}]*)\}", r"^(\1)", s)
    s = re.sub(r"_\{([^{}]*)\}", r"_(\1)", s)
    s = s.replace(r"\left", "").replace(r"\right", "")
    s = re.sub(r"\\[a-zA-Z]+", lambda m: GREEK.get(m.group(0), SYM.get(m.group(0), "")), s)
    s = re.sub(r"\\[{}]", "", s)
    s = re.sub(r"\s+", " ", s).strip(" ,.;:=")
    return s


def clean_noise(md):
    """页眉/页脚噪音清理。"""
    lines = md.split("\n")
    out = []
    # 常见教材页眉模式（人教 A 版：章名+册名单独行、孤立数字、栏目名）
    header_re = re.compile(r"^(第[一二三四五六七八九十百]+[章讲节]\s*.{0,20}|数学[\s·]*选择性?必修.{0,10}|\d{1,3})\s*$")
    for ln in lines:
        if header_re.match(ln.strip()):
            continue
        # 行首页眉粘连："2"重复"意味着…" 这类独立数字+内容的残留行首
        m = re.match(r'^"(\d{1,2})"', ln.strip())
        if m and len(ln.strip()) > 3:
            ln = re.sub(r'^"?\d{1,2}"?', "", ln, count=1).lstrip()
        out.append(ln)
    return "\n".join(out)


def add_formula_alt(md):
    """为 $$..$$ 块公式追加 <!-- alt: ... --> 线性文本。

    行级状态机（非正则跨行匹配）：只有遇到独立成行的 $$ 开始、且后续能找到
    独立成行的 $$ 结束时才处理；未闭合/单行混排等异常形态原样保留，绝不一吞一大片。
    幂等：已有 alt 的公式不重复加。
    """
    lines = md.split("\n")
    out = []
    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]
        if ln.strip() == "$$":
            j = i + 1
            body = []
            while j < n and lines[j].strip() != "$$":
                body.append(lines[j])
                j += 1
            if j >= n:
                # 未闭合：原样输出起始行及剩余，不再尝试吞内容
                out.extend(lines[i:])
                break
            body_txt = "\n".join(body).strip()
            # 幂等：公式块后一行已是 alt 则跳过
            nxt = lines[j + 1] if j + 1 < n else ""
            out.append(ln)
            out.extend(body)
            out.append(lines[j])
            if body_txt and not nxt.strip().startswith("<!-- alt:"):
                alt = latex_to_plain(body_txt)
                if alt:
                    out.append(f"<!-- alt: {alt} -->")
            i = j + 1
            continue
        # 单行 $$...$$ 形态
        m = re.match(r"^\s*\$\$(.+?)\$\$\s*$", ln)
        if m and not ln.strip().startswith("<!--"):
            body_txt = m.group(1).strip()
            alt = latex_to_plain(body_txt)
            if alt:
                out.append(f"$$\n{body_txt}\n$$\n<!-- alt: {alt} -->")
                i += 1
                continue
        out.append(ln)
        i += 1
    return "\n".join(out)


def extract_page_map(book):
    """从 blocks/{book}/ex_*/middle_json.json 提取 物理页→教材页码。"""
    pmap = {}
    for mjp in sorted(glob.glob(os.path.join(BLOCKS, book, "ex_*", "middle_json.json"))):
        m = re.search(r"ex_(\d+)-(\d+)", mjp)
        s = int(m.group(1))
        mj = json.load(open(mjp, encoding="utf-8"))
        for p in mj.get("pages", []):
            idx = p.get("page_idx")
            pn = next((b.get("content", [{}])[0].get("content")
                       for b in p.get("blocks", []) if b.get("type") == "page_number"), None)
            if idx is not None and pn:
                pmap[idx + 1] = pn  # page_idx(0-based 全局) → 物理页(1-based)
    return pmap


def build_toc(book, md):
    """提取标题，返回目录条目 [(level, title, anchor_line)。"""
    entries = []
    in_code = False
    for i, ln in enumerate(md.split("\n")):
        if ln.strip().startswith("```"):
            in_code = not in_code
        if in_code:
            continue
        m = re.match(r"^(#{2,4})\s+(.*)", ln)
        if m:
            entries.append((len(m.group(1)), m.group(2).strip()))
    return entries


QA_PATTERNS = {
    "公式内中文引号错识": re.compile(r"\^\s*\{?\s*\\mathrm\s*\{?\s*~"),
    "overrightarrow误识为widehat": re.compile(r"\\widehat\s*\{[A-Za-z]\.*[A-Za-z]*\}"),
    "顶点bar误识": re.compile(r"\\bar\s*\{?"),
    "多余否定号\\not": re.compile(r"\\not\s+[a-zA-Z]"),
    "花括号错位": re.compile(r"[A-Za-z0-9]\.?\}'"),
}


def main():
    report = {}
    toc_all = {}
    for book in BOOKS:
        md_path = os.path.join(FINAL, book, "markdown.md")
        if not os.path.exists(md_path):
            print(f"[跳过] {book} 无输出")
            continue
        md = open(md_path, encoding="utf-8").read()
        orig_len = len(md)

        # 1. 噪音清理 + 2. 公式 alt
        md = clean_noise(md)
        md = add_formula_alt(md)

        # 3. 页码映射表
        pmap = extract_page_map(book)
        if pmap:
            pmd = f"# {book} 页码映射表（物理页 → 教材页码）\n\n"
            pmd += "| 物理页 | 教材页 |\n| --- | --- |\n"
            for phys in sorted(pmap):
                pmd += f"| {phys} | {pmap[phys]} |\n"
            open(os.path.join(FINAL, book, "page_map.md"), "w", encoding="utf-8").write(pmd)

        # 4. QA 统计
        qa = {k: len(v.findall(md)) for k, v in QA_PATTERNS.items()}
        report[book] = {"qa_patterns": qa, "chars": len(md), "page_map_entries": len(pmap)}

        # 5. 目录
        toc_all[book] = build_toc(book, md)

        open(md_path, "w", encoding="utf-8").write(md)
        print(f"[{book}] 清理后 {len(md)} 字符（原 {orig_len}）| 页码映射 {len(pmap)} 条 | QA: {qa}")

    # 全局目录
    toc_md = "# 人教 A 版高中数学（5 册）总目录\n\n"
    for book in BOOKS:
        if book not in toc_all:
            continue
        toc_md += f"\n## {book}\n\n"
        for lv, t in toc_all[book]:
            toc_md += f"{'  ' * (lv - 2)}- {t}\n"
    open(os.path.join(FINAL, "TOC.md"), "w", encoding="utf-8").write(toc_md)

    # 质检报告
    qa_md = "# 转换质检报告\n\n"
    qa_md += "| 册 | 字符数 | 页码映射 | 公式内引号错识 | \\overrightarrow误识 | 顶点bar误识 | 多余\\not | 花括号错位 |\n"
    qa_md += "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
    for book, r in report.items():
        qa = r["qa_patterns"]
        qa_md += (f"| {book} | {r['chars']} | {r['page_map_entries']} | {qa['公式内中文引号错识']} | "
                  f"{qa['overrightarrow误识为widehat']} | {qa['顶点bar误识']} | {qa['多余否定号\\not']} | {qa['花括号错位']} |\n")
    qa_md += "\n> QA 统计为已知错识模式的频次，供人工复核定位；未做自动改写以免误伤。\n"
    open(os.path.join(FINAL, "质检报告.md"), "w", encoding="utf-8").write(qa_md)
    print("\n后处理完成：TOC.md / 质检报告.md / 各册 page_map.md 已生成")


if __name__ == "__main__":
    main()


def configure(root):
    """工作区路径注入（CLI 层调用）。

    仅替换模块级路径常量（ROOT/BLOCKS/FINAL），不改变任何函数行为：
    FINAL 对应 legacy 语义的 final 目录，在本包工作区布局中即 <workspace>/out。
    """
    global ROOT, BLOCKS, FINAL
    ROOT = root
    BLOCKS = os.path.join(ROOT, "blocks")
    FINAL = os.path.join(ROOT, "out")
