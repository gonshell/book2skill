# -*- coding: utf-8 -*-
"""b2q recall — 四路召回（R4 预留）+ RRF + 兜底，信封按 skill-io §1.1。"""
import os
import sys
import time

from book2qa import paths, retrieval
from book2qa.envelope import emit
from book2qa.exit_codes import EXIT_MISSING, EXIT_OK, EXIT_USAGE

QUOTE_BUDGET = 1200      # skill-io §3 token 预算：教材原文块
TOP_N = 5

_SENT_END = "。！？；"


def _cut_sentence(text, limit):
    """预算内截断到**句子边界**（实测教训：硬切把 P77 定义句切成两半，
    模型只能拿到半句原文）。窗口内无句末标点才整段截断。"""
    if len(text) <= limit:
        return text
    window = text[:limit]
    cut = max(window.rfind(ch) for ch in _SENT_END)
    if cut <= 0:
        return window
    return window[:cut + 1]


def _load(workspace):
    d = paths.data_dir(workspace)
    rows = {}
    for name in ("graph", "structure", "para_meta", "exercises"):
        rows[name] = source_jsonl(os.path.join(d, name + ".jsonl"))
    return rows


def source_jsonl(path):
    out = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    out.append(json_loads(ln))
    return out


def json_loads(s):
    import json
    return json.loads(s)


