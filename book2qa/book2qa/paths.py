# -*- coding: utf-8 -*-
"""路径解析：workspace 与 book2md 产物源根（arch.md §8 / design.md §9）。

workspace 四层：--workspace > B2Q_WORKSPACE > ~/.book2qa/config.json > 当前目录。
source_root 三层：--source-root > B2Q_SOURCE_ROOT > ~/.book2qa/config.json source_root。
book2md 产物只读；本包产物写 workspace/data/。
"""
import json
import os

DATA_SUBDIR = "data"


def _config():
    cfg = os.path.join(os.path.expanduser("~"), ".book2qa", "config.json")
    if os.path.exists(cfg):
        try:
            return json.load(open(cfg, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def resolve_workspace(args=None):
    ws = getattr(args, "workspace", None) if args is not None else None
    if ws:
        return os.path.abspath(ws)
    ws = os.environ.get("B2Q_WORKSPACE")
    if ws:
        return os.path.abspath(ws)
    ws = _config().get("workspace")
    if ws:
        return os.path.abspath(ws)
    return os.getcwd()


def resolve_source_root(args=None):
    """book2md 产物根（其下为 <册名>/markdown.md 等）。"""
    root = getattr(args, "source_root", None) if args is not None else None
    if root:
        return os.path.abspath(root)
    root = os.environ.get("B2Q_SOURCE_ROOT")
    if root:
        return os.path.abspath(root)
    root = _config().get("source_root")
    if root:
        return os.path.abspath(root)
    return None


def data_dir(workspace):
    return os.path.join(workspace, DATA_SUBDIR)


def book_data_dir(workspace, book):
    """按册隔离的产物目录（M3-4：必修二差点覆盖必修一冻结图谱的教训）。"""
    return os.path.join(data_dir(workspace), book)


def ensure_book_data_dir(workspace, book):
    d = book_data_dir(workspace, book)
    os.makedirs(d, exist_ok=True)
    return d


def ensure_data_dir(workspace):
    d = data_dir(workspace)
    os.makedirs(d, exist_ok=True)
    return d


def book_dir(source_root, book):
    return os.path.join(source_root, book)


def book_files(source_root, book):
    """一册书依赖的全部 book2md 产物路径。"""
    d = book_dir(source_root, book)
    return {
        "markdown": os.path.join(d, "markdown.md"),
        "page_map": os.path.join(d, "page_map.md"),
        "images_dir": os.path.join(d, "images"),
    }
