# -*- coding: utf-8 -*-
"""scan_md_preview.py — 用 WorkBuddy 预览同款渲染器规则验收 md。

复刻 markdown-it + markdown-it-texmath(dollars) + KaTeX 的判定规则
（规则来自 node_modules/markdown-it-texmath/texmath.js 源码实证）：

  行内 $...$  : 正则 /\\$((?:[^\\s\\\\])|(?:\\S.*?[^\\s\\\\]))\\$/gy
                → 内容不能以空白开头；不能以空白或反斜杠结尾；
                  长度为 1 时不能是反斜杠。
                 pre : 开 $ 前一个字符不能是数字或反斜杠。
                 post: 闭 $ 后一个字符不能是数字。
  块 $$...$$  : 正则 /\\${2}([^$]*?[^\\\\])\\${2}/gmy
                → 内容不能含 $，且不能以反斜杠结尾；同样受 pre/post 约束。
                $$ 优先于 $ 匹配（math_inline_double 注册在前）。
  KaTeX       : throwOnError=false，语法错误渲染成 katex-error（红色）。

输出每册的问题清单，全零为合格。
"""
import os
import re
import sys

_SRC_DIR = None   # 运行时注入：final 目录（run() 设置）
BOOKS = ["必修第一册", "必修第二册", "选择性必修第一册", "选择性必修第二册", "选择性必修第三册"]


def _is_digit(ch):
    return ch is not None and "0" <= ch <= "9"


def _inline_ok(content):
    """行内公式内容是否满足 texmath 正则"""
    if not content:
        return False
    if content[0] in " \t":
        return False                      # 不能以空白开头
    if content[-1] in " \t" or content[-1] == "\\":
        return False                      # 不能以空白/反斜杠结尾
    if len(content) == 1 and content == "\\":
        return False
    return True


def _block_ok(content):
    """$$ 块内容是否满足 texmath 正则"""
    if "$" in content:
        return False
    if content.endswith("\\"):
        return False
    return True


def _frag(text, a, b):
    """截取 [a,b) 片段，钳制在所在行内，避免跨行误导"""
    ls = text.rfind("\n", 0, a) + 1
    le = text.find("\n", b)
    if le < 0:
        le = len(text)
    return text[ls:le]


def scan_text(text):
    """全文扫描，返回 [(行号, 原因, 片段)]"""
    issues = []
    n = len(text)
    consumed = [False] * n          # 标记已被 $$ 块消费的字符

    # ---- 第一遍：所有 $$ 跨度（多行块 + 行内双联） ----
    i = 0
    while i < n:
        if not text.startswith("$$", i):
            i += 1
            continue
        prev = text[i - 1] if i > 0 else None
        if _is_digit(prev) or prev == "\\":
            issues.append((text[:i].count("\n") + 1, "$$ 前是数字/反斜杠",
                           _frag(text, max(0, i - 12), i + 30)))
            i += 2
            continue
        j = i + 2
        found = None
        while True:
            j = text.find("$$", j)
            if j < 0:
                break
            content = text[i + 2:j]
            if not _block_ok(content):
                j += 2
                continue
            nxt = text[j + 2] if j + 2 < n else None
            if _is_digit(nxt):
                j += 2
                continue
            found = j
            break
        if found is None:
            issues.append((text[:i].count("\n") + 1, "$$ 未闭合",
                           _frag(text, max(0, i - 12), i + 40)))
            i += 2
            continue
        for t in range(i, found + 2):
            consumed[t] = True
        i = found + 2

    # ---- 第二遍：行内 $...$（跳过已消费区） ----
    # 精确复刻粘性正则语义：\$(...)\$ 用懒惰匹配只取**最短**合法内容；
    # 正则匹配成功后，post 条件（闭 $ 后不能是数字）独立检查，失败则整个
    # 规则作废（$ 退化为文本，指针只前进 1 字符），绝不向后找更远的闭合 $。
    pos = 0
    while pos < n:
        if text[pos] != "$" or consumed[pos]:
            pos += 1
            continue
        prev = text[pos - 1] if pos > 0 else None
        if _is_digit(prev) or prev == "\\":
            issues.append((text[:pos].count("\n") + 1, "$ 前是数字/反斜杠",
                           _frag(text, max(0, pos - 14), pos + 30)))
            pos += 1
            continue
        # 正则部分：找最短的合法闭合 $
        j = pos + 1
        found = None
        while j < n:
            if consumed[j]:
                j += 1
                continue
            if text[j] == "$" and _inline_ok(text[pos + 1:j]):
                found = j
                break
            j += 1
        if found is None:
            issues.append((text[:pos].count("\n") + 1, "$ 正则无匹配（退化为文本）",
                           _frag(text, max(0, pos - 14), pos + 40)))
            pos += 1
            continue
        # post 条件：独立检查，失败则规则作废
        nxt = text[found + 1] if found + 1 < n else None
        if _is_digit(nxt):
            issues.append((text[:pos].count("\n") + 1, "闭 $ 后紧跟数字（规则作废）",
                           _frag(text, max(0, pos - 14), found + 12)))
            pos += 1
            continue
        pos = found + 1
    return issues


def scan_book(book):
    path = os.path.join(_SRC_DIR, book, "markdown.md")
    md = open(path, encoding="utf-8").read()
    # 去掉 alt/HTML 注释行（不参与渲染判定）
    lines = [l for l in md.split("\n") if not l.strip().startswith("<!--")]
    return scan_text("\n".join(lines))


def run(source_dir=None, books=None):
    """行为保持版入口（自 main() 参数化）。

    source_dir: final 目录；返回 {"per_book": {book: 命中数}, "total": 总数}，报告走 stderr。
    """
    global _SRC_DIR
    if not source_dir:
        raise ValueError("run() 需要 source_dir（参数化注入）")
    _SRC_DIR = source_dir
    # books 参数优先（空则回退默认五册）；不得按 BOOKS 白名单过滤——
    # 否则任意册名（新科目接入）会被静默丢弃、回落成全五册扫描
    only = list(books) if books else BOOKS
    grand = 0
    per = {}
    for book in only:
        issues = scan_book(book)
        per[book] = len(issues)
        print("===== %s：%d 处 =====" % (book, len(issues)), file=sys.stderr)
        for ln, why, frag in issues[:40]:
            print("  L%d [%s] %r" % (ln, why, frag[:90]), file=sys.stderr)
        if len(issues) > 40:
            print("  …… 其余 %d 处从略" % (len(issues) - 40), file=sys.stderr)
        grand += len(issues)
    print(file=sys.stderr)  # 空行分隔（对齐原 main 的 stdout 行为，改走 stderr）
    print("总计：%d 处" % grand, file=sys.stderr)
    return {"per_book": per, "total": grand}


if __name__ == "__main__":
    import argparse
    _p = argparse.ArgumentParser(description="texmath dollars 语义验收扫描（tbp run 质量门内核）")
    _p.add_argument("--source", required=True, help="final 目录")
    _p.add_argument("books", nargs="*", help="册名列表，缺省为默认五册")
    _a = _p.parse_args()
    run(source_dir=_a.source, books=_a.books or None)