def execute(args, t0):
    from book2qa import source
    workspace = paths.resolve_workspace(args)
    files = paths.book_files(paths.resolve_source_root(args), args.book)
    if not os.path.isfile(files["markdown"]):
        return emit("recall", EXIT_MISSING, workspace=workspace, book=args.book,
                    error="缺少 book2md 产物（先跑 build）", t0=t0)
    data = _load(workspace)
    nodes = data["graph"]
    if not nodes:
        return emit("recall", EXIT_MISSING, workspace=workspace, book=args.book,
                    error="graph.jsonl 为空——先跑 --stage=graph", t0=t0)
    text = source.read_markdown(files["markdown"])
    page_map = source.parse_page_map(files["page_map"])
    lines = text.split("\n")
    page_marks, _ = source.parse_page_marks(text)
    paragraphs = source.split_paragraphs(text, page_marks, page_map)
    meta_by = {m["idx"]: m for m in data["para_meta"]}
    node_by_id = {n["id"]: n for n in nodes}
    sec_by_id = {r["id"]: r for r in data["structure"]}

    query = args.query.strip()
    intent = retrieval.classify_intent(query)
    warnings = []

    # 排程/承接不进检索（retrieval §4 硬分流）
    if intent == "schedule":
        return emit("recall", EXIT_OK, workspace=workspace, book=args.book,
                    t0=t0, extra={"query": query, "intent": "schedule",
                                  "confidence": "none", "candidates": [],
                                  "fallback": {"type": "due"}})
    if intent == "follow_up" and not getattr(args, "context", None):
        return emit("recall", EXIT_OK, workspace=workspace, book=args.book,
                    t0=t0, extra={"query": query, "intent": "follow_up",
                                  "confidence": "none", "candidates": [],
                                  "fallback": {"type": "context"}})

    # ── 三路 ──
    r1 = retrieval.r1_lexicon(query, nodes)
    r3 = retrieval.r3_structural(query, nodes, data["exercises"])


    para_index = []
    for p in paragraphs:
        m = meta_by.get(p.idx)
        if not m:
            continue
        para_index.append({"start_line": p.start_line, "end_line": p.end_line,
                           "text": p.text, "section_id": m.get("owner_id"),
                           "block_kind": m.get("block_kind"),
                           "textbook_page": p.textbook_page,
                           "page_estimated": p.page_estimated})
    # R2 全册 + IDF（段落是独立证据源；seeds 只用于 why 归属提示）
    r2 = retrieval.r2_paragraphs(query, para_index, None)

    # R2 升格为第 4 路参与名次制 RRF（owner=段落所属节），与 R1/R3 等权——
    # 段落是正文证据的本体，不是 0.5 折算的旁证（评审后实测：折算会被 R1 噪声淹没）
    # owner_id（节/子节号）必须映射回 node_id——RRF 的 key 空间要统一
    # （此前 R2 的贡献从未进过候选：fused 里混了两种 key，60% 基线全是 R1/R3）
    unit_to_nodes = {}
    for n in nodes:
        unit_to_nodes.setdefault(n.get("unit"), []).append(n["id"])
    r2_owner = {}
    for key, _sc in r2.items():
        m = meta_by.get(_para_idx_of(paragraphs, key))
        o = m.get("owner_id") if m else None
        for nid in unit_to_nodes.get(o, []):
            r2_owner[nid] = r2_owner.get(nid, 0.0) + 1.0
    # R1 只保留片段强命中（score>=2 即 title/alias 片段出现在 query）；
    # 弱 bigram 底色是噪声源（"一定""函数"命中几十节点），模糊交给 R2 段落
    r1_strong = {k: v for k, v in r1.items() if v >= 2.0}
    # R3 题号分支的 key 是 owner_id，同样映射回 node_id（key 空间统一）
    r3_nodes = {}
    for k, v in r3.items():
        targets = [k] if k in node_by_id else unit_to_nodes.get(k, [])
        for nid in targets:
            r3_nodes[nid] = r3_nodes.get(nid, 0.0) + v
    # R4 向量路：index 存在且依赖可用时启用；缺失 = 三路正常形态（serving §1.2）。
    # 编码器进程级缓存（模块全局）；查询带 BGE 官方指令前缀（embed.py 封装）。
    # 降级原因必须进 warnings——宽 except 静默吞错曾让 R4 形同虚设（已修的教训）。
    r4_owner = {}
    _R4_ENCODER = globals().get("_R4_ENCODER")
    try:
        from book2qa import embed
        idx = embed.load_index(paths.data_dir(workspace))
        if idx:
            if _R4_ENCODER is None:
                models_dir = os.environ.get("B2Q_MODELS_DIR") or \
                    os.path.expanduser("~/.book2qa/models/bge-onnx")
                _R4_ENCODER = embed.Encoder(models_dir)
                globals()["_R4_ENCODER"] = _R4_ENCODER
            for m_row, _sc in embed.search(_R4_ENCODER, query, idx, top=8):
                for nid in unit_to_nodes.get(m_row.get("section_id"), []):
                    r4_owner[nid] = r4_owner.get(nid, 0.0) + 1.0
    except Exception as e:
        r4_owner = {}
        warnings.append("r4_degraded: %s" % type(e).__name__)

    rankings = {"r1": r1_strong, "r3": r3_nodes, "r2": r2_owner, "r4": r4_owner}
    fused = retrieval.rrf(rankings)

    ranked = sorted(fused.items(), key=lambda kv: -kv[1])[:TOP_N]
    # R4 预留：未装模型 = 三路正常形态（serving §1.2）
    if os.environ.get("B2Q_EMBED") == "on":
        warnings.append("r4_not_implemented")

    cands, budget = [], 0
    for nid, score in ranked:
        n = node_by_id.get(nid)
        if not n:
            continue
        quotes = []
        for a in n.get("anchors", [])[:3]:
            quotes.append({"role": a.get("role", "definition"),
                           "page": a.get("page"),
                           "text": _line_text(lines, a.get("quote"))})
        # 命中段落原文（R2 命中的段落优先，补足动机）
        for key, _sc in sorted(r2.items(), key=lambda kv: -kv[1]):
            p = paragraphs[_para_idx_of(paragraphs, key)]
            m = meta_by.get(p.idx, {})
            if m.get("owner_id") != nid:
                continue
            head = p.text.strip()[:160]
            if not any(head[:12] in q["text"] for q in quotes):
                quotes.append({"role": "paragraph",
                               "page": p.textbook_page, "text": head,
                               "estimated": p.page_estimated})
            if len(quotes) >= 5:
                break
        trimmed = []
        for q in quotes:
            if budget >= QUOTE_BUDGET:
                break
            take = _cut_sentence(q["text"], QUOTE_BUDGET - budget)
            budget += len(take)
            trimmed.append({**q, "text": take,
                            **({"truncated": True}
                               if len(take) < len(q["text"]) else {})})
        cands.append({
            "node_id": nid, "title": n.get("title"), "type": n.get("type"),
            "pages": n.get("pages"), "score": round(score, 4),
            "why": _why(query, n, r1, r2, r3, meta_by, paragraphs),
            "summary": n.get("summary", ""),
            "quotes": trimmed,
            "formulas": n.get("formulas", []),
            "errors": n.get("errors", []),
            "exercises": n.get("exercises", [])[:3],
        })

    conf = retrieval.confidence_of(cands)
    fallback = None
    if conf == "none":
        chapter = None
        if ranked:
            chapter = (node_by_id.get(ranked[0][0]) or {}).get("chapter")
        fallback = {"type": "clarify",
                    "options": retrieval.make_fallback_options(
                        data["structure"], chapter_id=chapter)}
    elif conf == "low":
        fallback = {"type": "confirm", "label": cands[0]["title"]}

    return emit("recall", EXIT_OK, workspace=workspace, book=args.book,
                t0=t0, warnings=warnings,
                extra={"query": query, "intent": intent, "confidence": conf,
                       "candidates": cands, "fallback": fallback})


