# -*- coding: utf-8 -*-
"""tbp extract — 仅抽取（docs/spec-cli.md §6.5）。

PDF → Canonical Extraction v1：账本断点续跑 → 分块提交网关 → 页序归一化 →
contract.json 落盘。不扫描不修复，不写 out/（out/ 是阶段 B 产物区）。
"""
import os
import re

from textbook_pipe.exit_codes import EXIT_OK, EXIT_USAGE, EXIT_BACKEND
from textbook_pipe.commands import _envelope
from textbook_pipe.commands._endpoints import resolve_api


def parse_page_range(text):
    """'N-M' → (N, M)；'N' → (N, N)；None → (None, None)。非法格式抛 ValueError。"""
    if not text:
        return None, None
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", text.strip())
    if not m:
        raise ValueError("page-range 格式应为 N-M（物理页范围），收到 %r" % text)
    a, b = int(m.group(1)), int(m.group(2) or m.group(1))
    if a > b:
        raise ValueError("page-range 起止颠倒：%s" % text)
    return a, b


def execute(args, t0):
    from textbook_pipe.extractors import mineru

    pdf = os.path.abspath(args.pdf)
    if not os.path.exists(pdf):
        return _envelope.emit("extract", 50, error={"code": "NOT_FOUND",
                               "message": "PDF 不存在：%s" % pdf}, t0=t0)

    # book id = PDF 文件名去扩展名（spec §6.5）；与 --book 不一致时以文件名为准并告警
    stem = os.path.splitext(os.path.basename(pdf))[0]
    warnings = []
    if args.book != stem:
        warnings.append("--book %r 与 PDF 文件名 %r 不一致，以文件名为准" % (args.book, stem))
    book = stem

    api = resolve_api()
    if api is None:
        return _envelope.emit("extract", EXIT_USAGE, book=book,
                              error={"code": "NO_ENDPOINT",
                                     "message": "未配置网关端点：设环境变量 TBP_BACKEND_API，"
                                                "或 tbp config set backend_endpoint http://<host>:<port>"}, t0=t0)

    start, end = parse_page_range(getattr(args, "page_range", None))
    if end is None:
        try:
            end = mineru.pdf_page_count(pdf)   # 需要可选增强 [extract]（pymupdf）
        except RuntimeError as e:
            return _envelope.emit("extract", EXIT_USAGE, book=book,
                                  error={"code": "NO_PAGECOUNT", "message": str(e)}, t0=t0)

    try:
        stats = mineru.extract_pdf(pdf, book, args.workspace, api, tier="basic",
                                   start_page=start if start is not None else mineru.DEFAULT_START_PAGE,
                                   end_page=end, force=args.force)
    except RuntimeError as e:
        return _envelope.emit("extract", EXIT_BACKEND, book=book, workspace=args.workspace,
                              error={"code": "BACKEND_FAILED", "message": str(e)}, t0=t0)

    return _envelope.emit("extract", EXIT_OK, workspace=args.workspace, book=book,
                          out_dir=os.path.dirname(stats["markdown"]),
                          artifacts={"contract": stats["contract"],
                                     "markdown": stats["markdown"]},
                          warnings=warnings, t0=t0)
