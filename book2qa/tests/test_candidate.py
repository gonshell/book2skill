# -*- coding: utf-8 -*-
"""候选切分测试（S1-3c）。数据形态对齐真实书：章→节→子节、短段落多行。"""
import unittest

from book2qa import source, structure
from book2qa.candidate import build_candidates, infer_type
from book2qa.extract import exercises


def _para(word, n):
    """n 个短段（每段一行），模拟真实书的段落密度。"""
    return ("\n\n".join("%s内容第%d句，一般地成立。" % (word, i) for i in range(n)))


def pipeline(md):
    if "原书物理页" not in md:
        md = "<!-- ===== 原书物理页 47-86 · 教材页码 40-79 ===== -->\n" + md
    marks, _ = source.parse_page_marks(md)
    pmap = {47: 40, 48: 41, 49: 42, 50: 43, 51: 44, 52: 45,
            53: 46, 54: 47, 55: 48}
    paras = source.split_paragraphs(md, marks, pmap)
    rows, meta, _ = structure.build_tree(paras)
    ex_rows, _ = exercises.extract(paras, meta)
    return build_candidates(rows, meta, paras, ex_rows)


BIG = ("## 第五章三角函数\n\n"
       "## 5.4 三角函数的图象与性质\n\n"
       "## 5.4.2 正弦函数、余弦函数的性质\n\n"
       + _para("性质引言", 40) + "\n\n"
       + "## 1. 周期性\n\n" + _para("周期", 60)
       + "\n\n## 2. 奇偶性\n\n" + _para("奇偶", 60)
       + "\n\n## 练习\n\n1. 题一！[](images/page_92_image_1.jpg)\n\n2. 题二。\n")

SMALL_PAIR = ("## 第四章指数函数与对数函数\n\n"
              "## 4.5 函数的应用（二）\n\n"
              "## 4.5.1 函数的零点\n\n零点内容一般地成立。\n\n"
              "## 4.5.2 二分法\n\n二分内容一般地成立。\n")


class TestSplit(unittest.TestCase):
    def test_big_unit_splits_by_items(self):
        cands, _, _ = pipeline(BIG)
        titles = [c["title"] for c in cands]
        self.assertIn("周期性", titles)
        self.assertIn("奇偶性", titles)

    def test_split_ids_sequential_and_unique(self):
        cands, _, _ = pipeline(BIG)
        ids = [c["id"] for c in cands]
        self.assertEqual(len(ids), len(set(ids)))
        for c in cands:
            self.assertTrue(c["id"].startswith("M1-C5-S4"), c["id"])


class TestMerge(unittest.TestCase):
    def test_small_unit_merges_to_next_sibling(self):
        cands, issues, quota = pipeline(SMALL_PAIR)
        self.assertEqual(quota["merged_units"].get("4.5.1"), "4.5.2")
        self.assertTrue(any("二分法" in c["title"] for c in cands))
        self.assertFalse(any(c["unit"] == "4.5.1" for c in cands))


class TestShellAndId(unittest.TestCase):
    SHELL = ("## 第三章函数的概念与性质\n\n"
             "## 3.2 函数的基本性质\n\n引言一句。\n\n"
             "## 3.2.1 单调性\n\n" + _para("单调", 30) + "\n")

    def test_shell_section_skipped(self):
        cands, issues, _ = pipeline(self.SHELL)
        self.assertFalse(any(c["unit"] == "3.2" for c in cands))
        self.assertTrue(any(i["code"] == "granularity_shell_skipped"
                            for i in issues))
        self.assertTrue(any(c["unit"] == "3.2.1" for c in cands))

    def test_subsection_letter_id(self):
        cands, _, _ = pipeline(self.SHELL)
        self.assertEqual(cands[0]["id"], "M1-C3-S2A-K01")

    def test_section_without_sub_keeps_plain_id(self):
        md = ("## 第三章函数的概念与性质\n\n"
              "## 3.3 幂函数\n\n" + _para("幂函数", 30) + "\n")
        cands, _, _ = pipeline(md)
        self.assertEqual(cands[0]["id"], "M1-C3-S3-K01")


class TestAnchorsAndExercises(unittest.TestCase):
    def test_anchor_quote_finds_source(self):
        cands, _, _ = pipeline(BIG)
        c = next(c for c in cands if c["title"] == "周期性")
        self.assertTrue(c["anchors"])
        self.assertTrue(all(a["quote"] and a["page"] for a in c["anchors"]))

    def test_exercises_attached(self):
        cands, _, _ = pipeline(BIG)
        c = next(c for c in cands if c["unit"] == "5.4.2")
        self.assertGreaterEqual(len(c["exercises"]), 1)
        self.assertIn("label", c["exercises"][0])


class TestTypes(unittest.TestCase):
    def test_infer_type_priority(self):
        self.assertEqual(infer_type("函数模型的应用"), "application")
        self.assertEqual(infer_type("用定义判定单调性"), "method")
        self.assertEqual(infer_type("函数的单调性"), "theorem")
        self.assertEqual(infer_type("函数的概念"), "concept")

    def test_quota_reported(self):
        _, _, quota = pipeline(BIG)
        self.assertIn("total", quota)
        self.assertIn("type_pct", quota)


if __name__ == "__main__":
    unittest.main()
