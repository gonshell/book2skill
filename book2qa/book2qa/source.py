# -*- coding: utf-8 -*-
"""适配层：读 book2md 产物（arch.md §1：唯一碰文件的地方）。

职责：页锚定（块标记解析 + 图片页偏移换算）与段落切分。
不做标题解析（structure.py）、不做抽取（extract/*）。
"""
import json
import os
import re
from dataclasses import dataclass, field, replace

from book2qa.paths import data_dir

# 真实格式：<!-- ===== 原书物理页 7-46 · 教材页码 None-39 ===== -->
# 「教材页码」段可选（RV-C2：上游条件追加，下游不得强制匹配静默丢页）
PAGE_MARK_RE = re.compile(
    r"<!--\s*=+\s*原书物理页\s*(\d+)-(\d+)"
    r"(?:\s*·\s*教材页码\s*(\S+?)-(\S+?))?\s*=+\s*-->")
PAGE_MARK_LOOSE = re.compile(r"原书物理页\s*\d+-\d+")
IMAGE_RE = re.compile(r"page_(\d+)")


def _int_or_none(s):
    if s is None:
        return None
    s = s.strip()
    return int(s) if s.isdigit() else None


@dataclass(frozen=True)
class PageMark:
    idx: int                 # 块序号
    line_no: int             # 标记所在行（1 起）
    phys_start: int
    phys_end: int
    tb_start: int | None
    tb_end: int | None
    offset: int | None = None   # 图页→物理页偏移：physical = pdf_page - offset
    img_pages: tuple = field(default_factory=tuple)  # 块内全部图片 PDF 页（去重升序）


@dataclass(frozen=True)
class Paragraph:
    idx: int
    start_line: int
    end_line: int
    text: str
    block_idx: int                    # -1 = 首块标记前的导语区
    img_pages: tuple                  # 本段内图片 PDF 页（去重升序）
    physical_page: int | None
    page_estimated: bool              # True = 继承邻近锚定段，非图片锚定
    textbook_page: int | None


