# -*- coding: utf-8 -*-
"""b2m onboard — 新书接入（docs/spec-cli.md §6.4，人机协作回路入口）。

建工作区 → 加载科目配置（缺失则生成模板后退出码 20）→ 网关预检 →
抽取 → 全量基线扫描（extract 源）→ issues.json + provenance.json。
不产出 HTML（裁定完成后由 run 产出）。
"""
import argparse
import json
import os
import subprocess
import sys

from book2md.exit_codes import EXIT_OK, EXIT_USAGE, EXIT_BACKEND
from book2md.commands import _envelope
from book2md.commands._endpoints import resolve_api

CONFIGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configs")

SUBJECT_TEMPLATE = {
    "subject": None,               # 科目 id（写入时填充）
    "toc_chapter_pattern": "<TOC 章目识别正则，占位——编辑后删除本注释字段>",
    "rules_pack": "packs/<subject>.json",
    "note": "编辑本文件（补 TOC 章目正则与规则包）后重跑 b2m onboard",
}


def _subject_config_path(subject):
    return os.path.join(CONFIGS_DIR, subject + ".json")


def _precheck_gateway(api):
    """网关连通性预检：curl GET {api}/version，超时 5s。

    返回 (reachable, detail)；连接层失败即不可达（HTTP 状态由后续抽取如实上报）。
    """
    cmd = ["curl", "-sS", "-m", "5", "-o", os.devnull, "-w", "%{http_code}", api + "/version"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    if r.returncode != 0:
        return False, (r.stderr or "").strip()[:200]
    return True, "HTTP " + r.stdout.strip()


def execute(args, t0):
    workspace = args.workspace
    pdf = os.path.abspath(args.pdf)
    if not os.path.exists(pdf):
        return _envelope.emit("onboard", 50, workspace=workspace,
                              error={"code": "NOT_FOUND", "message": "PDF 不存在：%s" % pdf}, t0=t0)
    book = os.path.splitext(os.path.basename(pdf))[0]

    # ② 科目配置：不存在 → 生成模板 + 退出码 20（stderr 指引编辑后重跑）
    cpath = _subject_config_path(args.subject)
    if not os.path.exists(cpath):
        tpl = dict(SUBJECT_TEMPLATE)
        tpl["subject"] = args.subject
        tpl["rules_pack"] = "packs/%s.json" % args.subject
        os.makedirs(CONFIGS_DIR, exist_ok=True)
        json.dump(tpl, open(cpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("!! 科目配置不存在，已生成模板：%s" % cpath, file=sys.stderr)
        print("!! 请编辑该文件（TOC 章目正则、规则包）后重跑 b2m onboard", file=sys.stderr)
        return _envelope.emit("onboard", EXIT_USAGE, workspace=workspace, book=book,
                              artifacts={"subject_template": cpath},
                              error={"code": "NO_SUBJECT_CONFIG",
                                     "message": "科目配置 %s 不存在，模板已生成，编辑后重跑" % cpath}, t0=t0)

    # ③ 网关端点 + 连通性预检
    api = resolve_api()
    if api is None:
        return _envelope.emit("onboard", EXIT_USAGE, workspace=workspace, book=book,
                              error={"code": "NO_ENDPOINT",
                                     "message": "未配置网关端点：设环境变量 B2M_BACKEND_API，"
                                                "或 b2m config set backend_endpoint http://<host>:<port>"}, t0=t0)
    reachable, detail = _precheck_gateway(api)
    if not reachable:
        return _envelope.emit("onboard", EXIT_BACKEND, workspace=workspace, book=book,
                              error={"code": "GATEWAY_UNREACHABLE",
                                     "message": "网关不可达 %s（%s）；检查网络后重试" % (api, detail)}, t0=t0)

    # ④ 抽取（ledger 断点续跑）→ 归一化 → contract.json
    from book2md.extractors import mineru
    from book2md.commands.extract import parse_page_range
    start, end = parse_page_range(args.page_range)
    try:
        stats = mineru.extract_pdf(pdf, book, workspace, api, tier="basic",
                                   start_page=start if start is not None else mineru.DEFAULT_START_PAGE,
                                   end_page=end, force=args.force)
    except RuntimeError as e:
        return _envelope.emit("onboard", EXIT_BACKEND, workspace=workspace, book=book,
                              error={"code": "BACKEND_FAILED", "message": str(e)}, t0=t0)

    contract = json.load(open(stats["contract"], encoding="utf-8"))

    # ⑤ 全量基线扫描（extract 源：规则尚未生效的原始错识量）→ out/<book>/issues.json
    # scan.execute 独立运行时自带 stdout 信封；onboard 是信封单出口，
    # 故收编其 stdout 到 stderr（内容不丢，纪律不破）
    import io
    import contextlib
    from book2md.commands import scan as scan_mod
    scan_args = argparse.Namespace(workspace=workspace, source="extract", book=book)
    scan_buf = io.StringIO()
    with contextlib.redirect_stdout(scan_buf):
        scan_rc = scan_mod.execute(scan_args, t0)
    if scan_buf.getvalue():
        sys.stderr.write(scan_buf.getvalue())
    if scan_rc != EXIT_OK:
        return scan_rc

    # ⑥ provenance.json（§6.3：指纹必须含 PDF 哈希；网关未上报字段一律 None）
    from book2md.commands import _provenance
    out_dir = os.path.join(workspace, "out", book)
    prov = _provenance.write(pdf, "mineru-remote", api, "basic",
                             contract["meta"]["extracted_at"],
                             os.path.join(out_dir, "provenance.json"))

    issues_path = os.path.join(out_dir, "issues.json")
    issues = json.load(open(issues_path, encoding="utf-8"))
    warnings = []
    if issues["counts"]["B"] or issues["counts"]["C"]:
        warnings.append("抽取原始版共 %d 处命中（tier 细分在 run 环节进行），见 issues.json" % (issues["counts"]["B"] + issues["counts"]["C"]))

    return _envelope.emit("onboard", EXIT_OK, workspace=workspace, book=book, out_dir=out_dir,
                          artifacts={"issues": issues_path, "provenance": prov,
                                     "contract": stats["contract"]},
                          warnings=warnings, t0=t0)
