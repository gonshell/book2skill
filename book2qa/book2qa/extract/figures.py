# -*- coding: utf-8 -*-
"""核心层：图号 ↔ 图片文件映射（S1-2c）。

真实形态（必修一取证）：图号 `图3.4-1`（无空格），文件 `page_N_image_M.jpg`
（N = PDF 页）。锚定链：图注行（段首即图号，最可靠）→ 首次引用行 →
段落物理页 → 邻近 ±1 PDF 页内的图片文件。

无丢弃：引用找不到文件报 figure_no_file；文件没被任何图号引用汇总一条
file_no_ref（章节插图/装饰图多，属常态）。
"""
import os
import re

IMG_REF_RE = re.compile(r"!\[[^\]]*\]\(images/(page_(\d+)_image_(\d+)\.\w+)\)")
FIG_RE = re.compile(r"图(\d+\.\d+-\d+)")
FIG_CAPTION_RE = re.compile(r"^图\s*(\d+\.\d+-\d+)")


def map_figures(paragraphs, page_marks, images_dir):
    """(paragraphs, page_marks, images_dir) → (rows, issues)。

    rows: {fig, file, physical_page, textbook_page?, line, by_caption}
    """
    files_by_pdf = {}
    if images_dir and os.path.isdir(images_dir):
        for fn in sorted(os.listdir(images_dir)):
            m = re.match(r"page_(\d+)_image_(\d+)\.\w+", fn)
            if m:
                files_by_pdf.setdefault(int(m.group(1)), []).append(fn)

    line2para = {}
    for p in paragraphs:
        for ln in range(p.start_line, p.end_line + 1):
            line2para[ln] = p

    def offset_of(ln):
        """行所属块的图片偏移；无块/越界返回 None。"""
        lo = 0
        for i, mk in enumerate(page_marks):
            if mk.line_no <= ln:
                lo = i
            else:
                break
        if not page_marks or page_marks[lo].line_no > ln:
            return None
        return page_marks[lo].offset

    rows = []
    issues = []
    used_files = set()
    seen_fig = {}
    caption_figs = set()
    ref_figs = {}

    for p in paragraphs:
        for off, ln in enumerate(p.text.split("\n")):
            abs_ln = p.start_line + off
            cm = FIG_CAPTION_RE.match(ln.strip())
            if cm:
                caption_figs.add(cm.group(1))
            for fm in FIG_RE.finditer(ln):
                ref_figs.setdefault(fm.group(1), abs_ln)

    def phys_of_line(ln):
        p = line2para.get(ln)
        if p is None or p.physical_page is None:
            return None
        return p.physical_page, p.textbook_page

    for fig, first_line in sorted(ref_figs.items(), key=lambda kv: kv[1]):
        cap_line = None
        # 图注行：在引用行前后 3 行内找
        p = line2para.get(first_line)
        if p is not None:
            for ln in range(max(p.start_line, first_line - 3),
                            min(p.end_line + 1, first_line + 4)):
                if ln in line2para and \
                        FIG_CAPTION_RE.match(line2para[ln].text.split("\n")[0].strip()):
                    cap_line = ln
                    break
        anchor_line = cap_line if cap_line is not None else first_line
        anch = phys_of_line(anchor_line)
        if anch is None:
            issues.append({"code": "figure_no_page", "fig": fig,
                           "detail": "图 %s 锚定行 %d 无物理页" % (fig, anchor_line)})
            continue
        phys, tb = anch
        cands = []
        base_off = offset_of(anchor_line) or 0
        for dp in (-1, 0, 1):
            pdf = phys + base_off + dp
            for fn in files_by_pdf.get(pdf, []):
                cands.append((abs(dp), fn))
        if not cands:
            issues.append({"code": "figure_no_file", "fig": "图" + fig,
                           "detail": "图 %s（物理页 %d）±1 页无图片文件" % (fig, phys)})
            continue
        cands.sort()
        file_pick = None
        for _, fn in cands:  # 贪心去重：一个文件不判给两个图号
            if fn not in used_files:
                file_pick = fn
                break
        if file_pick is None:
            file_pick = cands[0][1]
        used_files.add(file_pick)
        rows.append({"fig": "图" + fig, "file": "images/" + file_pick,
                     "physical_page": phys, "textbook_page": tb,
                     "line": anchor_line, "by_caption": cap_line is not None})
        seen_fig[fig] = file_pick

    n_unref = sum(len(v) for k, v in files_by_pdf.items())
    if rows:
        issues.append({"code": "file_no_ref",
                       "detail": "未被图号引用的图片文件 %d/%d（章节插图属常态，不逐个列）"
                                 % (n_unref - len(seen_fig), n_unref)})
    return rows, issues


def to_json_line(row):
    import json
    return json.dumps(row, ensure_ascii=False)
