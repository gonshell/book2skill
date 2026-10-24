# -*- coding: utf-8 -*-
"""渲染完整性扫描：行内游离 $$、奇数 $、块结构异常。

搬迁自 gzsx-md/scan_render.py（2026-10-24，行为保持，docs/conventions.md 附录 A）：
原为模块级脚本，改包为 scan(source_dir, books) 函数；报告走 stderr。
"""
import os
import re
import sys

BOOKS = ["必修第一册", "必修第二册", "选择性必修第一册", "选择性必修第二册", "选择性必修第三册"]


def scan(source_dir=None, books=None):
    """三项渲染完整性扫描（+ 未闭合块）；返回 {类别: [(book, 行号, 片段)…]}，报告走 stderr。"""
    if not source_dir:
        raise ValueError("scan() 需要 source_dir（参数化注入）")
    books = books or BOOKS
    issues = {"行内游离$$": [], "奇数$行": [], "块内奇数$": []}

    for book in books:
        path = os.path.join(source_dir, book, "markdown.md")
        lines = open(path, encoding="utf-8").read().split("\n")
        in_block = False
        block_start = 0
        for i, ln in enumerate(lines, 1):
            s = ln.strip()
            # 去 alt 注释后统计
            body = re.sub(r"<!--\s*alt:.*?-->", "", ln)
            if s == "$$":
                in_block = not in_block
                if in_block:
                    block_start = i
                continue
            # 行内游离 $$（不是独立成行的 $$）
            if "$$" in body:
                issues["行内游离$$"].append((book, i, ln.strip()[:150]))
            # 奇数 $（行内公式不配对）
            if body.count("$") % 2 == 1:
                issues["奇数$行"].append((book, i, ln.strip()[:150]))
            # 块内行的 $ 也应为偶数（块公式是裸 LaTeX，不含 $）
            if in_block and body.count("$") % 2 == 1:
                issues["块内奇数$"].append((book, i, ln.strip()[:150]))
        if in_block:
            issues.setdefault("未闭合块", []).append((book, block_start, ""))
    for k, v in issues.items():
        print("=== %s: %d 处 ===" % (k, len(v)), file=sys.stderr)
        for book, i, txt in v[:15]:
            print("  %s L%d: %s" % (book, i, txt), file=sys.stderr)
        print(file=sys.stderr)
    return issues


if __name__ == "__main__":
    import argparse
    _p = argparse.ArgumentParser(description="渲染完整性扫描（tbp run 质量门内核）")
    _p.add_argument("--source", required=True, help="final 目录")
    _p.add_argument("books", nargs="*", help="册名列表，缺省为默认五册")
    _a = _p.parse_args()
    scan(source_dir=_a.source, books=_a.books or None)
