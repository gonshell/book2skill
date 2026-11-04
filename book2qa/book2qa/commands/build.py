# -*- coding: utf-8 -*-
"""b2q build — 四段编排（design.md §5.5）。

structure: 页锚定 + 标题四分类 → data/structure.jsonl
extract:   题目 + 公式双轨 + 图号 → data/exercises.jsonl / figures.json
candidates / graph: S1-3 / S1-4 实现（本阶段 EXIT_USAGE）。
"""
import os
import sys
import time

from book2qa import paths
from book2qa.envelope import emit
from book2qa.exit_codes import (EXIT_OK, EXIT_MISSING, EXIT_USAGE,
                                EXIT_GATE_FAIL)

_STAGES = ("structure", "extract", "candidates", "graph")


def execute(args, t0):
    book = args.book
    workspace = paths.resolve_workspace(args)
    source_root = paths.resolve_source_root(args)

    if args.stage not in _STAGES:  # argparse choices 已挡，防御性保留
        return emit("build", EXIT_USAGE, workspace=workspace, book=book,
                    error="未知 stage：%s" % args.stage, t0=t0)
    if not source_root or not os.path.isdir(paths.book_dir(source_root, book)):
        return emit("build", EXIT_MISSING, workspace=workspace, book=book,
                    error="book2md 产物根未配置或目录不存在：source_root=%r"
                          % (source_root,), t0=t0)
    files = paths.book_files(source_root, book)
    # page_map 可选（RV-C1：上游合法地不产；缺失降级报 issue，不整册拒收）
    missing = [k for k, v in files.items()
               if k not in ("images_dir", "page_map") and not os.path.isfile(v)]
    if missing:
        return emit("build", EXIT_MISSING, workspace=workspace, book=book,
                    error="缺少 book2md 产物：%s（%s）" % (missing, files["markdown"]),
                    t0=t0)

    if args.stage == "structure":
        return _stage_structure(args, workspace, files, t0)
    if args.stage == "candidates":
        return _stage_candidates(args, workspace, files, t0)
    if args.stage == "graph":
        return _stage_graph(args, workspace, files, t0)
    return _stage_extract(args, workspace, files, t0)


