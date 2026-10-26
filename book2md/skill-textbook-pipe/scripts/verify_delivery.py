#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""技能壳脚本：交付核验（SKILL.md §2.1）。

核对 out/<book>/ 交付清单完整性 + HTML 自包含抽查。只读，不修改产物。

用法：
    python verify_delivery.py --workspace <ws> --book <册名>

退出码：0 交付完整 · 10 有缺口（detail 列出） · 50 找不到产物目录。
"""
import argparse
import json
import os
import re
import sys
import time

EXIT_OK = 0
EXIT_GATE = 10
EXIT_MISSING = 50

# 交付清单（核心包 run 产物）
BOOK_FILES = ["markdown.md", "issues.json", "qa_gate.log", "TOC.md", "质检报告.md"]
BOOK_DIRS = ["images"]
# 条件产物：存在则记入 checks，缺失不判缺口
BOOK_FILES_OPTIONAL = ["provenance.json", "page_map.md", "broken_formulas.tsv"]
HTML_RE = re.compile(r'(src|href)="(?!data:|#)([^"]+)"')


def _emit(payload, exit_code, t0):
    payload.update({"cmd": "verify_delivery", "ok": exit_code == 0,
                    "exit_code": exit_code, "elapsed_sec": round(time.time() - t0, 2)})
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return exit_code


def main():
    t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--book", required=True)
    args = ap.parse_args()

    book_dir = os.path.join(args.workspace, "out", args.book)
    if not os.path.isdir(book_dir):
        return _emit({"book": args.book,
                      "error": {"code": "NO_DELIVERY", "message": "未找到 %s" % book_dir}},
                     EXIT_MISSING, t0)

    gaps, checks = [], []

    for f in BOOK_FILES:
        ok = os.path.isfile(os.path.join(book_dir, f))
        checks.append({"name": "file:%s" % f, "ok": ok})
        if not ok:
            gaps.append("缺少文件 out/%s/%s" % (args.book, f))
    for d in BOOK_DIRS:
        n = len([x for x in os.listdir(os.path.join(book_dir, d))]) if os.path.isdir(os.path.join(book_dir, d)) else -1
        ok = n > 0
        checks.append({"name": "dir:%s" % d, "ok": ok, "count": max(n, 0)})
        if not ok:
            gaps.append("目录为空或缺失 out/%s/%s" % (args.book, d))
    for f in BOOK_FILES_OPTIONAL:
        checks.append({"name": "optional:%s" % f,
                       "ok": True,
                       "present": os.path.isfile(os.path.join(book_dir, f))})

    # HTML 产物：核心包 run 落在 out/<book>/<variant>/<book>.html
    # （兼容历史/手工布局：工作区级 <variant>/、out/<book>/ 同名）
    html_hits = {}
    for variant in ("html", "kb_html"):
        candidates = [
            os.path.join(book_dir, variant, "%s.html" % args.book),
            os.path.join(args.workspace, variant, "%s.html" % args.book),
            os.path.join(book_dir, "%s.html" % args.book),
        ]
        p = next((c for c in candidates if os.path.isfile(c)), None)
        found = p is not None
        html_hits[variant] = {"found": found, "path": p}
        if not found:
            gaps.append("缺 %s 版 HTML（%s.html）" % (variant, args.book))

    # HTML 自包含抽查：外链 src/href 必须为 0（除 data:/锚点）
    for variant, hit in html_hits.items():
        if hit["found"]:
            html = open(hit["path"], encoding="utf-8").read()
            ext = [m[1] for m in HTML_RE.findall(html)]
            ok = not ext
            checks.append({"name": "selfcontain:%s" % variant, "ok": ok,
                           "external_refs": len(ext)})
            if not ok:
                gaps.append("%s 版 HTML 存在 %d 处外部引用（非自包含）"
                            % (variant, len(ext)))

    # issues.json 可解析且 schema 正确
    ipath = os.path.join(book_dir, "issues.json")
    if os.path.isfile(ipath):
        try:
            issues = json.load(open(ipath, encoding="utf-8"))
            ok = issues.get("schema") == "tbp.issues/v1"
            checks.append({"name": "issues_schema", "ok": ok,
                           "counts": issues.get("counts")})
            if not ok:
                gaps.append("issues.json schema 非 tbp.issues/v1")
        except (OSError, ValueError) as ex:
            gaps.append("issues.json 解析失败：%s" % ex)

    exit_code = EXIT_OK if not gaps else EXIT_GATE
    return _emit({"book": args.book, "book_dir": book_dir, "checks": checks,
                  "gaps": gaps, "html": html_hits}, exit_code, t0)


if __name__ == "__main__":
    sys.exit(main())
