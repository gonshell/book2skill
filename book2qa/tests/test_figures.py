# -*- coding: utf-8 -*-
"""图号映射测试（S1-2c）。"""
import os
import tempfile
import unittest

from book2qa import source
from book2qa.extract import figures


def setup(md, image_pages):
    tmp = tempfile.mkdtemp()
    img_dir = os.path.join(tmp, "images")
    os.makedirs(img_dir)
    for pdf in image_pages:
        open(os.path.join(img_dir, "page_%d_image_0.jpg" % pdf), "w").close()
    marks, _ = source.parse_page_marks(md)
    pmap = {47: 40, 48: 41, 49: 42}
    paras = source.split_paragraphs(md, marks, pmap)
    rows, issues = figures.map_figures(paras, marks, img_dir)
    return rows, issues


class TestFigures(unittest.TestCase):
    MD = ("<!-- ===== 原书物理页 47-86 · 教材页码 40-79 ===== -->\n"
          "## 3.2 函数的基本性质\n\n"
          "如图 3.2-1 所示！[](images/page_92_image_1.jpg)\n\n"
          "图3.2-1\n\n"
          "再看图3.2-2 的情形！[](images/page_94_image_9.jpg)\n\n"
          "正文一段。\n")

    def test_caption_anchor(self):
        rows, _ = setup(self.MD, [92, 94])
        self.assertEqual(rows[0]["fig"], "图3.2-1")
        self.assertEqual(rows[0]["file"], "images/page_92_image_0.jpg")
        self.assertTrue(rows[0]["by_caption"])

    def test_neighbor_page_fallback(self):
        """图3.2-2 无图注，引用行 ±1 页内找文件。"""
        rows, _ = setup(self.MD, [92, 94])
        by = {r["fig"]: r for r in rows}
        self.assertIn("图3.2-2", by)
        self.assertEqual(by["图3.2-2"]["file"], "images/page_94_image_0.jpg")

    def test_no_file_issue(self):
        rows, issues = setup(self.MD, [92])  # page_94 缺
        by = {r["fig"]: r for r in rows}
        self.assertIn("图3.2-1", by)
        self.assertTrue(any(i["code"] == "figure_no_file" and i["fig"] == "图3.2-2"
                            for i in issues))

    def test_file_no_ref_summary(self):
        _, issues = setup(self.MD, [92, 94, 96])
        self.assertTrue(any(i["code"] == "file_no_ref" for i in issues))

    def test_no_page_issue(self):
        md = ("<!-- ===== 原书物理页 247-270 · 教材页码 240-259 ===== -->\n"
              "## 5.7 应用\n\n如图5.7-1 所示。\n")
        marks, _ = source.parse_page_marks(md)
        paras = source.split_paragraphs(md, marks, {})
        rows, issues = figures.map_figures(paras, marks, None)
        self.assertEqual(rows, [])
        self.assertTrue(any(i["code"] == "figure_no_page" for i in issues))


if __name__ == "__main__":
    unittest.main()
