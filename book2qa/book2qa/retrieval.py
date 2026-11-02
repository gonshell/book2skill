# -*- coding: utf-8 -*-
"""核心层：意图识别 + 三路召回 + RRF 融合 + 置信兜底（retrieval.md §2–§8）。

纯函数：输入命令层组装好的 nodes/paragraphs/exercises，输出候选与信封字段。
R4 向量路预留接口（`r4_rankings` 参数）——模型未装 = 三路正常形态（serving §1.2）。

意图规则（retrieval §2，三源信号，任一命中即分类；全空 → auto）。
兜底三级（§8）：强命中直接答 / 弱命中"是不是X" / 全空回问 3 切入点。
"""
import re

# ── 意图信号（顺序即优先级：先判"不进检索"的，再判侧重）──
_INTENT_RULES = (
    ("too_broad", ("一点都听不懂", "完全不会", "完全懵", "彻底懵", "听不懂",
                   "一点都不会", "完全没学过")),
    ("schedule", ("复习什么", "复习啥", "考考我", "该复习", "帮我安排",
                  "出几道题考", "抽查我")),
    ("follow_up", ("那为什么", "为什么这步", "这一步", "那这", "接着说",
                   "继续", "再讲讲")),
    ("check_work", ("对不对", "对吗", "我算的", "我这样", "我写的",
                    "怎么老混", "我是不是", "帮我看看", "这样判断对")),
    ("method_list", ("几种方法", "有哪几种", "步骤是什么", "怎么做这类",
                     "有哪几个", "从哪下手", "什么时候用", "怎么换算",
                     "怎么求")),
    ("concept_why", ("为什么", "是什么意思", "什么叫", "是谁发明",
                     "哪个是", "是什么", "是谁", "差在哪", "谁快")),
)

STUCK_MARK_RE = re.compile(r"^(.{15,})$")
MATHISH_RE = re.compile(r"[0-9a-zA-Z^\\{}()$]{3,}")


def classify_intent(query, context=None):
    """(query, context) → intent。规则命中即返回；全空 → stuck（有实词的默认）。"""
    q = query.strip()
    for intent, words in _INTENT_RULES:
        for w in words:
            if w in q:
                return intent
    if STUCK_MARK_RE.match(q) and MATHISH_RE.search(q):
        return "stuck"          # 长题干/公式串 → 卡题
    return "stuck"


def _bigrams(text):
    """CJK 2-gram + 连续拉丁/数字词。检索 token 化。"""
    s = re.sub(r"\s+", "", text or "")
    grams = set()
    latin = re.findall(r"[a-zA-Z0-9]+", s)
    for w in latin:
        wl = w.lower()
        if len(w) >= 2:
            grams.add(wl)
        elif w:
            grams.add(wl + "$")
        if len(wl) > 3:   # sin2x vs "sin 2x"：拉丁长词补内部切片，保证可相交
            for i in range(len(wl) - 1):
                grams.add(wl[i:i + 2])
    cjk = re.sub(r"[^\u4e00-\u9fff]", " ", s).split()
    for seg in cjk:
        if len(seg) == 1:
            grams.add(seg)
        for i in range(len(seg) - 1):
            grams.add(seg[i:i + 2])
    return grams


def _node_lexicon(node):
    """R1 语料：title×3 + aliases×2.5 + errors×2 + summary×1。"""
    parts = []
    parts.extend([node.get("title", "")] * 3)
    for a in node.get("aliases", []) or []:
        parts.extend([a] * 2)
    for e in node.get("errors", []) or []:
        parts.append(e)
    s = node.get("summary", "")
    if s:
        parts.append(s)
    return " ".join(parts)


_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
           "七": 7, "八": 8, "九": 9, "十": 10}


def r1_lexicon(query, nodes):
    """词表锚定 → {node_id: score}。

    两级：title/aliases 的**完整片段**出现在 query = 强命中（+2/片段）；
    bigram 重叠 = 弱分底色。片段 = title 按标点/连接词切开后的词面。
    """
    q = query.strip()
    qg = _bigrams(query)
    scores = {}
    for n in nodes:
        score = 0.0
        phrases = [n.get("title", "")]
        phrases += [a for a in (n.get("aliases") or []) if a]
        for ph in phrases:
            for piece in re.split(r"[与和、（）()，,/]", ph):
                piece = piece.strip()
                if len(piece) >= 2 and piece in q:
                    score += 2.0
        ng = _bigrams(_node_lexicon(n))
        if ng:
            hit = qg & ng
            if hit:
                score += len(hit) / (len(qg) ** 0.5 + 1)
        if score > 0:
            scores[n["id"]] = score
    return scores


