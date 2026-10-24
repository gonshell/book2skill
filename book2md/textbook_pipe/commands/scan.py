# -*- coding: utf-8 -*-
"""tbp scan — 只读体检（docs/spec-cli.md §6.8）。

跑 D1–D10 探测器 + 渲染完整性 + texmath 语义三套检查，刷新 out/<book>/issues.json。
--source out：扫修复终版（回归过关线 = 探测器全零）；
--source extract：扫抽取原始 md（评估规则包覆盖率）。
"""
import datetime
import json
import os

from textbook_pipe.engine.inspectors import detectors, integrity, texmath
from textbook_pipe.exit_codes import EXIT_MISSING, EXIT_OK
from textbook_pipe.commands._envelope import emit


def execute(args, t0):
    workspace = args.workspace
    src_root = os.path.join(workspace, args.source)   # out/ 或 extract/
    md = os.path.join(src_root, args.book, "markdown.md")
    if not os.path.exists(md):
        return emit("scan", EXIT_MISSING,
                    error={"code": "NO_BOOK",
                           "message": "未找到 %s（需要 %s/<book>/markdown.md）" % (md, src_root)}, t0=t0)

    det = detectors.run(source_dir=src_root, books=[args.book])
    integ = integrity.scan(source_dir=src_root, books=[args.book])
    tex = texmath.run(source_dir=src_root, books=[args.book])

    total = det["total"] + sum(len(v) for v in integ.values()) + tex["total"]
    items = [{"id": "I-%04d" % i, "tier": "B", "detector": name,
              "line": None, "excerpt": None, "suggestion": None}
             for name, n in det["per_detector"].items() for i in range(n)]
    issues = {
        "schema": "tbp.issues/v1",
        "book": args.book,
        "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "counts": {"A": 0, "B": total, "C": 0},
        "items": items,
        "detail": {"detectors": det["per_detector"],
                   "render_integrity": {k: len(v) for k, v in integ.items()},
                   "texmath": tex["per_book"]},
        "note": "细项见 stderr 报告；tier 归类（A 引擎自修 / C 人工裁定）在 run/onboard 环节细分",
    }
    out_dir = os.path.join(workspace, "out", args.book)
    os.makedirs(out_dir, exist_ok=True)
    issues_path = os.path.join(out_dir, "issues.json")
    json.dump(issues, open(issues_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    warnings = []
    if args.source == "out" and total > 0:
        warnings.append("修复终版存在 %d 处命中（过关线为全零），见 issues.json detail" % total)
    return emit("scan", EXIT_OK, workspace=workspace, book=args.book,
                artifacts={"issues": issues_path}, warnings=warnings, t0=t0)
