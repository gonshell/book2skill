# -*- coding: utf-8 -*-
"""b2m report — 重生 TOC.md 与 质检报告.md（docs/spec-cli.md §6.9）。

语义 = regen_toc_qa.py（行为保持）：只读 out/<book>/markdown.md，聚合重建
workspace 级 TOC.md 与 质检报告.md；md 本体永不改动。
"""
import os
import sys
import time

from book2md.engine import reporting
from book2md.engine.reporting import QA_COLUMNS
from book2md.exit_codes import EXIT_MISSING, EXIT_OK
from book2md.commands._envelope import emit


def execute(args, t0):
    workspace = args.workspace
    out_root = os.path.join(workspace, "out")
    if not os.path.isdir(out_root):
        return emit("report", EXIT_MISSING,
                    error={"code": "NO_OUT", "message": "out 目录不存在: %s" % out_root}, t0=t0)

    reporting.configure(workspace)  # 页码映射需要 blocks/<book>/（无则映射为空，报告照出）

    if args.book:
        books = [args.book]
        if not os.path.exists(os.path.join(out_root, args.book, "markdown.md")):
            return emit("report", EXIT_MISSING,
                        error={"code": "NO_BOOK", "message": "未找到 %s/markdown.md" % args.book}, t0=t0)
    else:
        books = sorted(d for d in os.listdir(out_root)
                       if os.path.exists(os.path.join(out_root, d, "markdown.md")))
        if not books:
            return emit("report", EXIT_MISSING,
                        error={"code": "NO_BOOK", "message": "out/ 下没有任何 <book>/markdown.md"}, t0=t0)

    report, toc_all, warnings = {}, {}, []
    for book in books:
        md_path = os.path.join(out_root, book, "markdown.md")
        md = open(md_path, encoding="utf-8").read()
        pmap = reporting.extract_page_map(book)
        report[book] = {"qa_patterns": {k: len(v.findall(md)) for k, v in reporting.QA_PATTERNS.items()},
                        "chars": len(md), "page_map_entries": len(pmap)}
        toc_all[book] = reporting.build_toc(book, md)

    # TOC.md（聚合，格式同 regen_toc_qa 语义）
    toc_md = "# 总目录\n"
    for book in books:
        toc_md += "\n## %s\n" % book
        for lv, t in toc_all[book]:
            toc_md += "%s- %s\n" % ("  " * (lv - 2), t)
    toc_path = os.path.join(out_root, "TOC.md")
    open(toc_path, "w", encoding="utf-8").write(toc_md)

    # 质检报告.md（格式同 regen_toc_qa 语义）
    qa_md = "# 转换质检报告\n\n"
    qa_md += "| 册 | 字符数 | 页码映射 | " + " | ".join(QA_COLUMNS) + " |\n"
    qa_md += "| --- | --- | --- | " + " | ".join(["---"] * len(QA_COLUMNS)) + " |\n"
    for book, r in report.items():
        qa = r["qa_patterns"]
        qa_md += "| %s | %d | %d | " % (book, r["chars"], r["page_map_entries"])
        qa_md += " | ".join(str(qa[c]) for c in QA_COLUMNS) + " |\n"
    qa_md += "\n> QA 统计为已知错识模式的频次，供人工复核定位；未做自动改写以免误伤。\n"
    qa_path = os.path.join(out_root, "质检报告.md")
    open(qa_path, "w", encoding="utf-8").write(qa_md)

    print("TOC + QA REGEN-DONE", file=sys.stderr)
    return emit("report", EXIT_OK,
                workspace=workspace, book=args.book,
                artifacts={"toc": toc_path, "qa_report": qa_path},
                warnings=warnings, t0=t0)
