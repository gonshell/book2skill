# -*- coding: utf-8 -*-
"""tbp 命令行入口（docs/spec-cli.md）。

全局约定：stdout = 单个 JSON 信封；stderr = 人类可读进度；非交互。
"""
import argparse
import os
import sys
import time

from textbook_pipe.exit_codes import (EXIT_OK, EXIT_USAGE)
from textbook_pipe.commands import _envelope

DEFAULT_BOOKS = ["必修第一册", "必修第二册", "选择性必修第一册", "选择性必修第二册", "选择性必修第三册"]


def _resolve_workspace(args):
    """四层解析（spec §2）：--workspace > TBP_WORKSPACE > ~/.tbp/config.json > 当前目录。"""
    ws = getattr(args, "workspace", None)
    if ws:
        return os.path.abspath(ws)
    ws = os.environ.get("TBP_WORKSPACE")
    if ws:
        return os.path.abspath(ws)
    cfg = os.path.join(os.path.expanduser("~"), ".tbp", "config.json")
    if os.path.exists(cfg):
        import json
        try:
            ws = json.load(open(cfg, encoding="utf-8")).get("workspace")
            if ws:
                return os.path.abspath(ws)
        except Exception:
            pass
    return os.getcwd()


def _todo(name, feature):
    """未接线命令的统一信封（能力缺口显式可见，不静默）。"""
    return _envelope.emit(name, EXIT_USAGE,
                          error={"code": "NOT_WIRED",
                                 "message": "%s 依赖尚未完成接线的组件：%s（见 AGENT.md 欠账台账）" % (name, feature)})


def build_parser():
    p = argparse.ArgumentParser(prog="tbp", description="教材 PDF → md+图片+公式 → 双版本单体 HTML 转换工具")
    p.add_argument("--workspace", help="工作区目录（覆盖四层解析）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("config", help="用户配置管理（~/.tbp/config.json）")
    sp.add_argument("action", choices=["get", "set", "path"])
    sp.add_argument("key", nargs="?", help="workspace | backend | subjects")
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
    sp.set_defaults(func=lambda a, t0: _run_gate(a, t0))

    sp = sub.add_parser("convert", help="一条命令全流程（抽取 + 流水线）")
    sp.add_argument("--pdf", required=True, help="教材 PDF 路径")
    sp.add_argument("--subject", required=True, help="科目配置 id")
    sp.set_defaults(func=lambda a, t0: _todo("convert", "抽取适配器接线（extractors/mineru.py）"))

    sp = sub.add_parser("onboard", help="新书接入（抽取 + 基线扫描 → issues.json）")
    sp.add_argument("--subject", required=True, help="科目配置 id")
    sp.add_argument("--pdf", required=True, help="教材 PDF 路径")
    sp.add_argument("--page-range", help="物理页范围 N-M")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=lambda a, t0: _todo("onboard", "抽取适配器接线（extractors/mineru.py）"))

    sp = sub.add_parser("extract", help="仅抽取（PDF → Canonical Extraction v1）")
    sp.add_argument("--book", required=True, help="册名")
    sp.add_argument("--pdf", required=True, help="教材 PDF 路径")
    sp.add_argument("--page-range", help="物理页范围 N-M")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=lambda a, t0: _todo("extract", "抽取适配器接线（extractors/mineru.py）"))

    sp = sub.add_parser("baseline", help="基准回归（防后端静默漂移）")
    sp.add_argument("action", choices=["init", "run"])
    sp.add_argument("--subject", help="科目配置 id")
    sp.set_defaults(func=lambda a, t0: _todo("baseline", "抽取适配器接线（页面重抽部分）"))

    return p


def _import(name):
    import importlib
    return importlib.import_module("textbook_pipe.commands." + name)


def _run_gate(a, t0):
    """tbp run：阶段 B 质量门编排。

    当前接线状态：修复引擎（rules）/渲染（render）/探测器（inspectors）已就位；
    输入契约检查按 spec 执行（extract/<book>/contract.json 缺失 → 50）。
    完整编排（staging 原子落盘等）在抽取适配器接线后启用。
    """
    from textbook_pipe import exit_codes as ec
    workspace = _resolve_workspace(a)
    contract = os.path.join(workspace, "extract", a.book, "contract.json")
    if not os.path.exists(contract):
        return _envelope.emit("run", ec.EXIT_MISSING, workspace=workspace, book=a.book,
                              error={"code": "NO_CONTRACT",
                                     "message": "未找到 %s（先执行 extract/onboard）" % contract})
    return _todo("run", "质量门编排接线（依赖抽取适配器，切片 4）")


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
