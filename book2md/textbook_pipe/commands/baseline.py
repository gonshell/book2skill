# -*- coding: utf-8 -*-
"""tbp baseline — 基准回归（docs/spec-cli.md §6.10，方案 §4.3.3/§4.3.6）。

防抽取后端静默漂移：固定"已知良好"页样本，后端升级/换适配器后重抽同页比对。

init：从 workspace/out/<book>/markdown.md（已验收产物）按页界标记切片，
     默认每册首/中/尾各 2 物理页（科目配置 baseline.pages 可覆盖），
     记录指标基线（字符数 / D1–D10 / KaTeX 错误数）+ 抽取产物样本 + 指纹。
run ：对同页区间走网关重抽（convert_block → merge_one），逐指标比对：
     字符数 ±0.5%、探测器 ±0、KaTeX 错误 ±0、版本指纹一致。
     三态：0 一致 / 40 漂移（列差异 + 指纹对比）/ 20 基线不存在。
"""
import datetime
import json
import os
import re
import shutil
import sys
import tempfile

from textbook_pipe.commands._envelope import emit
from textbook_pipe.commands._endpoints import resolve_api
from textbook_pipe.extractors import merge, mineru
from textbook_pipe.engine.inspectors import detectors
from textbook_pipe.engine import render, rules
from textbook_pipe.exit_codes import EXIT_BACKEND, EXIT_CONTRACT, EXIT_MISSING, EXIT_OK, EXIT_USAGE

MARKER_RE = re.compile(r"<!--\s*===== 原书物理页 (\d+)-(\d+)")
IMG_RE = re.compile(r"\(images/([^)]+)\)")
SCHEMA = "tbp.baseline/v1"
CHAR_TOL = 0.005   # 字符数允许 ±0.5%（spec §6.10）


# ---------- 基础工具 ----------

def _strip_markers(text):
    """去掉页界标记行——比对只看内容本身（merge_one 的标记尾为 " ===== -->"）。"""
    return re.sub(r"<!--\s*===== 原书物理页 [^>]*=====\s*-->\n?", "", text)


def _char_count(text):
    """非空白字符数（对换行/空格差异不敏感，专抓内容漂移）。"""
    return len(re.sub(r"\s+", "", _strip_markers(text)))


def _slice_segments(md_text):
    """按页界标记切片 → [{s, e, text}]（text 含标记行，便于原样落盘）。"""
    marks = [(int(m.group(1)), int(m.group(2)), m.start())
             for m in MARKER_RE.finditer(md_text)]
    if not marks:
        return None
    segs = []
    for i, (s, e, start) in enumerate(marks):
        end = marks[i + 1][2] if i + 1 < len(marks) else len(md_text)
        segs.append({"s": s, "e": e, "text": md_text[start:end]})
    return segs


def _default_sample_pages(lo, hi):
    """默认抽样：首 2 / 中 2 / 尾 2 物理页（去重排序）。"""
    mid = (lo + hi) // 2
    pages = {lo, min(lo + 1, hi), mid, min(mid + 1, hi), hi, max(hi - 1, lo)}
    return sorted(p for p in pages if lo <= p <= hi)


def _select_segments(segs, pages):
    """物理页 → 覆盖它的块切片（去重，按起始页排序）。"""
    picked, seen = [], set()
    for seg in sorted(segs, key=lambda x: x["s"]):
        if any(seg["s"] <= p <= seg["e"] for p in pages) and seg["s"] not in seen:
            picked.append(seg)
            seen.add(seg["s"])
    return picked


def _pick_segments(segs, pages_cfg, blocks_cfg, ledger_blocks):
    """init 抽样选段（spec §6.10）：三级优先。

    ① pages_cfg：科目配置 baseline.pages 显式页列表（页 → 覆盖块切片）；
    ② blocks_cfg=="all"：按账本抽取块全覆盖（每块整段入样）——不再需要手填页码，
       整册化学书实测默认首中尾抽样会漏掉表内图最密集的块（87-126）；
    ③ 默认：首/中/尾各 2 物理页。
    返回 [(seg, pages_sampled)]。
    """
    if pages_cfg:
        return [(seg, sorted(p for p in pages_cfg if seg["s"] <= p <= seg["e"]))
                for seg in _select_segments(segs, pages_cfg)]
    if blocks_cfg == "all":
        keys = {str(k) for k in (ledger_blocks or {})}
        picked = [(seg, [seg["s"], seg["e"]]) for seg in sorted(segs, key=lambda x: x["s"])
                  if "%d-%d" % (seg["s"], seg["e"]) in keys]
        if picked:
            return picked
        # 账本无该册（如 out/ 产物先于本工作区账本）→ 退化按页界标记自身分块
        return [(seg, [seg["s"], seg["e"]]) for seg in segs]
    lo, hi = segs[0]["s"], segs[-1]["e"]
    return [(seg, sorted(p for p in _default_sample_pages(lo, hi)
                         if seg["s"] <= p <= seg["e"]))
            for seg in _select_segments(segs, _default_sample_pages(lo, hi))]


