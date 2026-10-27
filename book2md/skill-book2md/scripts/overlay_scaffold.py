#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""技能壳脚本：书目覆盖层（L2）骨架固化（方案 §4.2.1 overlays / §流程④固化）。

把复核裁定表里已裁定的结论登记为 overlays/<book>/overlay.jsonl 骨架
（每行一条规则元数据：出处、类型、备注）。**只生成登记骨架，不实现规则加载**
——覆盖层引擎加载属于核心包 L2 机制（路线图阶段 C 后随化学书实战落地）。

用法：
    python overlay_scaffold.py --workspace <ws> --book <册名> \\
        [--source 复核裁定表.md] [--note 说明]

退出码：0 已登记 · 50 找不到输入。
"""
import argparse
import datetime
import json
import os
import sys
import time

EXIT_OK = 0
EXIT_MISSING = 50


def _emit(payload, exit_code, t0):
    payload.update({"cmd": "overlay_scaffold", "ok": exit_code == 0,
                    "exit_code": exit_code, "elapsed_sec": round(time.time() - t0, 2)})
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return exit_code


def main():
    t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--book", required=True)
    ap.add_argument("--source", default=None, help="裁定表路径（缺省 out/<book>/复核裁定表.md）")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    book_dir = os.path.join(args.workspace, "out", args.book)
    src = args.source or os.path.join(book_dir, "复核裁定表.md")
    if not os.path.isfile(src):
        return _emit({"book": args.book,
                      "error": {"code": "NO_SHEET",
                                "message": "未找到 %s（先跑 adjudicate_sheet.py 并完成人工裁定）" % src}},
                     EXIT_MISSING, t0)

    ov_dir = os.path.join(args.workspace, "overlays", args.book)
    os.makedirs(ov_dir, exist_ok=True)
    entry = {
        "schema": "b2m.overlay/v1",
        "book": args.book,
        "registered_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_sheet": os.path.abspath(src),
        "note": args.note,
        "status": "scaffold",   # scaffold → 核心包 L2 加载机制落地后转 active
    }
    out_path = os.path.join(ov_dir, "overlay.jsonl")
    with open(out_path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    readme = os.path.join(ov_dir, "README.md")
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("# overlays/%s — 书目裁定覆盖层（用户数据，不进产品仓库）\n\n"
                     "记录本书人工裁定的存疑内容结论。核心包 L2 加载机制落地前，\n"
                     "本目录仅作登记沉淀；overlay.jsonl 每行一条 b2m.overlay/v1 登记。\n" % args.book)
    return _emit({"book": args.book, "overlay": out_path,
                  "note": "骨架已登记；规则加载待核心包 L2 机制（见路线图阶段 C）"},
                 EXIT_OK, t0)


if __name__ == "__main__":
    sys.exit(main())
