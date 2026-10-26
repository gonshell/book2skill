# -*- coding: utf-8 -*-
"""issues.json 构建（docs/spec-cli.md §6.2 schema，scan / run 共用）。

两条来源，统一成 items：
  · 探测器/渲染完整性/texmath 命中 → B 档（需人工判断是否误报）
  · S16 结构性损坏公式降级清单（broken_formulas.tsv）→ C 档（引擎已判定不可还原，
    须按 PDF 原书补录；引擎不臆造内容）
items 一律带 line / excerpt 定位信息，供技能壳生成可裁定的复核表。
"""
import datetime
import os
import re

_LINE_RE = re.compile(r"\bL(\d+)\b")
_EXCERPT_MAX = 160


def _items_from_detectors(det, start=1):
    """探测命中串 → items（命中串形如「册名 L行号：描述」）。"""
    items, idx = [], start
    for name, hits in det.get("details", {}).items():
        for hit in hits:
            m = _LINE_RE.search(hit)
            items.append({"id": "I-%04d" % idx, "tier": "B", "detector": name,
                          "line": int(m.group(1)) if m else None,
                          "excerpt": hit[:_EXCERPT_MAX],
                          "suggestion": None})
            idx += 1
    return items, idx


def _items_from_broken(src_root, book, start=1):
    """S16 降级清单（TSV：序号/类型/原串/上下文）→ C 档 items。

    注意：原串字段本身可能含换行（块公式），不能按行切分；行首「序号\\t」才是新记录。
    """
    path = os.path.join(src_root, book, "broken_formulas.tsv")
    if not os.path.isfile(path):
        return [], start
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    items, idx = [], start
    for row in re.split(r"\n(?=\d+\t)", text):
        row = row.strip("\n")
        if not row or row.lstrip().startswith("#"):
            continue
        cols = row.split("\t")
        if len(cols) < 3:
            continue
        kind = cols[1].strip()
        raw = " ".join(cols[2].split())
        items.append({"id": "I-%04d" % idx, "tier": "C",
                      "detector": "S16 结构性损坏公式降级（%s）" % (kind or "?"),
                      "line": None,
                      "excerpt": raw[:_EXCERPT_MAX],
                      "suggestion": "按 PDF 原书补录；引擎已降级为占位，未臆造内容"})
        idx += 1
    return items, idx


def collect(book, src_root, books=None):
    """对 src_root 下指定册跑探测器矩阵 + 渲染完整性 + texmath，返回 issues dict。"""
    from textbook_pipe.engine.inspectors import detectors, integrity, texmath

    det = detectors.run(source_dir=src_root, books=books)
    integ = integrity.scan(source_dir=src_root, books=books)
    tex = texmath.run(source_dir=src_root, books=books)

    total = det["total"] + sum(len(v) for v in integ.values()) + tex["total"]
    items, nxt = _items_from_detectors(det)
    c_items, nxt = _items_from_broken(src_root, book, start=nxt)
    items.extend(c_items)
    return {
        "schema": "tbp.issues/v1",
        "book": book,
        "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "counts": {"A": 0, "B": total, "C": len(c_items)},
        "items": items,
        "detail": {"detectors": det["per_detector"],
                   "render_integrity": {k: len(v) for k, v in integ.items()},
                   "texmath": tex["per_book"],
                   "broken_formulas": len(c_items)},
        "note": "A 档引擎自修不入 items；C 档来自 S16 降级清单，须按 PDF 人工补录",
    }


def write(issues, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    import json
    json.dump(issues, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return out_path
