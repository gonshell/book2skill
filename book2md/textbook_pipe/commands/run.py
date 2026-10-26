# -*- coding: utf-8 -*-
"""tbp run — 阶段 B 全流水线（docs/spec-cli.md §6.6，六道质量门）。

以 extract/<book>/contract.json 为输入，执行 修复→渲染→检测→报告 全链路。
失败不落盘：全部产物先写 <out>/<book>.staging/，六门全绿后晋升到 <out>/<book>/
（旧版先挪 .prev-<时间戳>，任何失败时上一版产物完好无损）；
qa_gate.log 全程随 staging，晋升时随册提交。

质量门序列（= run_pipeline.sh 六关语义，行为保持）：
  deps（失败 20）→ fix → html → selfcontain → render → preview → scan3+toc（失败 10）

规则来源优先级：overlays/<book>（书级，最高）> packs/<subject>（学科级）>
引擎内置 S 规则（通用级）；规则包/裁定接线状态如实记录 qa_gate.log（不虚报）。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

from textbook_pipe.exit_codes import EXIT_OK, EXIT_USAGE, EXIT_GATE_FAIL
from textbook_pipe.commands import _envelope, _issues

GATE_ORDER = ["deps", "fix", "html", "selfcontain", "render", "preview", "scan3", "toc"]
GATE_20 = {"deps"}   # 依赖门失败映射退出码 20，其余 10


class GateLog:
    """qa_gate.log 逐关记录（stderr 同步播报）。"""

    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.fh = open(path, "a", encoding="utf-8")

    def line(self, text):
        msg = "[%s] %s" % (time.strftime("%Y-%m-%dT%H:%M:%S%z"), text)
        self.fh.write(msg + "\n")
        self.fh.flush()
        print(msg, file=sys.stderr)

    def close(self):
        if self.fh and not self.fh.closed:
            self.fh.close()


def _gate_deps(book, staging, log, ctx):
    """门1：Node.js / KaTeX 资产 / 输入契约存在性（run_pipeline.sh 关0语义）。"""
    node = shutil.which("node")
    if not node:
        return "未找到 node，KaTeX 预渲染无法执行"
    try:
        r = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=30)
        node_ver = (r.stdout or "").strip() or "unknown"
    except OSError as e:
        return "node 不可执行：%s" % e
    from textbook_pipe.engine.render import KATEX_DIR
    if not os.path.isdir(os.path.join(KATEX_DIR, "fonts")):
        return "KaTeX 资产缺失：%s/fonts" % KATEX_DIR
    log.line("[deps] node=%s · katex_assets=在位" % node_ver)
    return None


def _gate_fix(book, staging, log, ctx):
    """门2：修复流水线。抽取 md 快照 → 页眉噪音清理 + 公式双表示（历史 postprocess
    链，合并后、S 规则前执行过一次）→ S1–S20（rules.run，从基线干净重跑）。"""
    from textbook_pipe.engine import rules, reporting

    baseline_dir = os.path.join(staging, "baseline")
    os.makedirs(baseline_dir, exist_ok=True)
    baseline_md = os.path.join(baseline_dir, book + ".markdown.md")
    shutil.copy2(ctx["extract_md"], baseline_md)

    md = open(baseline_md, encoding="utf-8").read()
    md = reporting.clean_noise(md)
    md = reporting.add_formula_alt(md)
    open(baseline_md, "w", encoding="utf-8").write(md)

    img_src = os.path.join(ctx["extract_dir"], "images")
    if os.path.isdir(img_src):
        shutil.copytree(img_src, os.path.join(staging, book, "images"), dirs_exist_ok=True)

    steps = rules.run(books=[book], source_dir=baseline_dir, output_dir=staging)
    log.line("[fix] S 规则计数 %s" % json.dumps(steps.get(book, {}), ensure_ascii=False))
    return None


def _gate_html(book, staging, log, ctx):
    """门3：双版本 HTML（KaTeX 预渲染 0 错误要求 + 字体内联）。"""
    from textbook_pipe.engine import render
    reader = render.run(books=[book], variant="reader",
                        source_dir=staging, out_dir=os.path.join(staging, "html"))
    kb = render.run(books=[book], variant="kb",
                    source_dir=staging, out_dir=os.path.join(staging, "kb_html"))
    errs = reader["errors"] + kb["errors"]
    missing = reader["missing"] + kb["missing"]
    if errs:
        return "渲染错误 %d 处（KaTeX 预渲染要求 0）" % len(errs)
    if missing:
        return "缺失图片 %d 处" % len(missing)
    log.line("[html] 阅读版+知识库版 KaTeX 全部渲染成功")
    return None


def _gate_selfcontain(book, staging, log, ctx):
    """门4：自包含校验（run_pipeline.sh 关2 内嵌校验语义，行为保持）。"""
    bad = []
    for tag, path in (("阅读", os.path.join(staging, "html", book + ".html")),
                      ("知识库", os.path.join(staging, "kb_html", book + ".html"))):
        if not os.path.exists(path):
            bad.append("%s %s 缺失" % (tag, book))
            continue
        d = open(path, encoding="utf-8").read()
        fonts = d.count("data:font/woff2")
        ext = len(re.findall(r"url\((?!data:)[^)]+\)", d)) + \
            len(re.findall(r'(?:src|href)="(?!data:|#)[^"]+"', d))
        raw = len(re.findall(r"\$[^<\n]{1,30}\$", d))
        if fonts != 20:
            bad.append("%s 字体内联 %d/20" % (tag, fonts))
        if ext:
            bad.append("%s 外部引用 %d" % (tag, ext))
        if raw:
            bad.append("%s 裸 LaTeX %d" % (tag, raw))
    if bad:
        return "；".join(bad)
    log.line("[selfcontain] 两版均 20 字体内联 · 0 外部引用 · 0 裸 LaTeX")
    return None


def _gate_render(book, staging, log, ctx):
    """门5a：渲染完整性（游离 $$/奇数 $/块内奇数 $，零容忍）。"""
    from textbook_pipe.engine.inspectors import integrity
    integ = integrity.scan(source_dir=staging, books=[book])
    hits = {k: len(v) for k, v in integ.items() if v}
    if hits:
        return "渲染完整性未归零：%s" % hits
    log.line("[render] 行内游离$$/奇数$行/块内奇数$ 全部为 0")
    return None


def _gate_preview(book, staging, log, ctx):
    """门5b：目标渲染器规则验收（markdown-it-texmath dollars 语义复刻）。"""
    from textbook_pipe.engine.inspectors import texmath
    tex = texmath.run(source_dir=staging, books=[book])
    if tex["total"]:
        return "预览渲染规则未归零（总计 %d 处）" % tex["total"]
    log.line("[preview] 行内/块公式定界规则全部合规")
    return None


def _gate_scan3_toc(book, staging, log, ctx):
    """门6：D1–D10 探测器归零 + TOC/质检报告/issues 重生（regen_toc_qa 语义）。"""
    from textbook_pipe.engine import reporting
    from textbook_pipe.engine.inspectors import detectors

    det = detectors.run(source_dir=staging, books=[book])
    if det["total"]:
        return "scan3 未归零（总计 %d 处）" % det["total"]

    reporting.configure(ctx["workspace"])   # 页码映射需要 blocks/<book>/（无则映射为空）
    md = open(os.path.join(staging, book, "markdown.md"), encoding="utf-8").read()
    pmap = reporting.extract_page_map(book)
    qa_patterns = {k: len(v.findall(md)) for k, v in reporting.QA_PATTERNS.items()}

    toc_md = "# 总目录\n\n## %s\n" % book
    for lv, t in reporting.build_toc(book, md):
        toc_md += "%s- %s\n" % ("  " * (lv - 2), t)
    open(os.path.join(staging, book, "TOC.md"), "w", encoding="utf-8").write(toc_md)

    qa_md = "# 转换质检报告\n\n"
    qa_md += "| 册 | 字符数 | 页码映射 | " + " | ".join(reporting.QA_COLUMNS) + " |\n"
    qa_md += "|---|---|---|" + "---|" * len(reporting.QA_COLUMNS) + "\n"
    qa_md += "| %s | %d | %d | " % (book, len(md), len(pmap))
    qa_md += " | ".join(str(qa_patterns.get(k, 0)) for k in reporting.QA_COLUMNS) + " |\n"
    qa_md += "\n> 渲染无误 ≠ 内容与原书一致：以上命中项为人工复核队列。\n"
    open(os.path.join(staging, book, "质检报告.md"), "w", encoding="utf-8").write(qa_md)

    # 页码映射表（postprocess §3 语义，格式逐字保持：final/<book>/page_map.md）
    if pmap:
        pmd = "# %s 页码映射表（物理页 → 教材页码）\n\n" % book
        pmd += "| 物理页 | 教材页 |\n| --- | --- |\n"
        for phys in sorted(pmap):
            pmd += "| %s | %s |\n" % (phys, pmap[phys])
        open(os.path.join(staging, book, "page_map.md"), "w", encoding="utf-8").write(pmd)

    issues = _issues.collect(book, staging, books=[book])
    _issues.write(issues, os.path.join(staging, book, "issues.json"))

    log.line("[scan3+toc] D1–D10 归零；TOC.md / 质检报告.md / issues.json 已重生")
    return None


GATES = {"deps": _gate_deps, "fix": _gate_fix, "html": _gate_html,
         "selfcontain": _gate_selfcontain, "render": _gate_render,
         "preview": _gate_preview, "scan3": _gate_scan3_toc, "toc": _gate_scan3_toc}


def _promote(book, staging, out_root, log):
    """staging/<book> → out/<book>（旧版挪 .prev-<时间戳>，仅保留最近一份）。

    Windows 下打开的日志句柄会锁住目录，改名前必须先关日志；
    落位后以追加模式重开续写（记录随册提交）。
    """
    src = os.path.join(staging, book)
    dst = os.path.join(out_root, book)
    log.line("[promote] 开始晋升（旧版挪 .prev-<时间戳>，仅保留最近一份）")
    log.close()
    if os.path.isdir(dst):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        prev = os.path.join(out_root, "%s.prev-%s" % (book, stamp))
        os.replace(dst, prev)
        for d in os.listdir(out_root):
            if d.startswith(book + ".prev-") and d != os.path.basename(prev):
                shutil.rmtree(os.path.join(out_root, d), ignore_errors=True)
    os.replace(src, dst)
    # 双版本 HTML 目录随册落位（spec §4：out/<book>/{html,kb_html}/）
    for sub in ("html", "kb_html"):
        s = os.path.join(staging, sub)
        if os.path.isdir(s):
            shutil.move(s, os.path.join(dst, sub))
    shutil.rmtree(staging, ignore_errors=True)
    log2 = GateLog(os.path.join(dst, "qa_gate.log"))
    log2.line("[promote] 产物已提交 %s" % dst)
    log2.close()


def execute(args, t0):
    workspace = args.workspace
    book = args.book
    out_root = os.path.join(workspace, "out")
    extract_dir = os.path.join(workspace, "extract", book)
    contract_path = os.path.join(extract_dir, "contract.json")
    if not os.path.exists(contract_path):
        return _envelope.emit("run", 50, workspace=workspace, book=book,
                              error={"code": "NO_CONTRACT",
                                     "message": "未找到 %s（先执行 extract/onboard）" % contract_path}, t0=t0)
    contract = json.load(open(contract_path, encoding="utf-8"))
    extract_md = contract.get("markdown", "")
    if not os.path.exists(extract_md):
        return _envelope.emit("run", 50, workspace=workspace, book=book,
                              error={"code": "NO_EXTRACT_MD",
                                     "message": "contract 指向的抽取 md 不存在：%s" % extract_md}, t0=t0)

    # 科目配置：缺失 → 20（onboard 会生成模板）
    from textbook_pipe.commands.onboard import _subject_config_path
    cpath = _subject_config_path(args.subject)
    if not os.path.exists(cpath):
        return _envelope.emit("run", EXIT_USAGE, workspace=workspace, book=book,
                              error={"code": "NO_SUBJECT_CONFIG",
                                     "message": "科目配置 %s 不存在（先执行 onboard 或手工创建）" % cpath}, t0=t0)
    subject_cfg = json.load(open(cpath, encoding="utf-8"))

    if args.gates.strip().lower() == "all":
        gates = list(GATE_ORDER)
    else:
        gates = [g.strip() for g in args.gates.split(",") if g.strip()]
    unknown = [g for g in gates if g not in GATE_ORDER]
    if unknown:
        return _envelope.emit("run", EXIT_USAGE, workspace=workspace, book=book,
                              error={"code": "BAD_GATES",
                                     "message": "未知质量门 %s（可选：%s）" % (unknown, ",".join(GATE_ORDER))}, t0=t0)
    full_run = set(gates) == set(GATE_ORDER)

    staging = os.path.join(out_root, book + ".staging")
    shutil.rmtree(staging, ignore_errors=True)
    book_dir = os.path.join(staging, book)
    os.makedirs(book_dir, exist_ok=True)
    gate_log_path = os.path.join(book_dir, "qa_gate.log")
    log = GateLog(gate_log_path)

    ctx = {"workspace": workspace, "extract_dir": extract_dir, "extract_md": extract_md}
    warnings = []
    log.line("tbp run book=%s subject=%s gates=%s workspace=%s"
             % (book, args.subject, ",".join(gates), workspace))
    log.line("规则来源：引擎内置 S 规则；packs/%s 引用=%s（学科规则包机制未接线，如实记录）"
             % (args.subject, subject_cfg.get("rules_pack")))
    warnings.append("学科规则包机制尚未接线（packs/ 骨架空），本轮仅引擎内置 S 规则生效")
    if os.path.isdir(os.path.join(workspace, "overlays", book)):
        warnings.append("检测到 overlays/%s（C 档裁定规则），overlay 机制尚未接线，本轮未生效" % book)

    rc, failed_gate = EXIT_OK, None
    try:
        for g in GATE_ORDER:
            if g not in gates:
                continue
            t1 = time.time()
            try:
                err = GATES[g](book, staging, log, ctx)
            except Exception as e:   # 引擎异常 = 该门失败，信封如实上报
                err = "%s: %s" % (type(e).__name__, e)
            if err:
                rc = EXIT_USAGE if g in GATE_20 else EXIT_GATE_FAIL
                failed_gate = g
                log.line("[%s] FAIL（%s）" % (g, err))
                break
            log.line("[%s] PASS（%.1fs）" % (g, time.time() - t1))

        if rc == EXIT_OK and full_run:
            _promote(book, staging, out_root, log)
    finally:
        log.close()

    if rc != EXIT_OK:
        return _envelope.emit("run", rc, workspace=workspace, book=book,
                              error={"code": "GATE_FAILED", "gate": failed_gate,
                                     "message": "质量门 %s 未通过（详见 %s）" % (failed_gate, gate_log_path)},
                              warnings=warnings, t0=t0)

    if not full_run:
        # 子集运行（调试单关）：产物留 staging 不晋升，避免半成品混入交付区
        return _envelope.emit("run", EXIT_OK, workspace=workspace, book=book,
                              artifacts={"staging": staging,
                                         "qa_gate_log": gate_log_path},
                              warnings=warnings + ["--gates 为子集（%s），产物保留在 staging 未晋升"
                                                   % ",".join(gates)], t0=t0)

    out_dir = os.path.join(out_root, book)
    return _envelope.emit("run", EXIT_OK, workspace=workspace, book=book, out_dir=out_dir,
                          artifacts={"markdown": os.path.join(out_dir, "markdown.md"),
                                     "html": os.path.join(out_dir, "html", book + ".html"),
                                     "kb_html": os.path.join(out_dir, "kb_html", book + ".html"),
                                     "toc": os.path.join(out_dir, "TOC.md"),
                                     "qa_report": os.path.join(out_dir, "质检报告.md"),
                                     "issues": os.path.join(out_dir, "issues.json"),
                                     "qa_gate_log": os.path.join(out_dir, "qa_gate.log")},
                          warnings=warnings, t0=t0)
