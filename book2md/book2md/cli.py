# -*- coding: utf-8 -*-
"""b2m 命令行入口（docs/spec-cli.md）。

全局约定：stdout = 单个 JSON 信封；stderr = 人类可读进度；非交互。
"""
import argparse
import os
import sys
import time

from book2md.exit_codes import (EXIT_OK, EXIT_USAGE)
from book2md.commands import _envelope

DEFAULT_BOOKS = ["必修第一册", "必修第二册", "选择性必修第一册", "选择性必修第二册", "选择性必修第三册"]


def _resolve_workspace(args):
    """四层解析（spec §2）：--workspace > B2M_WORKSPACE > ~/.book2md/config.json > 当前目录。"""
    ws = getattr(args, "workspace", None)
    if ws:
        return os.path.abspath(ws)
    ws = os.environ.get("B2M_WORKSPACE")
    if ws:
        return os.path.abspath(ws)
    cfg = os.path.join(os.path.expanduser("~"), ".book2md", "config.json")
    if os.path.exists(cfg):
        import json
        try:
            ws = json.load(open(cfg, encoding="utf-8")).get("workspace")
            if ws:
                return os.path.abspath(ws)
        except Exception:
            pass
    return os.getcwd()


def build_parser():
    p = argparse.ArgumentParser(prog="b2m", description="教材 PDF → md+图片+公式 → 双版本单体 HTML 转换工具")
    p.add_argument("--workspace", help="工作区目录（覆盖四层解析）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("config", help="用户配置管理（~/.book2md/config.json）")
    sp.add_argument("action", choices=["get", "set", "path"])
    sp.add_argument("key", nargs="?", help="workspace | backend | backend_endpoint | subjects")
    sp.add_argument("value", nargs="?", help="set 时的值")
    sp.set_defaults(func=lambda a, t0: _import("config").execute(a, t0))

    sp = sub.add_parser("report", help="重生 TOC.md 与 质检报告.md")
    sp.add_argument("--book", help="册名；缺省聚合 out/ 下全部书")
    sp.set_defaults(func=lambda a, t0: _import("report").execute(a, t0))

    sp = sub.add_parser("scan", help="只读体检（D1–D10 + 渲染完整性 + texmath 语义）")
    sp.add_argument("--book", required=True, help="册名")
    sp.add_argument("--source", choices=["out", "extract"], default="out")
    sp.set_defaults(func=lambda a, t0: _import("scan").execute(a, t0))

    sp = sub.add_parser("run", help="阶段 B 全流水线（质量门）")
    sp.add_argument("--book", required=True, help="册名")
    sp.add_argument("--subject", required=True, help="科目配置 id")
    sp.add_argument("--gates", default="all", help="逗号分隔子集（deps,fix,html,selfcontain,render,preview,scan3,toc）")
    sp.add_argument("--workspace", default=argparse.SUPPRESS, help="工作区目录（覆盖四层解析）")
    sp.set_defaults(func=lambda a, t0: _import("run").execute(a, t0))

    sp = sub.add_parser("convert", help="一条命令全流程（抽取 + 流水线）")
    sp.add_argument("--pdf", required=True, help="教材 PDF 路径")
    sp.add_argument("--subject", required=True, help="科目配置 id")
    sp.add_argument("--page-range", help="物理页范围 N-M")
    sp.add_argument("--force", action="store_true")
    sp.add_argument("--workspace", default=argparse.SUPPRESS, help="工作区目录（覆盖四层解析）")
    sp.set_defaults(func=lambda a, t0: _convert(a, t0))

    sp = sub.add_parser("onboard", help="新书接入（抽取 + 基线扫描 → issues.json）")
    sp.add_argument("--subject", required=True, help="科目配置 id")
    sp.add_argument("--pdf", required=True, help="教材 PDF 路径")
    sp.add_argument("--page-range", help="物理页范围 N-M")
    sp.add_argument("--force", action="store_true")
    sp.add_argument("--workspace", default=argparse.SUPPRESS, help="工作区目录（覆盖四层解析）")
    sp.set_defaults(func=lambda a, t0: _import("onboard").execute(a, t0))

    sp = sub.add_parser("extract", help="仅抽取（PDF → Canonical Extraction v1）")
    sp.add_argument("--book", required=True, help="册名（=PDF 文件名去扩展名；不一致时以文件名为准并告警）")
    sp.add_argument("--pdf", required=True, help="教材 PDF 路径")
    sp.add_argument("--page-range", help="物理页范围 N-M")
    sp.add_argument("--force", action="store_true")
    sp.add_argument("--workspace", default=argparse.SUPPRESS, help="工作区目录（覆盖四层解析）")
    sp.set_defaults(func=lambda a, t0: _import("extract").execute(a, t0))

    sp = sub.add_parser("baseline", help="基准回归（防后端静默漂移，spec §6.10）")
    sp.add_argument("action", choices=["init", "run"])
    sp.add_argument("--subject", required=True, help="科目配置 id")
    sp.add_argument("--book", help="限定单册（默认 init=全部已转换书 / run=基线全部书）")
    sp.add_argument("--pdf", help="run 用：PDF 路径（缺省按基线记录名在 workspace 根/inbox/pdf/ 查找）")
    sp.add_argument("--workspace", default=argparse.SUPPRESS, help="工作区目录（覆盖四层解析）")
    sp.set_defaults(func=lambda a, t0: _import("baseline").execute(a, t0))

    return p


def _import(name):
    import importlib
    return importlib.import_module("book2md.commands." + name)


def _import(name):
    import importlib
    return importlib.import_module("book2md.commands." + name)


def _convert(a, t0):
    """b2m convert = extract + run 的原子组合（docs/spec-cli.md §6.7）。

    C 档默认处理策略：引擎按现有规则处理全部内容，存疑条目列入质检报告复核队列。
    """
    from types import SimpleNamespace
    from book2md.commands import onboard as onboard_mod

    # 前置检查复用 onboard 语义：PDF 存在性、科目配置（缺失生成模板 + 20）、网关预检
    pre = SimpleNamespace(workspace=a.workspace, pdf=a.pdf, subject=a.subject,
                          page_range=a.page_range, force=a.force)
    pdf = os.path.abspath(a.pdf)
    if not os.path.exists(pdf):
        return _envelope.emit("convert", 50, workspace=a.workspace,
                              error={"code": "NOT_FOUND", "message": "PDF 不存在：%s" % pdf}, t0=t0)
    book = os.path.splitext(os.path.basename(pdf))[0]
    cpath = onboard_mod._subject_config_path(a.subject)
    if not os.path.exists(cpath):
        import json
        tpl = dict(onboard_mod.SUBJECT_TEMPLATE)
        tpl["subject"] = a.subject
        tpl["rules_pack"] = "packs/%s.json" % a.subject
        os.makedirs(onboard_mod.CONFIGS_DIR, exist_ok=True)
        json.dump(tpl, open(cpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("!! 科目配置不存在，已生成模板：%s（编辑后重跑）" % cpath, file=sys.stderr)
        return _envelope.emit("convert", EXIT_USAGE, workspace=a.workspace, book=book,
                              artifacts={"subject_template": cpath},
                              error={"code": "NO_SUBJECT_CONFIG",
                                     "message": "科目配置 %s 不存在，模板已生成，编辑后重跑" % cpath}, t0=t0)
    api = _import("_endpoints").resolve_api()
    if api is None:
        return _envelope.emit("convert", EXIT_USAGE, workspace=a.workspace, book=book,
                              error={"code": "NO_ENDPOINT",
                                     "message": "未配置网关端点：设环境变量 B2M_BACKEND_API，"
                                                "或 b2m config set backend_endpoint http://<host>:<port>"}, t0=t0)
    reachable, detail = onboard_mod._precheck_gateway(api)
    if not reachable:
        return _envelope.emit("convert", 30, workspace=a.workspace, book=book,
                              error={"code": "GATEWAY_UNREACHABLE",
                                     "message": "网关不可达 %s（%s）" % (api, detail)}, t0=t0)

    # 阶段一：抽取
    from book2md.extractors import mineru
    from book2md.commands.extract import parse_page_range
    start, end = parse_page_range(a.page_range)
    try:
        mineru.extract_pdf(pdf, book, a.workspace, api, tier="basic",
                           start_page=start if start is not None else mineru.DEFAULT_START_PAGE,
                           end_page=end, force=a.force)
    except RuntimeError as e:
        return _envelope.emit("convert", 30, workspace=a.workspace, book=book,
                              error={"code": "BACKEND_FAILED", "message": str(e)}, t0=t0)

    # 阶段二：质量门流水线（全绿自动晋升 out/<book>/）
    run_args = SimpleNamespace(workspace=a.workspace, book=book, subject=a.subject, gates="all")
    return _import("run").execute(run_args, t0)


def main(argv=None):
    t0 = time.time()
    args = build_parser().parse_args(argv)
    if args.cmd in ("report", "scan", "run", "onboard", "convert", "extract", "baseline"):
        args.workspace = _resolve_workspace(args)
    try:
        return args.func(args, t0)
    except FileNotFoundError as e:
        return _envelope.emit(args.cmd, 50, error={"code": "NOT_FOUND", "message": str(e)}, t0=t0)
    except ValueError as e:
        return _envelope.emit(args.cmd, EXIT_USAGE, error={"code": "BAD_INPUT", "message": str(e)}, t0=t0)
    except Exception as e:  # 未知异常：信封如实上报，不静默
        return _envelope.emit(args.cmd, 1, error={"code": "INTERNAL", "message": "%s: %s" % (type(e).__name__, e)}, t0=t0)


if __name__ == "__main__":
    sys.exit(main())
