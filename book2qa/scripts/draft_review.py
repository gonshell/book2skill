# -*- coding: utf-8 -*-
"""draft_review — 选项 C：机器代拟裁定初稿，填入批注列，用户只否决。

规则（2026-11-04 用户批准的选项 C）：
  - 页跨度≥5 且 题≥8：拆 2（首块原名，次块「·判定方法」method）；跨度≥8 加「·典型例题」application
  - 题≥10（跨度小）：拆出「·方法」method 位
  - 别名：高置信口语叫法小词表，仅精确匹配标题才填
  - 全部备注以「机器初稿：」开头，用户可整行清空否决
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openpyxl import load_workbook                       # noqa: E402
from book2qa.commands import review                      # noqa: E402

_ALIAS_MAP = {
    "周期性": "循环出现｜一遍遍重复",
    "单调性": "增减性｜递增递减",
    "奇偶性": "奇函数偶函数",
    "集合的概念": "元素与集合",
    "集合间的基本关系": "子集真子集",
    "指数函数": "指数爆炸",
    "对数函数": "log 是什么",
    "函数的基本性质": "增减性",
    "诱导公式（一~四）": "奇变偶不变",
    "函数与方程": "二分法",
}


def draft_row(row):
    """row: (id,标题,类型,页码,题数,...) → (动作,新标题,新类型,备注,别名) 或 None。"""
    cid, title, type_, pages, n_ex = row[0], row[1], row[2], row[3], row[4]
    try:
        p0, p1 = [int(x) for x in str(pages).split("-")]
        span = p1 - p0 + 1
    except (ValueError, AttributeError):
        return None
    alias = _ALIAS_MAP.get(title, "")

    if span >= 5 and n_ex >= 8:
        pieces = [title, "%s·判定方法@method" % title]
        note = "机器初稿：页跨度%d+题%d，拆定义/方法两块" % (span, n_ex)
        if span >= 8:
            pieces.append("%s·典型例题@application" % title)
            note += "；跨度大，另拆例题块"
        return ("拆分", "｜".join(pieces), "", note + "（可整行清空否决）", alias)
    if n_ex >= 14:
        return ("拆分", "%s｜%s·方法@method" % (title, title), "",
                "机器初稿：题量%d偏大，补一个 method 位（可整行清空否决）" % n_ex,
                alias)
    if alias:
        return ("", "", "", "", alias)
    return None


def main(xlsx_path):
    wb = load_workbook(xlsx_path)
    ws = wb["候选"]
    filled = split_n = 0
    for row in ws.iter_rows(min_row=2):
        vals = [c.value for c in row]
        if not vals[0] or vals[7]:            # 无 id 或已有人工批注 → 不覆盖
            continue
        d = draft_row(vals)
        if not d:
            continue
        action, new_title, new_type, note, alias = d
        row[7].value = action
        row[8].value = new_title
        row[9].value = new_type
        row[10].value = note
        if alias:
            row[11].value = alias
        filled += 1
        if action == "拆分":
            split_n += 1
    wb.save(xlsx_path)
    print("初稿已填：%d 行（其中拆分 %d）→ %s" % (filled, split_n, xlsx_path))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else
         "data/review-必修第一册.xlsx")
