# -*- coding: utf-8 -*-
"""review — 裁定辅助（M3-1，方案 2026-11-04 经用户批准）。

candidates.jsonl ↔ Excel 双向：人在 Excel 里批注（动作/新标题/新类型/备注），
机器执行拆并改名并产出 diff 报告。动作枚举：
  （空）保持 ｜ 改名 ｜ 拆分 ｜ 并入 ｜ 改类型 ｜ 删除
拆分：新标题列用「｜」分隔 2–4 个新标题，首个顶替原 id，其余生成新 id；
并入：新标题列填目标候选 id，本条的 anchors/exercises 合并进目标后删除本条。
导入后重算 prereq（graph.generate_prereq），保证前置链一致。
"""
import json
import os

from book2qa import paths
from book2qa.envelope import emit
from book2qa.exit_codes import EXIT_OK, EXIT_MISSING, EXIT_USAGE

ACTIONS = ("", "改名", "拆分", "并入", "改类型", "删除")
TYPES = ("concept", "theorem", "method", "skill", "application")
SPLIT_SEP = "｜"

_COLS = ["id", "标题", "类型", "页码", "题数", "unit", "机器建议",
         "动作", "新标题", "新类型", "备注"]


# ── 导出 ──────────────────────────────────────────────────
def export_xlsx(cands, out_path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "候选"
    ws.append(_COLS)
    head_fill = PatternFill("solid", fgColor="D9E2F3")
    warn_fill = PatternFill("solid", fgColor="FCE4D6")
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = head_fill

    for r in cands:
        n_ex = len(r.get("exercises") or [])
        pages = r.get("pages") or [None, None]
        span = (pages[1] - pages[0] + 1) if pages and pages[0] is not None else 0
        advice = []
        if span >= 5 and n_ex >= 8:
            advice.append("页跨度%d+题%d：建议拆 2–3 个（定义/判定/方法分开）"
                          % (span, n_ex))
        elif n_ex >= 10:
            advice.append("题量%d：可拆出一个 method 位" % n_ex)
        if not r.get("aliases"):
            advice.append("aliases 空：建议补口语叫法")
        row = [r["id"], r["title"], r["type"],
               "%s-%s" % tuple(pages) if pages[0] is not None else "",
               n_ex, r.get("unit", ""), "；".join(advice),
               "", "", "", ""]          # 用户四列留空
        ws.append(row)
        if advice:
            for cell in ws[ws.max_row]:
                cell.fill = warn_fill

    # 使用说明 sheet
    ws2 = wb.create_sheet("说明")
    ws2.append(["裁定动作说明"])
    for line in (
        "动作列只允许：改名 / 拆分 / 并入 / 改类型 / 删除，留空=保持",
        "改名：新标题列填新名字（用学生的说法）",
        "拆分：新标题列填 2–4 个新标题，用「%s」分隔；首个沿用原 id" % SPLIT_SEP,
        "并入：新标题列填目标候选 id（本条的题和锚点并入对方）",
        "改类型：新类型列填 concept/theorem/method/skill/application",
        "橙色行 = 机器建议关注（页跨度过大/题量密集/缺别名），仅供参考",
        "目标：总节点 72–88；method 占比 25–30%",
    ):
        ws2.append([line])
    wb.save(out_path)
    return out_path


# ── 导入 ──────────────────────────────────────────────────
def import_xlsx(xlsx_path):
    """读回 Excel → (动作列表, errors)。动作列表供 apply_actions 使用。"""
    from openpyxl import load_workbook
    ws = load_workbook(xlsx_path)["候选"]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    acts, errors = [], []
    for vals in rows:
        vals = list(vals) + [""] * (len(_COLS) - len(vals))
        cid, action, new_title, new_type = vals[0], vals[7], vals[8], vals[9]
        if not cid:
            continue
        action = (action or "").strip()
        if not action:
            continue                      # 留空 = 保持，不记动作
        if action not in ACTIONS:
            errors.append("%s 动作非法：%r（允许：%s）"
                          % (cid, action, "/".join(filter(None, ACTIONS))))
            continue
        if action in ("改名", "拆分", "并入") and not (new_title or "").strip():
            errors.append("%s 动作=%s 但新标题列为空" % (cid, action))
            continue
        if action == "改类型" and (new_type or "").strip() not in TYPES:
            errors.append("%s 新类型非法：%r" % (cid, new_type))
            continue
        acts.append({"id": cid, "action": action,
                     "new_title": (new_title or "").strip(),
                     "new_type": (new_type or "").strip(),
                     "note": (vals[10] or "").strip()})
    return acts, errors


def apply_actions(cands, acts):
    """执行动作 → (新 cands, diff 报告行)。导入后由调用方重算 prereq。"""
    by_id = {c["id"]: c for c in cands}
    diff, dropped, used_k = [], set(), {}

    def next_k(base):
        used_k[base] = used_k.get(base, 0) + 1
        return "%s-K%02d" % (base, used_k[base])

    # 先算最大 K 序号（新拆分节点接着排）
    for c in cands:
        parts = c["id"].rsplit("-K", 1)
        if len(parts) == 2:
            base, k = parts[0], int(parts[1])
            used_k[base] = max(used_k.get(base, 0), k)

    for a in acts:
        c = by_id.get(a["id"])
        if c is None:
            diff.append({"id": a["id"], "what": "SKIP",
                         "detail": "id 不存在（可能已被并入/删除）"})
            continue
        act = a["action"]
        if act == "改名":
            old = c["title"]
            c["title"] = a["new_title"]
            c["built_by"] = "auto+review"
            diff.append({"id": c["id"], "what": "改名",
                         "detail": "%r → %r" % (old, c["title"])})
        elif act == "改类型":
            c["type"] = a["new_type"]
            c["built_by"] = "auto+review"
            diff.append({"id": c["id"], "what": "改类型",
                         "detail": "→ " + c["type"]})
        elif act == "删除":
            dropped.add(c["id"])
            diff.append({"id": c["id"], "what": "删除",
                         "detail": "%s（%s）" % (c["title"], a["note"])})
        elif act == "并入":
            target = by_id.get(a["new_title"])
            if target is None or target["id"] == c["id"]:
                diff.append({"id": c["id"], "what": "SKIP",
                             "detail": "并入目标 %r 不存在" % a["new_title"]})
                continue
            target["exercises"] = (target.get("exercises") or []) + \
                (c.get("exercises") or [])
            target["anchors"] = (target.get("anchors") or []) + \
                (c.get("anchors") or [])
            target["built_by"] = "auto+review"
            dropped.add(c["id"])
            diff.append({"id": c["id"], "what": "并入",
                         "detail": "→ %s（题 %d 条随迁）"
                                   % (target["id"], len(c.get("exercises") or []))})
        elif act == "拆分":
            titles = [t.strip() for t in a["new_title"].split(SPLIT_SEP)
                      if t.strip()]
            if len(titles) < 2:
                diff.append({"id": c["id"], "what": "SKIP",
                             "detail": "拆分至少 2 个新标题（「%s」分隔）" % SPLIT_SEP})
                continue
            base = c["id"].rsplit("-K", 1)[0]
            old_title = c["title"]
            c["title"], c["built_by"] = titles[0], "auto+review"
            diff.append({"id": c["id"], "what": "拆分",
                         "detail": "%r → 首块 %r" % (old_title, titles[0])})
            for t in titles[1:]:
                nid = next_k(base)
                import copy
                nc = copy.deepcopy(c)
                nc["id"], nc["title"] = nid, t
                nc["exercises"], nc["anchors"] = [], []
                by_id[nid] = nc
                diff.append({"id": nid, "what": "拆分新增",
                             "detail": "%r（自 %s 拆出）" % (t, c["id"])})

    # 保序：原顺序的存活者 + 新拆分节点按 id 排在末尾
    seen, ordered = set(), []
    for c in cands:
        if c["id"] in by_id and c["id"] not in dropped:
            ordered.append(by_id[c["id"]])
            seen.add(c["id"])
    ordered += [by_id[i] for i in sorted(by_id)
                if i not in seen and i not in dropped]
    return ordered, diff


# ── 命令入口 ──────────────────────────────────────────────
def _load_cands(workspace):
    path = os.path.join(paths.data_dir(workspace), "candidates.jsonl")
    if not os.path.isfile(path):
        return None, path
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()], path