def r3_structural(query, nodes, exercise_rows):
    """页码/节号/题号精确命中 → {node_id: score}（强信号）。"""
    scores = {}
    page = re.search(r"[Pp]\s*(\d{1,3})", query)
    if page:
        p = int(page.group(1))
        for n in nodes:
            pg = n.get("pages")
            if pg and pg[0] - 1 <= p <= pg[1] + 1:
                scores[n["id"]] = scores.get(n["id"], 0) + 3.0
    sec = re.search(r"(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)", query)
    if sec:
        sid = sec.group(1)
        for n in nodes:
            s = n.get("section", "")
            if s.startswith(sid):
                scores[n["id"]] = scores.get(n["id"], 0) + 2.5
    num = re.search(r"(练习|习题|复习巩固|综合运用|拓广探索|例)\s*第?\s*\(?\s*(\d{1,2}|[一二三四五六七八九十]{1,3})\s*\)?\s*题?",
                    query)
    if num:
        tail = num.group(2)
        if not tail.isdigit():
            total = 0
            for ch in tail:
                total = total * 10 + _CN_NUM.get(ch, 0) if ch != "十" else (
                    (total or 1) * 10)
            tail = str(total)
        want = "%s%s" % (num.group(1), tail)
        for e in exercise_rows:
            lab = e.get("label", "")
            if want in lab.replace(" ", ""):
                owner = e.get("owner_id")
                if owner:
                    scores[owner] = scores.get(owner, 0) + 2.0
    return scores


def r2_paragraphs(query, para_index, section_ids=None, top=8):
    """段落路（两段式的段落段）：全册 + IDF 加权重叠 → {para_key: score}。

    section_ids 传入时做节内过滤（两段式的"定节"）；None = 全册
    （定节失败/段落级证据优先——"奇函数"不在 title 里，正文才有）。
    IDF 压制"函数/集合"类高频词，让"奇函数/诱导公式"类判别词赢。
    """
    qg = _bigrams(query)
    if not qg:
        return {}
    # 预计算 df
    df = {}
    scanned = []
    for p in para_index:
        if section_ids is not None and p.get("section_id") not in section_ids:
            continue
        if p.get("block_kind") not in ("正文", "思考", "观察", "探究", "归纳",
                                       "小结", "例"):
            continue
        grams = p.get("grams") or _bigrams(p.get("text", ""))
        scanned.append((p, grams))
        for g in grams:
            df[g] = df.get(g, 0) + 1
    import math
    n_docs = max(len(scanned), 1)
    scores = {}
    for p, grams in scanned:
        hit = qg & grams
        if not hit:
            continue
        idf_sum = sum(math.log(1.0 + n_docs / (1 + df.get(g, 0))) for g in hit)
        key = p["start_line"]
        scores[key] = idf_sum / (len(qg) ** 0.5 + 1)
    return dict(sorted(scores.items(), key=lambda kv: -kv[1])[:top])


def rrf(rankings, k=60):
    """rankings: {route: {key: score}} → {key: rrf}，同路先按分数排名次。"""
    out = {}
    for _route, scores in rankings.items():
        if not scores:
            continue
        for rank, (key, _s) in enumerate(
                sorted(scores.items(), key=lambda kv: -kv[1]), 1):
            out[key] = out.get(key, 0.0) + 1.0 / (k + rank)
    return out


def confidence_of(candidates, floor=0.008):
    """三级（retrieval §8）：none / low（top3 分差小）/ high。"""
    if not candidates:
        return "none"
    top = candidates[0]["score"]
    if top < floor:
        return "none"
    if len(candidates) >= 2:
        second = candidates[1]["score"]
        if top > 0 and (top - second) / top < 0.2 and second > floor * 0.6:
            return "low"
    return "high"


def make_fallback_options(structure_rows, chapter_id=None, n=3):
    """回问切入点：同章下一级节（学习顺序），来自 structure 而非模型编。"""
    secs = [r for r in structure_rows if r["kind"] == "section"]
    if chapter_id:
        secs = [r for r in secs if r.get("chapter_id") == chapter_id] or secs
    return [{"label": r["title"], "sec": r["id"]} for r in secs[:n]]
