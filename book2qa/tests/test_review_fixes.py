# -*- coding: utf-8 -*-
"""评审 BATCH-1 回归（book2qa 侧）：RV-C1 / RV-C2 / RV-C5。

台账要求：修前留失败证据、修后同命令复验、每条一条回归。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from book2qa.source import PAGE_MARK_RE, parse_page_marks

PY = sys.executable


def _make_source_root(tmp, with_page_map=True, page_mark=None):
    book = "测试册"
    d = os.path.join(tmp, book)
    os.makedirs(d)
    mark = page_mark or "<!-- ===== 原书物理页 7-46 · 教材页码 None-39 ===== -->"
    with open(os.path.join(d, "markdown.md"), "w", encoding="utf-8") as f:
        f.write(mark + "\n\n## 1.1 集合\n\n正文一段。\n")
    if with_page_map:
        with open(os.path.join(d, "page_map.md"), "w", encoding="utf-8") as f:
            f.write("| 物理页 | 教材页 |\n| --- | --- |\n| 7 | 1 |\n")
    return tmp, book


def _run_cli(args):
    r = subprocess.run([PY, "-m", "book2qa.cli"] + args, capture_output=True,
                       text=True, encoding="utf-8",
                       cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return json.loads(r.stdout)


class TestRvC1(unittest.TestCase):
    """无 page_map.md 的产物根：不得整册拒收，须降级报 pages_missing。"""

    def test_missing_page_map_degrades(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, book = _make_source_root(tmp, with_page_map=False)
            ws = os.path.join(tmp, "ws")
            e = _run_cli(["build", "--book", book, "--source-root", root,
                          "--workspace", ws, "--stage", "structure"])
            self.assertEqual(e["exit_code"], 0, e)
            codes = [i["code"] for i in e["issues"]]
            self.assertIn("pages_missing", codes)


class TestRvC2(unittest.TestCase):
    """「教材页码」段可选；识别不了的页界标记必须留痕不静默。"""

    def test_mark_without_textbook_section_matches(self):
        m = PAGE_MARK_RE.search("<!-- ===== 原书物理页 47-86 ===== -->")
        self.assertIsNotNone(m)
        marks, _ = parse_page_marks(
            "<!-- ===== 原书物理页 47-86 ===== -->\n正文")
        self.assertEqual(marks[0].phys_start, 47)
        self.assertIsNone(marks[0].tb_start)

    def test_unparsed_mark_reports_issue(self):
        _, issues = parse_page_marks(
            "<!-- ===== 原书物理页 7-46 · 教材页码？？ ===== -->\n正文")
        self.assertTrue(any(i["code"] == "page_mark_unparsed" for i in issues))


class TestRvC5(unittest.TestCase):
    """figures.jsonl：扩展名与 JSONL 格式一致。"""

    def test_extract_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, book = _make_source_root(tmp)
            ws = os.path.join(tmp, "ws")
            _run_cli(["build", "--book", book, "--source-root", root,
                      "--workspace", ws, "--stage", "structure"])
            e = _run_cli(["build", "--book", book, "--source-root", root,
                          "--workspace", ws, "--stage", "extract"])
            self.assertEqual(e["exit_code"], 0, e)
            fig = e["artifacts"]["figures"]
            self.assertTrue(fig.endswith("figures.jsonl"), fig)
            with open(fig, encoding="utf-8") as f:
                for ln in f:  # 每行独立合法 JSON（JSONL 语义）
                    json.loads(ln)


if __name__ == "__main__":
    unittest.main()
