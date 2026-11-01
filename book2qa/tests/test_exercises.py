# -*- coding: utf-8 -*-
"""题目抽取测试（S1-2b）。形态取自必修一真实练习/习题/例题。"""
import unittest

from book2qa import source, structure
from book2qa.extract import exercises


def run_md(md):
    if "原书物理页" not in md:
        md = "<!-- ===== 原书物理页 47-86 · 教材页码 40-79 ===== -->\n" + md
    marks, _ = source.parse_page_marks(md)
    pmap = {47: 40, 48: 41, 49: 42, 50: 43, 51: 44}
    paras = source.split_paragraphs(md, marks, pmap)
    rows, para_meta, _ = structure.build_tree(paras)
    ex_rows, issues = exercises.extract(paras, para_meta)
    return ex_rows, issues, rows


class TestMainItems(unittest.TestCase):
    def test_main_numbered_items(self):
        md = ("## 3.2 函数的基本性质\n\n## 习题3.2\n\n"
              "1. 判断下列函数的奇偶性！[](images/page_92_image_1.jpg)\n\n"
              "2. 已知函数 $f(x)=x^{2}$，求其单调区间。\n")
        ex_rows, issues, _ = run_md(md)
        self.assertEqual([r["num"] for r in ex_rows], [1, 2])
        self.assertEqual(ex_rows[0]["block_kind"], "习题")
        self.assertEqual(ex_rows[0]["owner_id"], "3.2")
        self.assertEqual(ex_rows[1]["label"], "P40 习题2")

    def test_sub_parts_attach_to_main(self):
        md = ("## 1.2 集合间的基本关系\n\n## 练习\n\n"
              "1. 判断下列关系是否正确：\n\n"
              "(1) $A = \\{ x \\mid x$ 是等腰三角形}；\n\n"
              "(2) $B = \\{ 1, 2 \\}$。\n")
        ex_rows, _, _ = run_md(md)
        self.assertEqual(len(ex_rows), 1)
        self.assertEqual([pt["sub"] for pt in ex_rows[0]["parts"]], [1, 2])
        self.assertIn("$B = \\{ 1, 2 \\}$", ex_rows[0]["parts"][1]["quote"])

    def test_sub_without_main_stands_alone(self):
        md = "## 1.1 集合\n\n## 练习\n\n(1) 第一小题。\n\n(2) 第二小题。\n"
        ex_rows, _, _ = run_md(md)
        self.assertEqual(len(ex_rows), 2)
        self.assertEqual([r["sub"] for r in ex_rows], [1, 2])

    def test_continuation_cross_page(self):
        md = ("## 1.1 集合\n\n## 练习\n\n"
              "1. 已知集合 $A = \\{ 1, 2 \\}$，\n\n"
              "求 A 的所有子集。\n\n2. 下一题。\n")
        ex_rows, _, _ = run_md(md)
        self.assertEqual(len(ex_rows), 2)
        self.assertEqual(ex_rows[0]["cont"], ["求 A 的所有子集。"])
        self.assertEqual(ex_rows[0]["lines"][1], ex_rows[1]["lines"][0] - 2)

    def test_page_from_anchor(self):
        md = ("<!-- ===== 原书物理页 47-86 · 教材页码 40-79 ===== -->\n"
              "## 3.2 函数的基本性质\n\n## 习题3.2\n\n"
              "1. 题一！[](images/page_92_image_1.jpg)\n\n"
              "2. 题二！[](images/page_94_image_1.jpg)\n")
        ex_rows, issues, _ = run_md(md)
        self.assertEqual([r["page"] for r in ex_rows], [40, 42])
        self.assertEqual([i["code"] for i in issues], [])


class TestExamples(unittest.TestCase):
    def test_example_in_body(self):
        md = ("## 3.2.1 单调性\n\n正文定义。\n\n"
              "例1 根据定义，研究函数 $f(x)=kx+b$ 的单调性。\n\n"
              "解：按定义作差。\n\n后续正文。\n")
        ex_rows, _, _ = run_md(md)
        self.assertEqual(len(ex_rows), 1)
        self.assertEqual(ex_rows[0]["num"], 1)
        self.assertEqual(ex_rows[0]["block_kind"], "例")
        self.assertEqual(ex_rows[0]["cont"], ["解：按定义作差。"])

    def test_example_solution_chain_stops(self):
        md = ("## 3.2.1 单调性\n\n例1 题。\n\n解：略。\n\n"
              "新的一段定义内容。\n")
        ex_rows, _, _ = run_md(md)
        self.assertEqual(len(ex_rows), 1)
        self.assertEqual(ex_rows[0]["cont"], ["解：略。"])

    def test_two_examples(self):
        md = "## 3.2.1 单调性\n\n例1 甲题。\n\n解：略。\n\n例2 乙题。\n\n解：略。\n"
        ex_rows, _, _ = run_md(md)
        self.assertEqual([r["num"] for r in ex_rows], [1, 2])
        self.assertEqual([len(r["cont"]) for r in ex_rows], [1, 1])


class TestGuards(unittest.TestCase):
    def test_orphan_text_issue(self):
        md = "## 1.1 集合\n\n## 练习\n\n没有编号的一段话。\n"
        ex_rows, issues, _ = run_md(md)
        self.assertEqual(ex_rows, [])
        self.assertTrue(any(i["code"] == "exercise_orphan_text" for i in issues))

    def test_no_page_issue(self):
        md = ("<!-- ===== 原书物理页 247-270 · 教材页码 240-259 ===== -->\n"
              "## 5.7 应用\n\n## 练习\n\n1. 无图段落题。\n")
        marks, _ = source.parse_page_marks(md)
        paras = source.split_paragraphs(md, marks, {})  # page_map 空 → 无教材页
        rows, pm, _ = structure.build_tree(paras)
        ex_rows, issues = exercises.extract(paras, pm)
        self.assertTrue(any(i["code"] == "exercise_no_page" for i in issues))
        self.assertEqual(ex_rows[0]["label"].startswith("P?"), True)

    def test_exercise_chain_breaks_at_new_block(self):
        """练习 → 思考 → 练习：思考断链，练习2 重新计号。"""
        md = ("## 1.1 集合\n\n## 练习\n\n1. 题一。\n\n## 思考\n\n为什么？\n\n"
              "## 练习\n\n1. 题二。\n")
        ex_rows, _, rows = run_md(md)
        self.assertEqual(len(ex_rows), 2)
        self.assertEqual(ex_rows[1]["quote"], "1. 题二。")

    def test_block_kind_carries_owner(self):
        md = "## 3.2 函数的基本性质\n\n## 3.2.1 单调性\n\n## 练习\n\n1. 题。\n"
        ex_rows, _, _ = run_md(md)
        self.assertEqual(ex_rows[0]["owner_id"], "3.2.1")


if __name__ == "__main__":
    unittest.main()
