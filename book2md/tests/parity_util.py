# -*- coding: utf-8 -*-
"""对账工具：把"引擎有意演进"与"意外改动"区分开。

两个对账测试（merge 抽取合并、rules 五册行为保持）都以历史产物为基准逐字节比对。
引擎有意演进的差异必须逐行登记在 `fixtures/parity_delta_allowlist.json`：

    {"rules": {"<册名>": [{"old": 历史行, "new": 引擎行}, ...]},
     "merge": {"<册名>": [...]}}

除登记项外的任何差异（含行数变化、缩进/标点级改动）一律判失败。
"""
import difflib
import json
import os

ALLOWLIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "fixtures", "parity_delta_allowlist.json")


def load_allowlist():
    if not os.path.isfile(ALLOWLIST_PATH):
        return {}
    with open(ALLOWLIST_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def collect_delta(got, want):
    """按行比对，返回 (pairs, structural)。

    pairs: 1:1 替换行对 [(历史行, 引擎行)]
    structural: 无法用 1:1 行对描述的变更（增删行、块重排等）描述串列表
    """
    a = want.decode("utf-8").splitlines()
    b = got.decode("utf-8").splitlines()
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    pairs, structural = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace" and (i2 - i1) == (j2 - j1):
            pairs.extend((a[i1 + k], b[j1 + k]) for k in range(i2 - i1))
        else:
            structural.append("%s: 历史 %d 行 -> 引擎 %d 行（首行 %r）"
                              % (tag, i2 - i1, j2 - j1,
                                 (a[i1] if i1 < len(a) else "")[:100]))
    return pairs, structural


def unexpected_delta(got, want, suite, book):
    """返回未登记差异描述；全部已登记则返回 None。"""
    allow = {(d["old"], d["new"]) for d in load_allowlist().get(suite, {}).get(book, [])}
    pairs, structural = collect_delta(got, want)
    bad = list("  " + s for s in structural)
    bad.extend("  第 %d 处未登记: %r" % (n + 1, new[:140])
               for n, (old, new) in enumerate(pairs) if (old, new) not in allow)
    return "\n".join(bad) if bad else None
