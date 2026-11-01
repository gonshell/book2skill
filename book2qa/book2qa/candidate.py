# -*- coding: utf-8 -*-
"""核心层：知识点候选切分（S1-3，人在环：机器出初稿，人裁边界与命名）。

拆并规则表（对照必修一 55 单元实测数据，2026-11-01）：
  纯壳   节有子节且自身教学行 ≤10           → 不出候选（行已归子节）
  拆分   单元 >90 行 或 >4500 字 且有编号项 → 按编号项拆（每项一候选）
  报警   大而无编号项                       → granularity_oversize（不猜，交人裁）
  合并   单元 <25 行 且 <3 题               → 并入同父相邻单元（后者优先）
  类型   词面启发式 application>method>theorem>concept；skill 给不出 → 报警留人工

id 稳定性（graph-spec §4）：M1-C{ch}-S{b}[A-Z]-K{nn}；nn 由
「单元排序 + 段内顺序」确定性推出，同输入同 id。
"""
import collections
import re

TEACH_KINDS = ("正文", "思考", "观察", "探究", "归纳", "小结",
               "阅读与思考", "探究与发现", "信息技术应用")
EXERCISE_KINDS = ("练习", "习题", "复习巩固", "综合运用", "拓广探索")

SPLIT_LINES = 90      # 单元教学行超此值且有编号项 → 拆
SPLIT_CHARS = 4500
MERGE_LINES = 25      # 教学行低于此 且 题 <3 → 并邻
MERGE_MIN_EX = 3
SHELL_LINES = 10      # 纯壳节判定（有子节的节）

TITLE_TYPE_RULES = (
    ("application", ("应用", "模型")),
    ("method", ("判定", "判断", "求解", "解法", "方法", "画", "作图", "表示法", "表示")),
    ("theorem", ("性质", "定理", "公式", "图象", "运算",
                 "单调", "奇偶", "周期", "对称", "有界", "诱导")),
    ("concept", ("定义", "概念", "集合", "函数", "角", "条件", "量词", "充分", "必要")),
)

ITEM_TITLE_RE = re.compile(r"^(\d+)\s*[\.、]\s*(\S.*)$")
# 题型分组（复习参考题/节末练习的"1. 选择题"）不是知识点，不出候选
QUIZ_GROUP_RE = re.compile(r"^(选择题|填空题|解答题|判断题|多选题)\s*$")


def infer_type(title):
    for t, words in TITLE_TYPE_RULES:
        for w in words:
            if w in title:
                return t
    return "concept"


def _item_sort_key(item_line):
    m = ITEM_TITLE_RE.match(item_line["title"])
    return int(m.group(1)) if m else 999


def _clean_item_title(title):
    m = ITEM_TITLE_RE.match(title)
    return m.group(2).strip() if m else title


def _unit_id_sort(unit):
    rid = unit["id"]
    if rid[0].isdigit():
        return [int(x) for x in rid.split(".")]
    return [99, 99]