def _quota(cands):
    n = len(cands) or 1
    from collections import Counter
    tc = Counter(c["type"] for c in cands)
    return {"total": len(cands),
            "types": {t: round(100.0 * tc.get(t, 0) / n, 1)
                      for t in TYPES}}


def cmd_export(args, t0):
    workspace = paths.resolve_workspace(args)
    cands, path = _load_cands(workspace)
    if cands is None:
        return emit("review-export", EXIT_MISSING, workspace=workspace,
                    error="candidates.jsonl 不存在（先跑 build --stage=candidates）：%s"
                          % path, t0=t0)
    out = args.out or os.path.join(paths.data_dir(workspace),
                                   "review-%s.xlsx" % args.book)
    export_xlsx(cands, out)
    return emit("review-export", EXIT_OK, workspace=workspace, book=args.book,
                artifacts={"xlsx": out}, t0=t0,
                extra={"candidates": len(cands),
                       "attention": sum(1 for c in cands
                                        if (c.get("pages") or [0, 0])[0]
                                        and c["pages"][1] - c["pages"][0] >= 5
                                        and len(c.get("exercises") or []) >= 8)})


def cmd_import(args, t0):
    workspace = paths.resolve_workspace(args)
    cands, path = _load_cands(workspace)
    if cands is None:
        return emit("review-import", EXIT_MISSING, workspace=workspace,
                    error="candidates.jsonl 不存在：%s" % path, t0=t0)
    if not os.path.isfile(args.file):
        return emit("review-import", EXIT_MISSING, workspace=workspace,
                    error="批注文件不存在：%s" % args.file, t0=t0)
    acts, errors = import_xlsx(args.file)
    if errors:
        return emit("review-import", EXIT_USAGE, workspace=workspace,
                    error="批注校验失败（未执行任何变更）", issues=[
                        {"code": "review_invalid_action", "detail": e}
                        for e in errors], t0=t0)
    new_cands, diff = apply_actions(cands, acts)
    # prereq 重算（拆并后前置链保持一致；graph 层规则复用）
    from book2qa.graph import generate_prereq
    prereq = generate_prereq(new_cands)
    for c in new_cands:
        c["prereq"] = prereq.get(c["id"], [])

    result = {"changed": sum(1 for d in diff if d["what"] != "SKIP"),
              "diff": diff, "quota": _quota(new_cands)}
    if args.apply:
        with open(path, "w", encoding="utf-8") as f:
            for c in new_cands:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        result["written_to"] = path
        result["note"] = "已写回；下一步：b2q build --stage=graph 重建图谱"
    else:
        result["note"] = "预览模式（未写回）；确认后加 --apply 执行"
    return emit("review-import", EXIT_OK, workspace=workspace, book=args.book,
                t0=t0, extra=result)
