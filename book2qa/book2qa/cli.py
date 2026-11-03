# -*- coding: utf-8 -*-
"""b2q 命令行入口（arch.md §8 CLI 面）。

全局约定（沿用 book2md）：stdout = 单个 JSON 信封；stderr = 人类可读进度；非交互。
"""
import argparse
import sys
import time

from book2qa import __version__
from book2qa.exit_codes import EXIT_USAGE
from book2qa.envelope import emit


def _import(name):
    """延迟导入命令模块（cli 不许有业务逻辑，也避免 --version 拖重依赖）。"""
    from importlib import import_module
    return import_module("book2qa.commands.%s" % name)


def build_parser():
    p = argparse.ArgumentParser(
        prog="b2q", description="book2md 产物 → 知识点图谱 → 学习能力集合")
    p.add_argument("--version", action="version",
                   version="b2q (book2qa) %s" % __version__)
    p.add_argument("--workspace", help="工作区目录（覆盖四层解析）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("build", help="建库四段（structure/extract/candidates/graph）")
    sp.add_argument("--book", required=True, help="册名（book2md 产物目录名）")
    sp.add_argument("--stage", default="structure",
                    choices=["structure", "extract", "candidates", "graph"])
    sp.add_argument("--source-root", help="book2md 产物根（覆盖三层解析）")
    sp.add_argument("--force", action="store_true", help="忽略已有产物重算")
    # RV-Q2：子命令级 --workspace，允许后置（b2q build ... --workspace P）
    sp.add_argument("--workspace", default=argparse.SUPPRESS,
                    help="工作区目录（覆盖四层解析）")
    sp.set_defaults(func=lambda a, t0: _import("build").execute(a, t0))

    sp = sub.add_parser("recall", help="检索：定位 + 取料（ask/learn/drill/review）")
    sp.add_argument("--book", required=True, help="册名")
    sp.add_argument("--query", required=True, help="学生原话")
    sp.add_argument("--top", type=int, default=5)
    sp.add_argument("--scene", default="ask",
                    choices=["ask", "learn", "drill", "review"])
    sp.add_argument("--context", help="上一轮节点 id（follow_up 绑定用）")
    sp.add_argument("--source-root", help="book2md 产物根（覆盖三层解析）")
    sp.add_argument("--workspace", default=argparse.SUPPRESS,
                    help="工作区目录（覆盖四层解析）")
    sp.set_defaults(func=lambda a, t0: _import("recall").execute(a, t0))

    sp = sub.add_parser("node", help="单节点全料")
    sp.add_argument("node_id", help="知识点 id（M1-C3-S2A-K01）")
    sp.add_argument("--workspace", default=argparse.SUPPRESS,
                    help="工作区目录（覆盖四层解析）")
    sp.set_defaults(func=lambda a, t0: _import("node").execute(a, t0))

    sp = sub.add_parser("index", help="R4 向量索引构建（编码全册教学段落）")
    sp.add_argument("--book", required=True, help="册名")
    sp.add_argument("--source-root", help="book2md 产物根（覆盖三层解析）")
    sp.add_argument("--workspace", default=argparse.SUPPRESS,
                    help="工作区目录（覆盖四层解析）")
    sp.set_defaults(func=lambda a, t0: _import("index").execute(a, t0))

    sp = sub.add_parser("serve", help="启动 HTTP 服务（M1a）")
    sp.add_argument("--workspace", default=argparse.SUPPRESS,
                    help="工作区目录（覆盖四层解析）")
    sp.set_defaults(func=lambda a, t0: _import("serve").main())

    sp = sub.add_parser("config", help="用户配置管理（~/.book2qa/config.json）")
    sp.add_argument("action", choices=["get", "set", "path"])
    sp.add_argument("key", nargs="?", help="workspace | source_root")
    sp.add_argument("value", nargs="?", help="set 时的值")
    sp.add_argument("--workspace", default=argparse.SUPPRESS,
                    help="工作区目录（覆盖四层解析）")
    sp.set_defaults(func=lambda a, t0: _import("config").execute(a, t0))

    return p


def main(argv=None):
    t0 = time.time()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args, t0)
    except SystemExit:
        raise
    except Exception as exc:  # 未预期异常也必须出信封，不许裸 traceback 上 stdout
        return emit(args.cmd, EXIT_USAGE, error="%s: %s" % (type(exc).__name__, exc), t0=t0)


if __name__ == "__main__":
    sys.exit(main())
