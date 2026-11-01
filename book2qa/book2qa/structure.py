# -*- coding: utf-8 -*-
"""核心层：标题四分类 + 章名续行 + OCR 归并 → 结构树（graph-spec §10）。

纯函数：输入 source.split_paragraphs 的段落序列，输出 (rows, issues)。
零文件 IO、零打印、零环境变量（arch.md §1 铁律）。

分类依据为必修一 436 个 `##` 的真实形态取证（2026-11-01）：
  章   `## 第一章集合与常用逻辑用语`（章名紧贴）/ `## 第五章`+`## 三角函数`（续行）
  节   `## 1.1 集合的概念` / `## 2.3二次函数…`（缺空格）
  子节 `## 3.2.1单调性与最大（小）值`（缺空格）
  提问块 `## 思考` / `## 3思考` / `## 2) 阅读与思考` / `## 6归纳`（OCR 前缀归并）
  栏内项 `## 1. 周期性` / `## 1. 选择题`（单数字开头，不切边界，留作候选线索）
  噪音 `## • •` / `## da`（记入 items，内容不丢）

行序约定：任何分支都不产生"丢弃"——标题要么成边界、要么进 items、
要么改变 block_kind；段落内容恒落入某个行（front 兜底）。
"""
import re
from dataclasses import dataclass

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
CHAPTER_RE = re.compile(r"^第([一二三四五六七八九十]+)章\s*(.*)$")
SUBSECTION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)\s*(.*)$")
SECTION_RE = re.compile(r"^(\d+)\.(\d+)(?![.\d])\s*(.*)$")
ITEM_RE = re.compile(r"^(\d+)\s*[\.、\)]\s*(\S.*)$")
CH_END_RE = re.compile(r"^([一二三四五六七八九十]+)\s*、\s*(\S.*)$")

# 提问块词表（graph-spec §10 四分类）；长词优先匹配
PROMPT_WORDS = sorted(
    ("思考", "观察", "探究", "归纳", "练习", "习题", "复习巩固", "综合运用",
     "拓广探索", "阅读与思考", "探究与发现", "信息技术应用", "小结"),
    key=len, reverse=True)
NOISE_RE = re.compile(r"^[\d\s\.\)\·•×,，。]*$")
META_TITLES = ("后记", "部分中英文词汇索引")
CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


@dataclass(frozen=True)
class Heading:
    line_no: int
    level: int          # # 个数
    kind: str           # chapter/section/subsection/prompt/ch_end/item/noise/minor/meta
    word: str | None    # prompt 块名
    num: str | None     # "1.1"/"1.4.1"/"第一章"
    title: str
    cn: int | None      # 章序号


def _clean_noise_prefix(text):
    """去 OCR 数字/符号前缀：`3思考`→`思考`、`2) 阅读与思考`→`阅读与思考`。"""
    return re.sub(r"^[\d\s\.\)\·•×,，]*", "", text)


def classify(text):
    """单行标题文本 → Heading 字段（不含 line_no/level）。"""
    t = text.strip()
    m = CHAPTER_RE.match(t)
    if m:
        cn = sum(CN_NUM[c] for c in m.group(1))
        return Heading(0, 0, "chapter", None, "第%s章" % m.group(1),
                       m.group(2).strip(), cn)
    m = SUBSECTION_RE.match(t)
    if m:
        return Heading(0, 0, "subsection", None,
                       "%s.%s.%s" % m.group(1, 2, 3), m.group(4).strip(), None)
    m = SECTION_RE.match(t)
    if m:
        return Heading(0, 0, "section", None,
                       "%s.%s" % m.group(1, 2), m.group(3).strip(), None)
    m = CH_END_RE.match(t)
    if m:
        return Heading(0, 0, "ch_end", m.group(2).strip(), None, t, None)
    if re.match(r"^复习参考题", t):
        return Heading(0, 0, "ch_end", None, None, t, None)
    cleaned = _clean_noise_prefix(t)
    for w in PROMPT_WORDS:
        if cleaned.startswith(w):
            return Heading(0, 0, "prompt", w, None, t, None)
    if NOISE_RE.match(t) or re.fullmatch(r"[A-Za-z]{1,3}", t):
        return Heading(0, 0, "noise", None, None, t, None)
    m = ITEM_RE.match(t)
    if m:
        return Heading(0, 0, "item", None, None, t, None)
    if t in META_TITLES:
        return Heading(0, 0, "meta", None, None, t, None)
    return Heading(0, 0, "minor", None, None, t, None)


def _collect_headings(paragraphs):
    """段落内逐行找标题行 → [(Heading)]。标题与正文同段时也拆出。"""
    out = []
    for p in paragraphs:
        for off, ln in enumerate(p.text.split("\n")):
            m = HEADING_RE.match(ln)
            if m:
                h = classify(m.group(2))
                out.append(Heading(p.start_line + off, len(m.group(1)),
                                   h.kind, h.word, h.num, h.title, h.cn))
    return out


def _agg(row, start_line, end_line, text, p):
    row["n_paras"] += 1
    row["n_lines"] += end_line - start_line + 1
    row["n_chars"] += len(text)
    if p.physical_page is not None:
        row["phys"][0] = min(row["phys"][0], p.physical_page)
        row["phys"][1] = max(row["phys"][1], p.physical_page)
    if p.textbook_page is not None:
        row["tb"][0] = min(row["tb"][0], p.textbook_page)
        row["tb"][1] = max(row["tb"][1], p.textbook_page)


