#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""技能壳脚本：C 档复核表生成（SKILL.md §2.2，方案 §4.2.3 adjudicate_sheet）。

从 out/<book>/issues.json 提取存疑项，生成 Markdown 复核表写回
out/<book>/复核裁定表.md，供人工对照 PDF 逐条裁定。只读 issues.json，
不修改任何转换产物。

用法：
    python adjudicate_sheet.py --workspace <ws> --book <册名> [--tier C]

退出码：0 已生成 · 50 找不到 issues.json。
"""
import argparse
import datetime
import json
import os
import sys
import time

EXIT_OK = 0
EXIT_MISSING = 50

HEADER = """# 复核裁定表 — {book}

> 生成：{now} · 来源：issues.json（{total} 项，B 档 {b} / C 档 {c}）
> 用法：逐条对照 PDF 原书，在"裁定"列填 正确 / 误报 / 存疑，必要时补备注。
> 裁定完成后用 overlay_scaffold.py 固化为书目覆盖层（L2）。

| # | 档位 | 探测器 | 位置 | 摘录 | 裁定 | 备注 |
|---|------|--------|------|------|------|------|
"""


def _emit(payload, exit_code, t0):
    payload.update({"cmd": "adjudicate_sheet", "ok": exit_code == 0,
                    "exit_code": exit_code, "elapsed_sec": round(time.time() - t0, 2)})
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return exit_code


def _esc(text):
    return (text or "").replace("|", "\\|").replace("\n", " ")[:80]


def main():
    t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--book", required=True)
    ap.add_argument("--tier", default="C", choices=["B", "C", "BC"])
    args = ap.parse_args()

    ipath = os.path.join(args.workspace, "out", args.book, "issues.json")
    if not os.path.isfile(ipath):
        return _emit({"book": args.book,
                      "error": {"code": "NO_ISSUES",
                                "message": "未找到 %s（先跑 tbp run / tbp scan）" % ipath}},
                     EXIT_MISSING, t0)
    issues = json.load(open(ipath, encoding="utf-8"))
    tiers = set(args.tier) if args.tier != "BC" else {"B", "C"}
    items = [it for it in issues.get("items", []) if it.get("tier") in tiers]

    lines = [HEADER.format(book=args.book,
                           now=datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                           total=issues.get("counts", {}).get("B", 0) + issues.get("counts", {}).get("C", 0),
                           b=issues.get("counts", {}).get("B", 0),
                           c=issues.get("counts", {}).get("C", 0))]
    if items:
        for i, it in enumerate(items, 1):
            loc = "L%s" % it["line"] if it.get("line") else "—"
            lines.append("| %d | %s | %s | %s | %s |  |  |\n" % (
                i, it.get("tier", "C"), it.get("detector", "?"), loc,
                _esc(it.get("excerpt") or it.get("suggestion") or "")))
    else:
        lines.append("\n（%s 档当前无细项——counts 见文件头。）\n" % "/".join(sorted(tiers)))

    out_path = os.path.join(os.path.dirname(ipath), "复核裁定表.md")
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.writelines(lines)
    return _emit({"book": args.book, "sheet": out_path, "items": len(items)},
                 EXIT_OK, t0)


if __name__ == "__main__":
    sys.exit(main())
