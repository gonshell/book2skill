# -*- coding: utf-8 -*-
"""b2m scan — 只读体检（docs/spec-cli.md §6.8）。

跑 D1–D10 探测器 + 渲染完整性 + texmath 语义三套检查，刷新 out/<book>/issues.json。
--source out：扫修复终版（回归过关线 = 探测器全零）；
--source extract：扫抽取原始 md（评估规则包覆盖率）。
"""
import os

from book2md.exit_codes import EXIT_MISSING, EXIT_OK
from book2md.commands._envelope import emit
from book2md.commands import _issues


def execute(args, t0):
    workspace = args.workspace
    src_root = os.path.join(workspace, args.source)   # out/ 或 extract/
    md = os.path.join(src_root, args.book, "markdown.md")
    if not os.path.exists(md):
        return emit("scan", EXIT_MISSING, workspace=src_root, book=args.book,
                    error={"code": "NO_BOOK",
                           "message": "未找到 %s（需要 %s/<book>/markdown.md）" % (md, src_root)}, t0=t0)

    issues = _issues.collect(args.book, src_root, books=[args.book])
    total = issues["counts"]["B"]
    out_dir = os.path.join(workspace, "out", args.book)
    issues_path = _issues.write(issues, os.path.join(out_dir, "issues.json"))

    warnings = []
    if args.source == "out" and total > 0:
        warnings.append("修复终版存在 %d 处命中（过关线为全零），见 issues.json detail" % total)
    return emit("scan", EXIT_OK, workspace=workspace, book=args.book,
                artifacts={"issues": issues_path}, warnings=warnings, t0=t0)
