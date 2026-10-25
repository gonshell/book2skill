# -*- coding: utf-8 -*-
"""issues.json 构建（docs/spec-cli.md §6.2 schema，scan / run 共用）。"""
import datetime
import os


def collect(book, src_root, books=None):
    """对 src_root 下指定册跑探测器矩阵 + 渲染完整性 + texmath，返回 issues dict。"""
    from textbook_pipe.engine.inspectors import detectors, integrity, texmath

    det = detectors.run(source_dir=src_root, books=books)
    integ = integrity.scan(source_dir=src_root, books=books)
    tex = texmath.run(source_dir=src_root, books=books)

    total = det["total"] + sum(len(v) for v in integ.values()) + tex["total"]
    items = [{"id": "I-%04d" % i, "tier": "B", "detector": name,
              "line": None, "excerpt": None, "suggestion": None}
             for name, n in det["per_detector"].items() for i in range(n)]
    return {
        "schema": "tbp.issues/v1",
        "book": book,
        "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "counts": {"A": 0, "B": total, "C": 0},
        "items": items,
        "detail": {"detectors": det["per_detector"],
                   "render_integrity": {k: len(v) for k, v in integ.items()},
                   "texmath": tex["per_book"]},
        "note": "细项见 stderr 报告；tier 归类（A 引擎自修 / C 人工裁定）在 run/onboard 环节细分",
    }


def write(issues, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    import json
    json.dump(issues, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return out_path