def _para_idx_of(paragraphs, start_line):
    import bisect
    starts = [p.start_line for p in paragraphs]
    i = bisect.bisect_right(starts, start_line) - 1
    return paragraphs[i].idx if 0 <= i < len(paragraphs) else None


def _line_text(lines, quote):
    """quote 回原文：去空白匹配行。找不到（引号偏差）原样返回截断。"""
    if not quote:
        return ""
    nows = retrieval._flat_nows(quote) if hasattr(retrieval, "_flat_nows") \
        else __import__("re").sub(r"\s+", "", quote)
    import re as _re
    nows = _re.sub(r"\s+", "", quote)
    for i, ln in enumerate(lines):
        if _re.sub(r"\s+", "", ln) and _re.sub(r"\s+", "", ln) in nows or \
                nows[:20] and nows[:20] in _re.sub(r"\s+", "", ln):
            return _complete_sentence(lines, i)
    return quote[:160]


def _complete_sentence(lines, i, max_extra=300):
    """行 i 的文本若不以句末标点收尾，向下跨空行续拼到句子结束。

    源 md 把一个数学句拆成多段（公式行独立成段），锚点按行存文 → 半句
    （2026-11-04 用户实测：P77 定义句断在"区间 I⊆D"）。展示层拼回完整句，
    不改图谱数据。"""
    import re as _re
    text = lines[i].strip()
    if text.endswith(tuple(_SENT_END)):
        return text[:200]
    j, extra = i + 1, []
    while j < len(lines) and len(text) + sum(len(x) for x in extra) < max_extra:
        nxt = lines[j].strip()
        if nxt:
            extra.append(nxt if text.endswith((" ", "$")) else " " + nxt)
            joined = text + "".join(extra)
            if _re.search(r"[。！？；]\s*$|\)\s*\.?\s*$|\.\s*$", joined):
                break
        j += 1
    out = (text + "".join(extra))[:200 + max_extra]
    return out


def _why(query, node, r1, r2, r3, meta_by, paragraphs):
    bits = []
    if node["id"] in r1:
        bits.append("术语命中(%.2f)" % r1[node["id"]])
    if node["id"] in r3:
        bits.append("结构定位(%.2f)" % r3[node["id"]])
    n_hit = sum(1 for key, _ in r2.items()
                if (meta_by.get(_para_idx_of(paragraphs, key)) or {})
                .get("owner_id") == node["id"])
    if n_hit:
        bits.append("段落命中×%d" % n_hit)
    return "; ".join(bits) or "融合排名"


if __name__ == "__main__":
    sys.exit(0)
