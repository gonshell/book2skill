# -*- coding: utf-8 -*-
"""b2q node — 单节点全料（learn/drill 的取料命令）。"""
import os
import sys

from book2qa import paths
from book2qa.envelope import emit
from book2qa.exit_codes import EXIT_MISSING, EXIT_OK


def execute(args, t0):
    import json
    workspace = paths.resolve_workspace(args)
    book = getattr(args, "book", "必修第一册")
    path = os.path.join(paths.book_data_dir(workspace, book), "graph.jsonl")
    node = None
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for ln in f:
                r = json.loads(ln)
                if r.get("id") == args.node_id:
                    node = r
                    break
    if node is None:
        return emit("node", EXIT_MISSING, workspace=workspace,
                    error="节点不存在：%s" % args.node_id, t0=t0)
    return emit("node", EXIT_OK, workspace=workspace, t0=t0,
                extra={"node": node})


if __name__ == "__main__":
    sys.exit(0)
