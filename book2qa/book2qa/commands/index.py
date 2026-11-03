# -*- coding: utf-8 -*-
"""b2q index — 全册教学段落编码 → vectors.npz + vectors_meta.jsonl（M1c）。"""
import argparse
import os
import sys
import time

from book2qa import embed, paths
from book2qa.envelope import emit
from book2qa.exit_codes import EXIT_MISSING, EXIT_OK

TEACH = ("正文", "思考", "观察", "探究", "归纳", "小结",
         "阅读与思考", "探究与发现", "信息技术应用", "例")
BATCH = 32


def execute(args, t0):
    import json
    from book2qa import source
    workspace = paths.resolve_workspace(args)
    files = paths.book_files(paths.resolve_source_root(args), args.book)
    if not os.path.isfile(files["markdown"]):
        return emit("index", EXIT_MISSING, workspace=workspace, book=args.book,
                    error="缺少 book2md 产物", t0=t0)
    models_dir = os.environ.get("B2Q_MODELS_DIR") or os.path.expanduser(
        "~/.book2qa/models/bge-onnx")
    try:
        encoder = embed.Encoder(models_dir)
    except Exception as e:   # 模型/依赖缺失：明确报错（index 是显式运营动作）
        return emit("index", EXIT_MISSING, workspace=workspace, book=args.book,
                    error="编码器不可用：%s" % e, t0=t0)

    text = source.read_markdown(files["markdown"])
    page_marks, _ = source.parse_page_marks(text)
    page_map = source.parse_page_map(files["page_map"])
    paragraphs = source.split_paragraphs(text, page_marks, page_map)
    meta_rows = source.load_para_meta(workspace, args.book)
    meta_by = {m["idx"]: m for m in meta_rows}

    items = []   # (text, meta)
    for p in paragraphs:
        m = meta_by.get(p.idx)
        if not m or m.get("block_kind") not in TEACH:
            continue
        t = p.text.strip()
        if len(t) < 12:
            continue
        items.append((t, {"section_id": m.get("owner_id"),
                          "block_kind": m.get("block_kind"),
                          "start_line": p.start_line,
                          "textbook_page": p.textbook_page,
                          "page_estimated": p.page_estimated,
                          "head": t[:40]}))

    vectors = []
    for i in range(0, len(items), BATCH):
        chunk = [t for t, _ in items[i:i + BATCH]]
        vectors.append(encoder.encode(chunk))
    import numpy as np
    mat = np.vstack(vectors).astype(np.float32)

    out_dir = paths.ensure_data_dir(workspace)
    np.savez_compressed(os.path.join(out_dir, "vectors.npz"),
                        vectors=mat)
    with open(os.path.join(out_dir, "vectors_meta.jsonl"), "w",
              encoding="utf-8") as f:
        for _, m in items:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    return emit("index", EXIT_OK, workspace=workspace, book=args.book,
                artifacts={"vectors": os.path.join(out_dir, "vectors.npz"),
                           "vectors_meta": os.path.join(out_dir, "vectors_meta.jsonl")},
                t0=t0,
                extra={"encoded": len(items), "dim": int(mat.shape[1])})


if __name__ == "__main__":
    sys.exit(0)
