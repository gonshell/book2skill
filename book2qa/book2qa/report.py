# -*- coding: utf-8 -*-
"""核心层：build_report.md 生成（所有降级的唯一人类出口）。

原则（arch.md）：任何模块不许自己 print；stderr 不是真相源——
一切待确认项都进本报告，按 issue.code 分组。
"""
import collections
import json
import os
import time

_CODE_TITLES = {
    "page_marks_absent": "页界标记缺失",
    "page_offset_ambiguous": "页偏移歧义（取首对齐，待查）",
    "page_offset_invalid": "页偏移无法换算",
    "page_offset_inconsistent": "偏移下越界图片",
    "block_no_images": "块内无图片（段落页码为继承估计）",
    "image_outside_block": "首块前存在图片引用",
    "chapter_unnamed": "章名缺失（无续行可合并）",
    "chapter_section_mismatch": "节号与所在章不符",
    "subsection_orphan": "子节父节缺失或错位",
    "exercise_no_page": "题目无教材页",
    "exercise_orphan_text": "练习块内未编号段落",
    "figure_no_page": "图号锚定行无物理页",
    "figure_no_file": "图号 ±1 页无图片文件",
    "file_no_ref": "未被图号引用的图片（汇总）",
    "formulas_plain_failed": "公式 plain 转换失败（源级 $ 配对破损）",
}


def render(issues, stats):
    """(issues, stats) → markdown 文本。"""
    out = ["# build_report.md — book2qa 建库待确认清单",
           "",
           "> 生成时间：%s。本报告是全部降级与待确认项的**唯一**出口；" % time.strftime("%Y-%m-%d %H:%M"),
           "> 未出现在此报告的内容视为机器有把握项。人工复核通过前产物不得定稿（AGENT.md 口径）。",
           ""]

    out.append("## 一、总量统计\n")
    out.append("| 项 | 值 |\n|---|---|")
    for k, v in stats.items():
        out.append("| %s | %s |" % (k, v))
    out.append("")

    by_code = collections.Counter(i["code"] for i in issues)
    out.append("## 二、待确认项（%d 条，%d 类）\n" % (len(issues), len(by_code)))
    if not issues:
        out.append("（无）\n")
    for code, n in by_code.most_common():
        out.append("### %s — %s（%d 条）\n" % (code, _CODE_TITLES.get(code, code), n))
        for i in [x for x in issues if x["code"] == code][:50]:
            out.append("- %s" % i.get("detail", json.dumps(i, ensure_ascii=False)))
        if n > 50:
            out.append("- ……（其余 %d 条见信封 issues 字段）" % (n - 50))
        out.append("")
    return "\n".join(out)


def write_report(workspace, issues, stats):
    path = os.path.join(workspace, "data", "build_report.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render(issues, stats))
    return path