def _stage_graph(args, workspace, files, t0):
    import datetime
    from book2qa import graph as graph_mod, report as report_mod, source
    data_dir = paths.data_dir(workspace)
    cands = source._load_jsonl(os.path.join(data_dir, "candidates.jsonl"))
    ex_rows = source._load_jsonl(os.path.join(data_dir, "exercises.jsonl"))
    fig_rows = source._load_jsonl(os.path.join(data_dir, "figures.jsonl"))
    if not cands or not ex_rows:
        return emit("build", EXIT_MISSING, workspace=workspace, book=args.book,
                    error="缺少前序产物——请先跑 structure/extract/candidates",
                    t0=t0)
    markdown_text = source.read_markdown(files["markdown"])

    prereq = graph_mod.generate_prereq(cands)
    gate_pass, issues = graph_mod.quality_gate(cands, markdown_text,
                                               ex_rows, fig_rows)
    if not gate_pass:
        report_path = report_mod.write_report(workspace, issues,
                                              {"册": args.book, "质量闸": "未通过"})
        return emit("build", EXIT_GATE_FAIL, workspace=workspace, book=args.book,
                    out_dir=data_dir,
                    artifacts={"build_report": report_path},
                    issues=issues, t0=t0,
                    error="质量闸未通过，graph.jsonl 不落盘")
    rows = graph_mod.build_graph(cands, prereq, issues)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    for r in rows:
        if r.get("built_by") == "auto" and r.get("status") == "unverified":
            pass  # 初稿保持 auto/unverified；人工改过的是 auto+review
        r.setdefault("built_at", now)
    out = os.path.join(data_dir, "graph.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(graph_mod.to_json_line(r) + "\n")
    stats = {"册": args.book, "节点数": len(rows),
             "prereq 边数": sum(len(r.get("prereq", [])) for r in rows),
             "unverified": sum(1 for r in rows if r["status"] == "unverified")}
    report_path = report_mod.write_report(workspace, issues, stats)
    return emit("build", EXIT_OK, workspace=workspace, book=args.book,
                out_dir=data_dir,
                artifacts={"graph": out, "build_report": report_path},
                issues=issues, t0=t0, extra={"nodes": len(rows), "stats": stats})


def _stage_candidates(args, workspace, files, t0):
    import datetime
    from book2qa import candidate, report as report_mod, source, structure
    rows = source.load_structure(workspace, args.book)
    para_meta = source.load_para_meta(workspace, args.book)
    ex_rows = source._load_jsonl(
        os.path.join(paths.data_dir(workspace), "exercises.jsonl"))
    if not rows or not para_meta or not ex_rows:
        return emit("build", EXIT_MISSING, workspace=workspace, book=args.book,
                    error="缺少前序产物——请先跑 --stage=structure 与 --stage=extract",
                    t0=t0)
    text = source.read_markdown(files["markdown"])
    page_marks, _ = source.parse_page_marks(text)
    page_map = source.parse_page_map(files["page_map"])
    paragraphs = source.split_paragraphs(text, page_marks, page_map)

    cands, issues, quota = candidate.build_candidates(rows, para_meta,
                                                      paragraphs, ex_rows)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    for c in cands:
        c["built_at"] = now
    out = os.path.join(paths.ensure_data_dir(workspace), "candidates.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for c in cands:
            f.write(source.to_json_line(c) + "\n")
    stats = {"册": args.book, "候选节点数": len(cands),
             "类型分布": quota.get("type_pct", {}),
             "合并单元": len(quota.get("merged_units", {}))}
    report_path = report_mod.write_report(workspace, issues, stats)
    return emit("build", EXIT_OK, workspace=workspace, book=args.book,
                out_dir=paths.data_dir(workspace),
                artifacts={"candidates": out, "build_report": report_path},
                issues=issues, t0=t0, extra={"candidates": len(cands),
                                             "quota": quota})


def _stage_structure(args, workspace, files, t0):
    from book2qa import source, structure
    text = source.read_markdown(files["markdown"])
    page_marks, pm_issues = source.parse_page_marks(text)
    page_map = source.parse_page_map(files["page_map"])
    if not os.path.isfile(files["page_map"]):
        pm_issues = pm_issues + [{"code": "pages_missing",
                                  "detail": "page_map.md 缺失（上游合法可选），"
                                            "教材页码降级为 None，节点将强制 unverified"}]
    elif not page_map:
        pm_issues = pm_issues + [{"code": "page_map_empty",
                                  "detail": "page_map.md 无有效映射行：%s"
                                            % files["page_map"]}]
    paragraphs = source.split_paragraphs(text, page_marks, page_map)
    rows, para_meta, issues = structure.build_tree(paragraphs)
    out = os.path.join(paths.ensure_data_dir(workspace), "structure.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(source.to_json_line(r) + "\n")
    meta_out = os.path.join(paths.data_dir(workspace), "para_meta.jsonl")
    with open(meta_out, "w", encoding="utf-8") as f:
        for m in para_meta:
            f.write(source.to_json_line(m) + "\n")
    return emit("build", EXIT_OK, workspace=workspace, book=args.book,
                out_dir=paths.data_dir(workspace),
                artifacts={"structure": out, "para_meta": meta_out},
                issues=pm_issues + issues, t0=t0,
                extra={"sections": len(rows), "paragraphs": len(paragraphs)})


def _stage_extract(args, workspace, files, t0):
    from book2qa import source
    from book2qa.extract import exercises, figures, formulas
    para_meta = source.load_para_meta(workspace, args.book)
    if not para_meta:
        return emit("build", EXIT_MISSING, workspace=workspace, book=args.book,
                    error="缺少 para_meta.jsonl——请先跑 --stage=structure", t0=t0)
    text = source.read_markdown(files["markdown"])
    page_marks, pm_issues = source.parse_page_marks(text)
    page_map = source.parse_page_map(files["page_map"])
    paragraphs = source.split_paragraphs(text, page_marks, page_map)
    out_dir = paths.ensure_data_dir(workspace)

    ex_rows, ex_issues = exercises.extract(paragraphs, para_meta)
    fig_rows, fig_issues = figures.map_figures(paragraphs, page_marks,
                                               files["images_dir"])
    fm_issues = formulas.validate_plain(ex_rows)

    with open(os.path.join(out_dir, "exercises.jsonl"), "w", encoding="utf-8") as f:
        for r in ex_rows:
            f.write(exercises.to_json_line(r) + "\n")
    # figures.jsonl（RV-C5：扩展名与实际 JSONL 格式一致，json.load 不再误用）
    fig_path = os.path.join(out_dir, "figures.jsonl")
    with open(fig_path, "w", encoding="utf-8") as f:
        for r in fig_rows:
            f.write(figures.to_json_line(r) + "\n")

    issues = pm_issues + ex_issues + fig_issues + fm_issues
    from book2qa import report as report_mod
    stats = {"册": args.book, "题目总数": len(ex_rows), "图号映射": len(fig_rows),
             "段落总数": len(paragraphs)}
    report_path = report_mod.write_report(workspace, issues, stats)
    return emit("build", EXIT_OK, workspace=workspace, book=args.book,
                out_dir=out_dir,
                artifacts={"exercises": os.path.join(out_dir, "exercises.jsonl"),
                           "figures": fig_path,
                           "build_report": report_path},
                issues=issues, t0=t0,
                extra={"exercises": len(ex_rows), "figures": len(fig_rows)})


if __name__ == "__main__":
    sys.exit(0)