def _new_row(kind, rid, title, chapter_id=None, cn=None, parent_id=None,
             line_start=None):
    return {"kind": kind, "id": rid, "title": title, "chapter_id": chapter_id,
            "chapter_num": cn, "parent_id": parent_id, "line_start": line_start,
            "line_end": None, "phys": [10 ** 9, -1], "tb": [10 ** 9, -1],
            "n_paras": 0, "n_lines": 0, "n_chars": 0, "items": [],
            "block_kinds": {}}


def build_tree(paragraphs):
    """paragraphs: [source.Paragraph] → (rows, issues)。行序单趟，栈式收口。"""
    heads = _collect_headings(paragraphs)

    # —— 章名续行合并：`## 第五章` 后 ≤3 行内的 minor 标题视为章名 ——
    issues = []
    heads2 = []
    skip = set()
    for k, h in enumerate(heads):
        if h.line_no in skip:
            continue
        if h.kind == "chapter" and not h.title:
            nxt = heads[k + 1] if k + 1 < len(heads) else None
            if nxt and nxt.kind == "minor" and nxt.line_no - h.line_no <= 3:
                heads2.append(Heading(h.line_no, h.level, "chapter", None,
                                      h.num, nxt.title, h.cn))
                skip.add(nxt.line_no)
                continue
            issues.append({"code": "chapter_unnamed", "line": h.line_no,
                           "detail": "章标题无续行可合并：%r" % h.num})
        heads2.append(h)
    heads = heads2

    head_at = {h.line_no: h for h in heads}
    last_line = max((p.end_line for p in paragraphs), default=0)

    rows = []
    cur_ch = cur_sec = cur_sub = None
    block_kind = "正文"
    front = _new_row("front", "F0", "前置内容")
    used_front = False

    def target():
        nonlocal used_front
        t = cur_sub or cur_sec
        if t is None:
            used_front = True
            if front["line_start"] is None:
                front["line_start"] = p.start_line
            return front
        return t

    def close(row, end_ln):
        if row is not None and row["line_end"] is None:
            row["line_end"] = end_ln

    for p in paragraphs:
        h = head_at.get(p.start_line)
        if h is not None:
            kind = h.kind
            if kind == "chapter":
                close(cur_sub, p.start_line - 1)
                close(cur_sec, p.start_line - 1)
                close(cur_ch, p.start_line - 1)
                cur_sub = cur_sec = None
                cur_ch = _new_row("chapter", h.num, h.title or "(章名缺失)",
                                  cn=h.cn, line_start=p.start_line)
                rows.append(cur_ch)
                block_kind = "正文"
            elif kind == "section":
                close(cur_sub, p.start_line - 1)
                close(cur_sec, p.start_line - 1)
                cur_sub = None
                ch_id = cur_ch["id"] if cur_ch else None
                sec_ch = int(h.num.split(".")[0])
                if cur_ch and cur_ch["chapter_num"] is not None \
                        and sec_ch != cur_ch["chapter_num"]:
                    issues.append({"code": "chapter_section_mismatch", "line": h.line_no,
                                   "detail": "节 %s 与当前章 %s 序号不符"
                                             % (h.num, cur_ch["id"])})
                cur_sec = _new_row("section", h.num, h.title, ch_id,
                                   line_start=p.start_line)
                rows.append(cur_sec)
                block_kind = "正文"
            elif kind == "subsection":
                close(cur_sub, p.start_line - 1)
                ch_id = cur_ch["id"] if cur_ch else None
                parent_ok = cur_sec is not None and \
                    cur_sec["id"] == h.num.rsplit(".", 1)[0]
                if not parent_ok:
                    issues.append({"code": "subsection_orphan", "line": h.line_no,
                                   "detail": "子节 %s 的父节缺失或错位" % h.num})
                cur_sub = _new_row("subsection", h.num, h.title, ch_id,
                                   parent_id=cur_sec["id"] if parent_ok else None,
                                   line_start=p.start_line)
                rows.append(cur_sub)
                block_kind = "正文"
            elif kind == "meta":
                close(cur_sub, p.start_line - 1)
                close(cur_sec, p.start_line - 1)
                cur_sub = None
                cur_sec = _new_row("meta", "M-" + h.title, h.title,
                                   line_start=p.start_line)
                rows.append(cur_sec)
                block_kind = "正文"
            elif kind == "prompt":
                block_kind = h.word
            elif kind == "ch_end":
                block_kind = "章末栏目"
            elif kind in ("item", "minor", "noise"):
                t = target()
                t["items"].append({"line": h.line_no, "kind": kind,
                                   "title": h.title})
            # 标题段的多余行（标题与正文粘连）照常聚合
            if p.end_line > p.start_line:
                rest = "\n".join(p.text.split("\n")[1:])
                if rest.strip():
                    _agg(target(), p.start_line + 1, p.end_line, rest, p)
                    target()["block_kinds"][block_kind] = \
                        target()["block_kinds"].get(block_kind, 0) + 1
            continue

        t = target()
        _agg(t, p.start_line, p.end_line, p.text, p)
        t["block_kinds"][block_kind] = t["block_kinds"].get(block_kind, 0) + 1

    close(cur_sub, last_line)
    close(cur_sec, last_line)
    close(cur_ch, last_line)
    if used_front:
        front["line_end"] = (rows[0]["line_start"] - 1) if rows else last_line
        rows.insert(0, front)

    for r in rows:
        if r["phys"][1] < r["phys"][0]:
            r["phys"] = None
        if r["tb"][1] < r["tb"][0]:
            r["tb"] = None
        if r["line_start"] is None:
            r["line_start"] = r["line_end"]
    return rows, issues