def _measure(book, text, tmp_root, img_src=None):
    """单块指标：字符数 + D1–D10 + KaTeX 错误/缺图。落盘临时目录跑探测器与渲染。

    img_src：该块配套图片目录（init 传 out/<book>/images，run 传重抽产物的 images）。
    只复制 text 实际引用到的图片——不复制会把 D 规则全部误判为"悬空引用"，
    使基线指标掺入测量环境假阳性（整册化学书实测 22 处）。
    """
    src = os.path.join(tmp_root, "src", book)
    out = os.path.join(tmp_root, "out")
    shutil.rmtree(tmp_root, ignore_errors=True)
    os.makedirs(src, exist_ok=True)
    with open(os.path.join(src, "markdown.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(_strip_markers(text))
    if img_src and os.path.isdir(img_src):
        dst = os.path.join(src, "images")
        for name in sorted(set(IMG_RE.findall(text))):
            fp = os.path.join(img_src, name)
            if os.path.isfile(fp):
                os.makedirs(dst, exist_ok=True)
                shutil.copy2(fp, os.path.join(dst, name))
    det = detectors.run(source_dir=os.path.join(tmp_root, "src"), books=[book])
    with _quiet():
        rr = render.run(books=[book], variant="reader",
                        source_dir=os.path.join(tmp_root, "src"), out_dir=out)
    return {
        "chars": _char_count(text),
        "detectors": dict(sorted(det["per_detector"].items())),
        "detectors_total": det["total"],
        "katex_errors": len(rr["errors"]),
        "katex_missing": len(rr["missing"]),
    }


class _quiet:
    """stderr 静音上下文（render 进度不污染 CLI stderr 信封纪律外的日志）。"""

    def __enter__(self):
        self._saved = sys.stderr
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
        return self

    def __exit__(self, *exc):
        sys.stderr.close()
        sys.stderr = self._saved
        return False


def _fingerprint_snapshot():
    return {"adapter": "mineru-remote", "tier": "basic",
            "fingerprint": mineru.collect_fingerprint()}


# ---------- init ----------

def _cmd_init(args, t0):
    workspace = args.workspace
    out_root = os.path.join(workspace, "out")
    if args.book and not os.path.exists(os.path.join(out_root, args.book, "markdown.md")):
        return emit("baseline", EXIT_MISSING,
                    error={"code": "NO_BOOKS",
                           "message": "out/%s/markdown.md 不存在（先 run/convert 产出）" % args.book},
                    t0=t0)
    books = [args.book] if args.book else sorted(
        d for d in os.listdir(out_root)
        if os.path.isdir(os.path.join(out_root, d))
        and os.path.exists(os.path.join(out_root, d, "markdown.md"))) \
        if os.path.isdir(out_root) else []
    if not books:
        return emit("baseline", EXIT_MISSING,
                    error={"code": "NO_BOOKS",
                           "message": "out/ 下无可入库的书（先 run/convert 产出 out/<book>/markdown.md）"},
                    t0=t0)

    # 科目配置的 baseline 覆盖（spec §6.10 init 规则）：
    # pages = 显式页列表；blocks = "all" 按账本抽取块全覆盖；都缺省走首中尾抽样
    pages_cfg, blocks_cfg = None, None
    from textbook_pipe.commands import onboard as onboard_mod
    cfg_path = onboard_mod._subject_config_path(args.subject)
    if os.path.exists(cfg_path):
        cfg = json.load(open(cfg_path, encoding="utf-8"))
        b = cfg.get("baseline") or {}
        pages_cfg = b.get("pages")
        blocks_cfg = b.get("blocks")
    ledger_blocks = {}
    ledger_path = os.path.join(workspace, "ledger.json")
    if os.path.exists(ledger_path):
        led = json.load(open(ledger_path, encoding="utf-8"))

    base_dir = os.path.join(workspace, "baselines", args.subject)
    entries, ledger_pdf = {}, None
    for book in books:
        md = open(os.path.join(out_root, book, "markdown.md"),
                  encoding="utf-8").read()
        segs = _slice_segments(md)
        if not segs:
            return emit("baseline", EXIT_CONTRACT,
                        error={"code": "NO_MARKERS",
                               "message": "%s 的 markdown.md 无页界标记（非 merge_all 产物，拒绝入库）"
                                          % book}, t0=t0)
        lo, hi = segs[0]["s"], segs[-1]["e"]
        ledger_blocks = (led.get("books", {}).get(book, {}).get("blocks")
                         if os.path.exists(ledger_path) else None)
        picked = _pick_segments(segs, pages_cfg, blocks_cfg, ledger_blocks)
        if not picked:
            return emit("baseline", EXIT_CONTRACT,
                        error={"code": "NO_COVER",
                               "message": "抽样页 %s 无覆盖块（%s 覆盖范围 %d-%d）"
                                          % (pages_cfg or "默认首中尾", book, lo, hi)}, t0=t0)

        book_dir = os.path.join(base_dir, book)
        os.makedirs(os.path.join(book_dir, "images"), exist_ok=True)
        items = []
        img_src = os.path.join(out_root, book, "images")
        for seg, sampled in picked:
            with tempfile.TemporaryDirectory(prefix="tbp-base-") as tmp:
                m = _measure(book, seg["text"], tmp, img_src=img_src)
            seg_name = "seg_%d-%d.md" % (seg["s"], seg["e"])
            with open(os.path.join(book_dir, seg_name), "w",
                      encoding="utf-8", newline="\n") as fh:
                fh.write(seg["text"])
            for img in IMG_RE.findall(seg["text"]):
                f = os.path.join(img_src, img)
                if os.path.exists(f):
                    shutil.copy2(f, os.path.join(book_dir, "images", img))
            items.append({"block": "%d-%d" % (seg["s"], seg["e"]),
                          "pages_sampled": sampled,
                          **m})
        entries[book] = items
        if ledger_pdf is None and os.path.exists(ledger_path):
            ledger_pdf = (led.get("books", {}).get(book) or {}).get("pdf")

    baseline = {
        "schema": SCHEMA,
        "subject": args.subject,
        "created_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "thresholds": {"chars_rel": CHAR_TOL, "detectors": 0, "katex_errors": 0},
        "source_pdf": {"name": ledger_pdf},
        "provenance": _fingerprint_snapshot(),
        "books": entries,
    }
    bpath = os.path.join(base_dir, "baseline.json")
    with open(bpath, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(baseline, fh, ensure_ascii=False, indent=2)
    n_seg = sum(len(v) for v in entries.values())
    return emit("baseline", EXIT_OK, workspace=workspace,
                artifacts={"baseline": bpath},
                extra={"subject": args.subject, "books": sorted(entries),
                       "segments": n_seg,
                       "note": "基线已入库；例行比对用 tbp baseline run --subject %s"
                               % args.subject},
                t0=t0)


# ---------- run ----------

def _find_pdf(workspace, name, override):
    if override:
        return os.path.abspath(override) if os.path.exists(override) else None
    for cand in (os.path.join(workspace, name),
                 os.path.join(workspace, "inbox", name),
                 os.path.join(workspace, "pdf", name)):
        if os.path.exists(cand):
            return cand
    return None


def _cmd_run(args, t0):
    workspace = args.workspace
    bpath = os.path.join(workspace, "baselines", args.subject, "baseline.json")
    if not os.path.exists(bpath):
        return emit("baseline", EXIT_USAGE,
                    error={"code": "NO_BASELINE",
                           "message": "未找到 %s（先 tbp baseline init --subject %s）"
                                      % (bpath, args.subject)}, t0=t0)
    baseline = json.load(open(bpath, encoding="utf-8"))
    if baseline.get("schema") != SCHEMA:
        return emit("baseline", EXIT_CONTRACT,
                    error={"code": "BAD_SCHEMA",
                           "message": "%s schema=%s 非本版本契约" % (bpath, baseline.get("schema"))},
                    t0=t0)

    api = resolve_api()
    if not api:
        return emit("baseline", EXIT_BACKEND,
                    error={"code": "NO_ENDPOINT",
                           "message": "未配置网关端点（TBP_BACKEND_API 或 tbp config set backend_endpoint）"},
                    t0=t0)

    books = {args.book: baseline["books"][args.book]} if args.book else baseline["books"]
    drifts, checked = [], 0
    pdf_cache = {}
    for book, items in sorted(books.items()):
        pdf = pdf_cache.get(book)
        if pdf is None:
            name = (baseline.get("source_pdf") or {}).get("name") or (book + ".pdf")
            pdf = _find_pdf(workspace, name, getattr(args, "pdf", None))
            if not pdf:
                return emit("baseline", EXIT_MISSING,
                            error={"code": "NO_PDF",
                                   "message": "找不到 %s（--pdf 显式指定或放入 workspace 根/inbox/pdf/）" % name},
                            t0=t0)
            pdf_cache[book] = pdf

        for item in items:
            s, e = map(int, item["block"].split("-"))
            tmp_dir = tempfile.mkdtemp(prefix="tbp-brrun-")
            blocks_dir = os.path.join(tmp_dir, "blocks", book)   # convert 写册目录，merge 用其父级
            print("[baseline] 重抽 %s %d-%d ..." % (book, s, e), flush=True, file=sys.stderr)
            status, msg = mineru.convert_block(pdf, s, e, blocks_dir, api,
                                               baseline["provenance"].get("tier", "basic"))
            if status != "done":
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return emit("baseline", EXIT_BACKEND,
                            error={"code": "BACKEND_FAILED",
                                   "message": "%s %d-%d 重抽失败：%s" % (book, s, e, msg)},
                            t0=t0)
            tmp_out = os.path.join(tmp_dir, "out")
            merge.merge_one(book, s, e, os.path.join(tmp_dir, "blocks"), tmp_out)
            # 口径对齐（关键）：init 基线取自 out/ 的**修复后**产物，重抽产物必须过同一套
            # S1–S20 才能比——否则 S12 清掉的 HTML 表格标记、S16 降级的坏公式会被误判为
            # 后端漂移（整册化学书实测假漂移 +67% 字符、D7 标签泄漏 0→23）。
            with _quiet():
                rules.run(books=[book], source_dir=os.path.join(tmp_dir, "blocks"),
                          output_dir=tmp_out,
                          quarantine_dir=os.path.join(tmp_dir, "quarantine"))
            seg_md = os.path.join(tmp_out, book, "markdown.md")
            text = open(seg_md, encoding="utf-8").read()
            with tempfile.TemporaryDirectory(prefix="tbp-bm-") as tmp:
                cur = _measure(book, text, tmp,
                               img_src=os.path.join(tmp_out, book, "images"))
            shutil.rmtree(tmp_dir, ignore_errors=True)
            checked += 1

            rel = abs(cur["chars"] - item["chars"]) / max(item["chars"], 1)
            if rel > CHAR_TOL:
                drifts.append({"book": book, "block": item["block"], "metric": "chars",
                               "baseline": item["chars"], "current": cur["chars"],
                               "rel": round(rel, 5)})
            if cur["detectors"] != item["detectors"]:
                diff = {k: [item["detectors"].get(k, 0), cur["detectors"].get(k, 0)]
                        for k in set(item["detectors"]) | set(cur["detectors"])
                        if item["detectors"].get(k, 0) != cur["detectors"].get(k, 0)}
                drifts.append({"book": book, "block": item["block"], "metric": "detectors",
                               "baseline_total": item["detectors_total"],
                               "current_total": cur["detectors_total"], "diff": diff})
            if cur["katex_errors"] != item["katex_errors"] or \
                    cur["katex_missing"] != item["katex_missing"]:
                drifts.append({"book": book, "block": item["block"], "metric": "katex",
                               "baseline": [item["katex_errors"], item["katex_missing"]],
                               "current": [cur["katex_errors"], cur["katex_missing"]]})

    fp_now = _fingerprint_snapshot()
    fp_drift = fp_now["fingerprint"] != baseline["provenance"]["fingerprint"]
    result = {"status": "漂移" if (drifts or fp_drift) else "一致",
              "books": sorted(books), "segments": checked,
              "fingerprint": {"baseline": baseline["provenance"]["fingerprint"],
                              "current": fp_now["fingerprint"], "drift": fp_drift}}
    if drifts or fp_drift:
        if fp_drift:
            drifts.append({"metric": "fingerprint",
                           "baseline": baseline["provenance"]["fingerprint"],
                           "current": fp_now["fingerprint"]})
        return emit("baseline", EXIT_CONTRACT, extra={**result, "drifts": drifts}, t0=t0)
    return emit("baseline", EXIT_OK, extra={**result, "note": "后端指纹未漂移（%d 块样本全部命中基线）" % checked},
                t0=t0)


def execute(args, t0):
    if args.action == "init":
        return _cmd_init(args, t0)
    return _cmd_run(args, t0)
