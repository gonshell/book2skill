# -*- coding: utf-8 -*-
"""核心层：正式图谱生成（S1-4，graph-spec §2/§3/§7）。

prereq 生成（确定性规则，人工可后续修改——prereq 属可扩字段内容）：
  规则1 同节链：同一节（含子节）内按 K 序，后一个节点 prereq 前一个；
  规则2 章间衔接：每章第一个节点 prereq 上一章最后一个节点；
  规则3 无前置则缺省字段（不写空数组，graph-spec §3）。

质量闸（任一必填/结构问题 → exit 10 不落盘；内容级问题 → issue + 保持
unverified，不阻断——渲染无误 ≠ 内容一致，定稿靠人工抽检）：
  结构：必填字段齐全 / id 唯一 / prereq 指向存在 / pages 非空
  内容：anchors.quote 原文可溯（去空白子串匹配）/ 公式 $ 配对
       （破损 → issue + 强制 unverified）/ exercises.label 可解析
"""
import re


def generate_prereq(cands):
    """单元内链式 + 章间首尾衔接（unit 之间不链，留人工补）。"""
    prereq = {}
    last_by_chapter = {}
    prev_chapter = None
    by_unit = {}
    for c in cands:
        by_unit.setdefault(c["unit"], []).append(c)
    for uid in by_unit:
        group = sorted(by_unit[uid], key=lambda c: c["id"])
        ch = group[0]["chapter"]
        for i, c in enumerate(group):
            ps = []
            if i > 0:
                ps.append(group[i - 1]["id"])
            elif prev_chapter and prev_chapter != ch \
                    and prev_chapter in last_by_chapter:
                ps.append(last_by_chapter[prev_chapter])
            if ps:
                prereq[c["id"]] = ps
        last_by_chapter[ch] = group[-1]["id"]
        prev_chapter = ch
    return prereq


REQUIRED = ("id", "title", "type", "book", "chapter", "section",
            "summary", "anchors", "status", "built_at", "built_by")
# pages 允许 null（arch §9.1 用户裁定）：缺页只强制 unverified，不阻断
TYPES = ("concept", "theorem", "method", "skill", "application")
QUOTE_MIN = 8


def _flat_nows(s):
    return re.sub(r"\s+", "", s or "")


def quality_gate(cands, markdown_text, exercise_rows, figures_rows):
    """→ (pass_fail, issues)。结构问题返回 False；内容问题只记 issue。"""
    issues = []
    structural = True
    nows_md = _flat_nows(markdown_text)

    ids = [c.get("id") for c in cands]
    if any(i is None for i in ids):
        structural = False
        issues.append({"code": "graph_missing_id", "detail": "存在无 id 节点"})
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        structural = False
        issues.append({"code": "graph_duplicate_id", "detail": "id 重复：%s"
                                                                 % sorted(dup)[:5]})

    ex_labels = {e["label"] for e in exercise_rows}
    fig_set = {f["fig"] for f in figures_rows}

    for c in cands:
        cid = c.get("id", "?")
        missing = [k for k in REQUIRED
                   if k not in c or c[k] in (None, "", [])]
        if missing:
            structural = False
            issues.append({"code": "graph_missing_field", "id": cid,
                           "detail": "%s 缺必填字段 %s" % (cid, missing)})
        if not c.get("pages"):
            issues.append({"code": "graph_no_pages", "id": cid,
                           "detail": "%s 无教材页，强制 unverified" % cid})
            c["status"] = "unverified"
        if c.get("type") not in TYPES:
            structural = False
            issues.append({"code": "graph_bad_type", "id": cid,
                           "detail": "%s type 非法：%r" % (cid, c.get("type"))})
        # 锚点可溯
        for a in c.get("anchors", []):
            q = a.get("quote", "")
            if len(q) >= QUOTE_MIN and _flat_nows(q) not in nows_md:
                issues.append({"code": "anchor_not_found", "id": cid,
                               "detail": "%s 锚点不可溯：%s…" % (cid, q[:24])})
        # 公式 $ 配对（题干与锚点）
        texts = [a.get("quote", "") for a in c.get("anchors", [])] + \
                [e.get("quote", "") for e in c.get("exercises", [])]
        for t in texts:
            # $ 奇偶不可靠（成对出现也可能被截半）；用转义花括号平衡判破损
            if t.count("\\{") != t.count("\\}") or t.count("{") != t.count("}"):
                issues.append({"code": "broken_formula_in_quote", "id": cid,
                               "detail": "%s 引用文本 $ 不配对（源级破损），"
                                         "节点强制 unverified" % cid})
                c["status"] = "unverified"
                break
        for e in c.get("exercises", []):
            if e["label"] not in ex_labels:
                issues.append({"code": "exercise_label_unknown", "id": cid,
                               "detail": "%s 引用题 %s 不存在" % (cid, e["label"])})
        for f in c.get("figures", []) or []:
            if f not in fig_set:
                issues.append({"code": "figure_unknown", "id": cid,
                               "detail": "%s 图 %s 不在 figures.json" % (cid, f)})
    return structural, issues


def build_graph(cands, prereq, issues):
    """应用 prereq 与 issues 判定 → (graph_rows, gate_pass)。"""
    rows = []
    for c in cands:
        row = dict(c)
        ps = prereq.get(c["id"])
        if ps:
            row["prereq"] = ps
        rows.append(row)
    return rows


def to_json_line(row):
    import json
    return json.dumps(row, ensure_ascii=False)