def build_candidates(rows, para_meta, paragraphs, exercise_rows):
    """→ (candidates, issues, quota)。全部确定性：同输入同输出。"""
    meta_by = {m["idx"]: m for m in para_meta}
    paras_by_owner = {}
    for p in paragraphs:
        m = meta_by.get(p.idx)
        if not m or not m.get("owner_id"):
            continue
        if m["block_kind"] in TEACH_KINDS:
            paras_by_owner.setdefault(m["owner_id"], []).append(p)

    ex_by_owner = {}
    for r in exercise_rows:
        if r.get("owner_id"):
            ex_by_owner.setdefault(r["owner_id"], []).append(r)

    row_by_id = {r["id"]: r for r in rows}
    # 教学单元：有内容的节/子节
    units = []
    for r in rows:
        if r["kind"] not in ("section", "subsection"):
            continue
        ps = paras_by_owner.get(r["id"], [])
        if not ps:
            continue
        units.append(r)

    # 拆分：大单元按编号项切
    raw = []       # (unit_row, [part])  part = {title, paras, items_line}
    for r in units:
        ps = paras_by_owner.get(r["id"], [])
        n_lines = sum(p.end_line - p.start_line + 1 for p in ps)
        n_chars = sum(len(p.text) for p in ps)
        item_entries = sorted([i for i in r.get("items", [])
                               if i["kind"] == "item" and ITEM_TITLE_RE.match(i["title"])
                               and not QUIZ_GROUP_RE.match(_clean_item_title(i["title"]))],
                              key=_item_sort_key)
        big = n_lines > SPLIT_LINES or n_chars > SPLIT_CHARS
        if big and item_entries:
            # 段落按行号归入编号项
            bounds = [(i["line"], _clean_item_title(i["title"]))
                      for i in item_entries]
            parts = []
            for bline, btitle in bounds:
                parts.append({"title": btitle, "paras": [], "start": bline})
            for p in ps:
                placed = False
                for pt in reversed(parts):
                    if p.start_line >= pt["start"]:
                        pt["paras"].append(p)
                        placed = True
                        break
                if not placed:
                    parts[0]["paras"].insert(0, p)
            raw.append((r, parts))
        else:
            raw.append((r, [{"title": r["title"], "paras": ps, "start": None}]))

    # 合并：过小单元并入同父相邻（后者优先）
    merged_into = {}
    sizes = []
    for r, parts in raw:
        n_lines = sum(p.end_line - p.start_line + 1 for pt in parts
                      for p in pt["paras"])
        n_ex = len(ex_by_owner.get(r["id"], []))
        sizes.append((n_lines, n_ex))
    drop = set()

    def resolve(uid):
        """合并链终解：4.5.1→4.5.2→X 时返回 X（防反向并回已丢弃单元）。"""
        seen = set()
        while uid in merged_into and uid not in seen:
            seen.add(uid)
            uid = merged_into[uid]
        return uid

    for i, (r, parts) in enumerate(raw):
        n_lines, n_ex = sizes[i]
        has_children = any(x.get("parent_id") == r["id"] for x, _ in raw)
        if n_lines < MERGE_LINES and n_ex < MERGE_MIN_EX and not has_children:
            target = None
            if i + 1 < len(raw) and raw[i + 1][0]["id"] not in merged_into \
                    and raw[i + 1][0].get("parent_id") in (
                        r["id"], r.get("parent_id")):
                target = raw[i + 1][0]["id"]
            elif i > 0 and raw[i - 1][0]["id"] not in merged_into \
                    and raw[i - 1][0].get("parent_id") == r.get("parent_id"):
                target = raw[i - 1][0]["id"]
            elif i + 1 < len(raw) and raw[i + 1][0]["id"] not in merged_into:
                target = raw[i + 1][0]["id"]
            if target and target != r["id"]:
                merged_into[r["id"]] = resolve(target)
                drop.add(i)

    # 重分配被并单元的段落与题目
    for src, dst in merged_into.items():
        for i, (r, parts) in enumerate(raw):
            if r["id"] == dst:
                for j, (sr, sparts) in enumerate(raw):
                    if sr["id"] == src:
                        for pt in sparts:
                            if pt["paras"]:
                                parts[-1]["paras"].extend(pt["paras"])
                break

    # 出候选
    cands = []
    issues = []
    counters = {}
    for i, (r, parts) in enumerate(raw):
        if i in drop:
            continue
        # 纯壳跳过
        has_children = any(x.get("parent_id") == r["id"]
                           for x, _ in raw if x["id"] not in merged_into)
        n_lines = sum(p.end_line - p.start_line + 1 for pt in parts
                      for p in pt["paras"])
        if r["kind"] == "section" and has_children and n_lines <= SHELL_LINES:
            issues.append({"code": "granularity_shell_skipped", "unit": r["id"],
                           "detail": "纯壳节 %s %s 不出候选（内容在其子节）"
                                     % (r["id"], r["title"][:20])})
            continue
        is_sub = r["kind"] == "subsection"
        parent = row_by_id.get(r.get("parent_id")) if is_sub else None
        sec_num = (parent["id"] if parent else r["id"])
        sec_title = (parent["title"] if parent else r["title"])
        ch_id = r.get("chapter_id")
        ch_row = next((x for x in rows if x["kind"] == "chapter"
                       and x["id"] == ch_id), None) if ch_id else None
        ch_num = ch_row["chapter_num"] if ch_row else None
        base = "S" + sec_num.split(".", 1)[1]
        if is_sub:
            letter = chr(ord("A") + int(r["id"].split(".")[2]) - 1)
            base += letter
        key = (ch_num, base)   # 子节各有独立 K 序号（graph-spec §4）
        counters.setdefault(key, 0)

        for pt in parts:
            counters[key] += 1
            nn = "%02d" % counters[key]
            cid = "M1-C%s-%s-K%s" % (ch_num, base, nn)
            ps = pt["paras"]
            if not ps:
                continue
            pages = [p.textbook_page for p in ps if p.textbook_page is not None]
            anchors = _make_anchors(ps)
            exs = [{"label": e["label"], "page": e["page"],
                    "quote": e["quote"][:40]}
                   for e in ex_by_owner.get(r["id"], [])]
            title = pt["title"] if pt["title"] != r["title"] else r["title"]
            n_lines_pt = sum(p.end_line - p.start_line + 1 for p in ps)
            alarms = []
            if n_lines_pt > SPLIT_LINES:
                alarms.append("granularity_oversize")
            if n_lines_pt < 15:
                alarms.append("granularity_undersize")
            ctype = infer_type(title)
            cands.append({
                "id": cid, "title": title, "type": ctype,
                "book": "必修第一册",
                "chapter": ch_row["title"] if ch_row else "",
                "section": (sec_num + " " + sec_title),
                "pages": [min(pages), max(pages)] if pages else None,
                "summary": (ps[0].text[:38] + "…") if ps else "",
                "anchors": anchors,
                "exercises": exs,
                "unit": r["id"],
                "status": "unverified", "built_by": "auto",
                "built_at": "",   # 由命令层填
            })
            if n_lines_pt > SPLIT_LINES and not pt.get("start"):
                issues.append({"code": "granularity_oversize", "unit": r["id"],
                               "detail": "候选 %s（%s）教学 %d 行未拆，需人裁"
                                         % (cid, title[:16], n_lines_pt)})

    for c in cands:
        if c["pages"] is None:
            issues.append({"code": "candidate_no_page", "id": c["id"],
                           "detail": "候选 %s %s 无教材页" % (c["id"], c["title"][:16])})
    quota = collections.Counter(c["type"] for c in cands)
    total = len(cands)
    quota_pct = {t: round(100.0 * n / total, 1) for t, n in quota.items()} if total else {}
    return cands, issues, {"total": total, "type_counts": dict(quota),
                           "type_pct": quota_pct,
                           "merged_units": merged_into}


def _make_anchors(paras):
    """前 2 段 + 定义段优先；role 按内容词面。"""
    anchors = []
    seen = set()
    ordered = list(paras)
    defi = next((p for p in ordered
                 if re.search(r"定义|一般地|通常", p.text)), None)
    picks = []
    if defi is not None:
        picks.append(defi)
    for p in ordered:
        if len(picks) >= 3:
            break
        if p not in picks:
            picks.append(p)
    for p in picks[:3]:
        q = re.sub(r"\s+", "", p.text)[:60]
        if q in seen or len(q) < 8:
            continue
        seen.add(q)
        if re.search(r"定义|一般地", p.text):
            role = "definition"
        elif re.search(r"思考|探究|观察|想一想|你能", p.text):
            role = "motivation"
        elif re.search(r"例\d|解[:：]", p.text):
            role = "example"
        else:
            role = "definition"
        anchors.append({"quote": q, "page": p.textbook_page, "role": role,
                        "estimated": p.page_estimated})
    return anchors