def read_markdown(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def parse_page_map(path):
    """page_map.md 表格 → {物理页: 教材页}。缺文件返回空表（调用方报 issue）。"""
    mapping = {}
    if not path or not os.path.isfile(path):
        return mapping
    with open(path, encoding="utf-8") as f:
        for ln in f:
            m = re.match(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|", ln)
            if m:
                mapping[int(m.group(1))] = int(m.group(2))
    return mapping


def parse_page_marks(text):
    """扫描块标记 → ([PageMark], issues)。图片偏移在此一并计算与校验。"""
    lines = text.split("\n")
    marks = []
    for i, ln in enumerate(lines, 1):
        m = PAGE_MARK_RE.search(ln)
        if m:
            marks.append(PageMark(
                idx=len(marks), line_no=i,
                phys_start=int(m.group(1)), phys_end=int(m.group(2)),
                tb_start=_int_or_none(m.group(3)), tb_end=_int_or_none(m.group(4))))
    # 兜底：含「原书物理页」但主正则不匹配的行必须留痕，不得静默丢页（RV-C2）
    issues = []
    for i, ln in enumerate(lines, 1):
        if PAGE_MARK_LOOSE.search(ln) and not PAGE_MARK_RE.search(ln):
            issues.append({"code": "page_mark_unparsed", "line": i,
                           "detail": "页界标记格式未识别（教材页码段异常？）：%s"
                                     % ln.strip()[:60]})
    if not marks:
        issues.append({"code": "page_marks_absent",
                       "detail": "全文无有效页界标记"})
        return [], issues

    mark_at = {mk.line_no: mk for mk in marks}
    imgs_by_block = {-1: []}
    cur = -1
    for i, ln in enumerate(lines, 1):
        if i in mark_at:
            cur = mark_at[i].idx
            imgs_by_block.setdefault(cur, [])
            continue
        for pg in IMAGE_RE.findall(ln):
            imgs_by_block[cur].append(int(pg))

    # 每块候选偏移：lo=首对齐 hi=尾对齐（块内有缺图 PDF 页时二者不等）
    cands = {}
    for mk in marks:
        imgs = tuple(sorted(set(imgs_by_block.get(mk.idx, []))))
        cands[mk.idx] = (imgs,
                         imgs[0] - mk.phys_start if imgs else None,
                         imgs[-1] - mk.phys_end if imgs else None)

    # 不变量（必修一实测）：每块恰占固定数量 PDF 页，块间 PDF 页连续等差 →
    # offset_k = offset_0 + (phys_start_k − phys_start_0)。
    # 首块偏移取自身候选（lo==hi 唯一；歧义取尾对齐并留痕）。
    offsets = {}
    imgs0, lo0, hi0 = cands[0]
    if lo0 is None:
        offsets[0] = None
        issues.append({"code": "block_no_images", "block": 0,
                       "detail": "块 %d-%d 无图片引用，段落只能继承估计页" % (0, 0)})
    elif lo0 == hi0:
        offsets[0] = lo0
    elif lo0 > hi0:
        # 基准块歧义：取首对齐（首图视为块首页），后续块按等差推；留痕待查
        offsets[0] = lo0
        issues.append({"code": "page_offset_ambiguous", "block": 0,
                       "detail": "基准块偏移候选 [%d, %d]，取首对齐 %d，后续块随之等差"
                                 % (hi0, lo0, lo0)})
    else:
        offsets[0] = None
        issues.append({"code": "page_offset_invalid", "block": 0,
                       "detail": "图片范围 %d-%d 超出物理页 %d-%d"
                                 % (imgs0[0], imgs0[-1], marks[0].phys_start, marks[0].phys_end)})
    for mk in marks[1:]:
        if offsets[0] is None:
            imgs, lo, hi = cands[mk.idx]
            if lo is None:
                offsets[mk.idx] = None
                issues.append({"code": "block_no_images", "block": mk.idx,
                               "detail": "块 %d-%d 无图片引用，段落只能继承估计页"
                                         % (mk.phys_start, mk.phys_end)})
            elif lo == hi:
                offsets[mk.idx] = lo
            elif lo > hi:
                offsets[mk.idx] = hi
                issues.append({"code": "page_offset_ambiguous", "block": mk.idx,
                               "detail": "偏移候选 [%d, %d]（块 %d-%d），取尾对齐 %d"
                                         % (hi, lo, mk.phys_start, mk.phys_end, hi)})
            else:
                offsets[mk.idx] = None
                issues.append({"code": "page_offset_invalid", "block": mk.idx,
                               "detail": "图片范围 %d-%d 超出物理页 %d-%d"
                                         % (imgs[0], imgs[-1], mk.phys_start, mk.phys_end)})
        else:
            offsets[mk.idx] = offsets[0] + (mk.phys_start - marks[0].phys_start)

    fixed = []
    for mk in marks:
        imgs = cands[mk.idx][0]
        offset = offsets[mk.idx]
        if offset is not None and imgs:
            bad = [p for p in imgs
                   if not (mk.phys_start <= p - offset <= mk.phys_end)]
            if bad:
                issues.append({"code": "page_offset_inconsistent", "block": mk.idx,
                               "detail": "偏移 %d 下越界图片 PDF 页：%s（块 %d-%d）"
                                         % (offset, bad[:8], mk.phys_start, mk.phys_end)})
        elif offset is None and imgs:
            issues.append({"code": "block_no_images", "block": mk.idx,
                           "detail": "块 %d-%d 无图片引用，段落只能继承估计页"
                                     % (mk.phys_start, mk.phys_end)})
        fixed.append(replace(mk, offset=offset, img_pages=imgs))
    if imgs_by_block[-1]:
        issues.append({"code": "image_outside_block", "detail":
                       "首块标记前存在图片引用 PDF 页 %s" % sorted(set(imgs_by_block[-1]))[:8]})
    return fixed, issues


def split_paragraphs(text, marks, page_map):
    """按块标记 + 空行切段；段内图片锚定物理页，无图段继承同块最近锚定段。"""
    lines = text.split("\n")
    mark_at = {mk.line_no: mk for mk in marks}
    cur_mk = None
    raws = []           # (mark|None, start, end, body, img_pages)
    cur, start, imgs = [], None, []

    def flush(end_line):
        nonlocal cur, start, imgs
        if cur:
            raws.append((cur_mk, start, end_line, list(cur), tuple(sorted(set(imgs)))))
        cur, start, imgs = [], None, []

    for i, ln in enumerate(lines, 1):
        if i in mark_at:
            flush(i - 1)
            cur_mk = mark_at[i]
            continue
        if not ln.strip():
            flush(i - 1)
            continue
        if start is None:
            start = i
        cur.append(ln)
        imgs.extend(int(p) for p in IMAGE_RE.findall(ln))
    flush(len(lines))

    staged = []
    for n, (mk, s, e, body, pimgs) in enumerate(raws):
        anchored = pimgs[0] - mk.offset if (mk and mk.offset is not None and pimgs) else None
        staged.append({"n": n, "mk": mk, "s": s, "e": e, "body": body,
                       "pimgs": pimgs, "anchored": anchored})

    by_block = {}
    for p in staged:
        by_block.setdefault(p["mk"].idx if p["mk"] else -1, []).append(p)

    out = []
    for blk, plist in by_block.items():
        anchored_ps = [q for q in plist if q["anchored"] is not None]
        for p in plist:
            if p["anchored"] is not None:
                phys, est = p["anchored"], False
            elif anchored_ps:
                q = min(anchored_ps, key=lambda q: (abs(q["s"] - p["s"]), q["s"]))
                phys, est = q["anchored"], True
            else:
                phys, est = None, True
            out.append(Paragraph(
                idx=p["n"], start_line=p["s"], end_line=p["e"],
                text="\n".join(p["body"]),
                block_idx=p["mk"].idx if p["mk"] else -1,
                img_pages=p["pimgs"], physical_page=phys,
                page_estimated=est,
                textbook_page=page_map.get(phys) if phys is not None else None))
    out.sort(key=lambda p: p.idx)
    return out


def load_structure(workspace, book):
    """读上一步产物 data/structure.jsonl → [dict]。"""
    return _load_jsonl(os.path.join(data_dir(workspace), "structure.jsonl"))


def load_para_meta(workspace, book):
    """读 data/para_meta.jsonl → [dict]。"""
    return _load_jsonl(os.path.join(data_dir(workspace), "para_meta.jsonl"))


def _load_jsonl(path):
    rows = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    rows.append(json.loads(ln))
    return rows


def to_json_line(obj):
    d = obj.__dict__ if hasattr(obj, "__dict__") else obj
    return json.dumps(d, ensure_ascii=False)
