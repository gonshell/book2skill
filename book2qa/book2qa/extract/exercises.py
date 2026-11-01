# -*- coding: utf-8 -*-
"""核心层：题目抽取（S1-2b，graph-spec §5.1 exercises 题目层）。

来源（v1 范围）：练习 / 习题 / 复习巩固 / 综合运用 / 拓广探索 五个提问块内的
主编号题（`1.`/`1、`）与小题（`(1)`），以及正文中的 `例N`。
章末复习参考题不入 v1（结构行 items 已留痕，S2+ 可扩）。

规则：
  主编号   `^\\d+[.、]`   → 新题
  小题     `^(\\d+)`      → 挂当前题 parts；无当前题则自立行
  续段     题干跨页/多段   → 挂 cont（练习块内）或以 解/分析/证明 开头（例题）
  例N      `^例\\d+`      → 新题（正文块内）
任何文本都不丢弃：进不了题的段落报 issue 留查（内容仍在 markdown）。
"""
import re

MAIN_RE = re.compile(r"^(\d{1,3})\s*[\.、]\s*(\S.*)$", re.S)
SUB_RE = re.compile(r"^[\(（]\s*(\d{1,3})\s*[\)）]\s*(\S.*)$", re.S)
EXAMPLE_RE = re.compile(r"^例\s*(\d{1,3})\s*[\.、：:]?\s*(\S.*)$", re.S)
SOLUTION_RE = re.compile(r"^(解|分析|证明|反思|探究|方法)", re.S)
EXERCISE_BLOCKS = ("练习", "习题", "复习巩固", "综合运用", "拓广探索")


def extract(paragraphs, para_meta):
    """(paragraphs, para_meta) → (rows, issues)。行序单趟。"""
    meta = {m["idx"]: m for m in para_meta}
    rows = []
    issues = []
    cur = None            # 当前开放题
    in_ex_block = False   # 练习块续段开关
    seq = 0

    def new_row(p, m, block, num, sub=None, quote=None):
        nonlocal seq
        seq += 1
        tb = p.textbook_page
        label_num = ("(%d)" % sub) if sub else (str(num) if num is not None else "?")
        label = "P%s %s%s" % (tb if tb is not None else "?", block, label_num)
        if tb is None:
            issues.append({"code": "exercise_no_page", "seq": seq,
                           "detail": "%s 无教材页（段落未锚定）" % label})
        row = {"seq": seq, "label": label, "num": num, "sub": sub,
               "block_kind": block, "owner_id": m["owner_id"] if m else None,
               "page": tb, "physical_page": p.physical_page,
               "quote": quote if quote is not None else p.text.strip(),
               "quote_plain": None, "cont": [], "parts": [],
               "lines": [p.start_line, p.end_line]}
        rows.append(row)
        return row

    for p in paragraphs:
        m = meta.get(p.idx)
        kind = m["block_kind"] if m else "正文"
        owner = m["owner_id"] if m else None
        text = p.text.strip()
        if not text:
            continue
        if kind in ("标题", "块标题", "noise"):
            continue  # 块标记/噪音段不是题目内容
        first = text.split("\n")[0].strip()

        if kind in EXERCISE_BLOCKS:
            mm = MAIN_RE.match(text)
            sm = SUB_RE.match(text)
            if mm and (not sm or mm.start(1) < sm.start(1)):
                cur = new_row(p, m, kind, int(mm.group(1)),
                              quote=text)
                in_ex_block = True
                continue
            if sm:
                if cur is not None and in_ex_block and cur["num"] is not None:
                    cur["parts"].append({"sub": int(sm.group(1)),
                                         "quote": text})
                    cur["lines"][1] = p.end_line
                else:
                    cur = new_row(p, m, kind, None, sub=int(sm.group(1)),
                                  quote=text)
                    in_ex_block = True
                continue
            if in_ex_block and cur is not None:
                cur["cont"].append(text)
                cur["lines"][1] = p.end_line
                continue
            issues.append({"code": "exercise_orphan_text",
                           "line": p.start_line,
                           "detail": "练习块内无主编号且无开放题：%r" % first[:40]})
            continue

        if kind not in EXERCISE_BLOCKS and kind not in ("章末栏目",):
            # 例题紧跟「思考/观察/探究」等提问块出现（教材结构：思考→例题→练习），
            # 因此例N 抽取范围 = 除练习五块与章末栏目外的一切内容块。
            em = EXAMPLE_RE.match(text)
            if em:
                cur = new_row(p, m, "例", int(em.group(1)),
                              quote=text)
                in_ex_block = False
                continue
            if cur is not None and cur["block_kind"] == "例" \
                    and cur["owner_id"] == owner and SOLUTION_RE.match(text):
                cur["cont"].append(text)
                cur["lines"][1] = p.end_line
                continue
            cur = None
            in_ex_block = False
            continue

        # 练习块 / 章末栏目：例题链保持，练习链断
        if cur is not None and cur["block_kind"] != "例":
            cur = None
            in_ex_block = False

    return rows, issues


def to_json_line(row):
    import json
    return json.dumps(row, ensure_ascii=False)
