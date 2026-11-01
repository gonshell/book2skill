# -*- coding: utf-8 -*-
"""标题四分类 + 结构树测试（S1-1d）。

全部用例喂字符串走真实管线（parse_page_marks → split_paragraphs → build_tree），
零 fixture 文件。形态全部取自必修一真实取证（structure.py 模块注释）。
"""
import unittest

from book2qa import source, structure


PAGE_CODES = ("page_marks_absent", "block_no_images", "page_offset_inconsistent",
              "page_offset_ambiguous", "page_offset_invalid", "image_outside_block")


def run_md(md):
    """合成 markdown → (rows, structure_issues)。页标记类 issue 默认滤除。"""
    if "原书物理页" not in md:
        md = "<!-- ===== 原书物理页 7-46 · 教材页码 None-39 ===== -->\n" + md
    marks, mk_issues = source.parse_page_marks(md)
    paras = source.split_paragraphs(md, marks, {})
    rows, para_meta, issues = structure.build_tree(paras)
    return rows, [i for i in mk_issues + issues if i["code"] not in PAGE_CODES]


def by_id(rows, rid):
    for r in rows:
        if r["id"] == rid:
            return r
    return None


class TestChapter(unittest.TestCase):
    def test_chapter_tight_name(self):
        rows, _ = run_md("## 第一章集合与常用逻辑用语\n\n正文\n")
        self.assertEqual(by_id(rows, "第一章")["title"], "集合与常用逻辑用语")

    def test_chapter_continuation_merge(self):
        rows, issues = run_md("## 第五章\n\n## 三角函数\n\n## 5.1 任意角\n\n正文\n")
        self.assertEqual(by_id(rows, "第五章")["title"], "三角函数")
        self.assertEqual([i["code"] for i in issues], [])

    def test_chapter_unnamed_no_continuation(self):
        rows, issues = run_md("## 第五章\n\n## 5.1 任意角\n\n正文\n")
        self.assertEqual(by_id(rows, "第五章")["title"], "(章名缺失)")
        self.assertTrue(any(i["code"] == "chapter_unnamed" for i in issues))

    def test_chapter_number_parsing(self):
        rows, _ = run_md("## 第三章函数的概念与性质\n\n正文\n")
        self.assertEqual(by_id(rows, "第三章")["chapter_num"], 3)


class TestSectionSubsection(unittest.TestCase):
    def test_section_with_space(self):
        rows, _ = run_md("## 1.1 集合的概念\n\n正文\n")
        self.assertEqual(by_id(rows, "1.1")["title"], "集合的概念")

    def test_section_missing_space(self):
        rows, _ = run_md("## 2.3二次函数与一元二次方程、不等式\n\n正文\n")
        self.assertEqual(by_id(rows, "2.3")["title"], "二次函数与一元二次方程、不等式")

    def test_subsection_missing_space(self):
        rows, _ = run_md("## 3.2.1单调性与最大（小）值\n\n正文\n")
        self.assertEqual(by_id(rows, "3.2.1")["title"], "单调性与最大（小）值")

    def test_pseudo_section_single_number_is_item(self):
        """衔接课 `## 3. 相似三角形的性质` 不得误判为节。"""
        rows, _ = run_md("## 1.4 充分条件\n\n## 3. 相似三角形的性质\n\n正文\n")
        self.assertIsNone(by_id(rows, "3"))
        sec = by_id(rows, "1.4")
        self.assertEqual(sec["items"][0]["kind"], "item")
        self.assertIn("相似三角形", sec["items"][0]["title"])

    def test_intra_item_recorded_not_boundary(self):
        rows, _ = run_md("## 5.4.2 正弦函数、余弦函数的性质\n\n## 1. 周期性\n\n正文A\n")
        sub = by_id(rows, "5.4.2")
        self.assertEqual(sub["items"][0]["title"], "1. 周期性")
        self.assertEqual(sub["n_paras"], 1)  # 正文A 仍归子节

    def test_section_not_confused_with_prompt(self):
        """`## 3.2 单调性` 是节不是提问块（清洗前缀不得吃掉节号）。"""
        rows, _ = run_md("## 3.2 单调性\n\n正文\n")
        self.assertIsNotNone(by_id(rows, "3.2"))

    def test_subsection_parent_link(self):
        rows, _ = run_md("## 3.2 函数的基本性质\n\n## 3.2.1 单调性\n\nA\n\n## 3.2.2 奇偶性\n\nB\n")
        self.assertEqual(by_id(rows, "3.2.1")["parent_id"], "3.2")
        self.assertEqual(by_id(rows, "3.2.2")["parent_id"], "3.2")

    def test_subsection_orphan_issue(self):
        rows, issues = run_md("## 第一章集合\n\n## 1.4.9 孤儿子节\n\n正文\n")
        self.assertTrue(any(i["code"] == "subsection_orphan" for i in issues))

    def test_section_two_level_is_section_not_subsection(self):
        """`## 9.9 X` 是节（两级编号），归错章才报 mismatch。"""
        rows, issues = run_md("## 第一章集合\n\n## 9.9 越章节\n\n正文\n")
        self.assertIsNotNone(by_id(rows, "9.9"))
        self.assertTrue(any(i["code"] == "chapter_section_mismatch" for i in issues))

    def test_chapter_section_mismatch_issue(self):
        rows, issues = run_md("## 第一章集合\n\n## 2.1 等式性质\n\n正文\n")
        self.assertTrue(any(i["code"] == "chapter_section_mismatch" for i in issues))


class TestPromptBlocks(unittest.TestCase):
    def test_prompt_plain(self):
        rows, _ = run_md("## 1.1 集合的概念\n\n## 思考\n\n问题？\n")
        self.assertEqual(by_id(rows, "1.1")["block_kinds"].get("思考"), 1)

    def test_prompt_ocr_prefix_digit(self):
        rows, _ = run_md("## 1.1 集合的概念\n\n## 3思考\n\n问题？\n")
        self.assertEqual(by_id(rows, "1.1")["block_kinds"].get("思考"), 1)

    def test_prompt_ocr_prefix_paren(self):
        rows, _ = run_md("## 1.1 集合的概念\n\n## 2) 阅读与思考\n\n文章\n")
        self.assertEqual(by_id(rows, "1.1")["block_kinds"].get("阅读与思考"), 1)

    def test_prompt_ocr_glued(self):
        rows, _ = run_md("## 1.1 集合的概念\n\n## 6归纳\n\n结论\n")
        self.assertEqual(by_id(rows, "1.1")["block_kinds"].get("归纳"), 1)

    def test_prompt_numbered(self):
        rows, _ = run_md("## 1.1 集合的概念\n\n## 探究1\n\n活动\n")
        self.assertEqual(by_id(rows, "1.1")["block_kinds"].get("探究"), 1)

    def test_block_kind_resets_at_section(self):
        rows, _ = run_md("## 1.1 集合\n\n## 思考\n\n问题\n\n## 1.2 基本关系\n\n定义\n")
        self.assertEqual(by_id(rows, "1.2")["block_kinds"].get("正文"), 1)
        self.assertIsNone(by_id(rows, "1.2")["block_kinds"].get("思考"))


class TestNoiseAndEndMatter(unittest.TestCase):
    def test_noise_symbol(self):
        rows, _ = run_md("## 1.1 集合\n\n## • •\n\n正文\n")
        sec = by_id(rows, "1.1")
        self.assertEqual(sec["items"][0]["kind"], "noise")
        self.assertEqual(sec["n_paras"], 1)  # 正文未丢

    def test_noise_latin(self):
        rows, _ = run_md("## 1.1 集合\n\n## da\n\n正文\n")
        self.assertEqual(by_id(rows, "1.1")["items"][0]["kind"], "noise")

    def test_ch_end_cn_numbered(self):
        rows, _ = run_md("## 1.1 集合\n\n## 一、本章知识结构\n\n图\n")
        self.assertEqual(by_id(rows, "1.1")["block_kinds"].get("章末栏目"), 1)

    def test_ch_end_review_problems(self):
        """复习参考题切出为章级附属行，不归最后一个节。"""
        rows, _ = run_md("## 第一章集合\n\n## 1.1 集合\n\n正文\n\n## 复习参考题1\n\n题\n")
        end = [r for r in rows if r["kind"] == "ch_end"]
        self.assertEqual([e["id"] for e in end], ["第一章-END"])
        self.assertEqual(end[0]["n_paras"], 1)  # 题段归章末行
        self.assertIsNone(by_id(rows, "1.1")["block_kinds"].get("章末栏目"))

    def test_meta_rows(self):
        rows, _ = run_md("## 第一章集合\n\n## 1.1 集合\n\n正文\n\n## 后记\n\n说明\n")
        meta = [r for r in rows if r["kind"] == "meta"]
        self.assertEqual([m["title"] for m in meta], ["后记"])

    def test_minor_heading_recorded(self):
        rows, _ = run_md("## 1.3 集合的基本运算\n\n## 补集\n\n定义\n")
        sec = by_id(rows, "1.3")
        self.assertEqual(sec["items"][0]["kind"], "minor")
        self.assertEqual(sec["items"][0]["title"], "补集")


class TestTreeShape(unittest.TestCase):
    def test_front_matter_bucket(self):
        rows, _ = run_md("前言内容\n\n## 第一章集合\n\n## 1.1 集合\n\n正文\n")
        front = [r for r in rows if r["kind"] == "front"]
        self.assertEqual(len(front), 1)
        self.assertEqual(front[0]["n_paras"], 1)

    def test_page_aggregates(self):
        # 图 92/131 跨满整块 47-86 → 偏移唯一（45），无歧义
        md = ("<!-- ===== 原书物理页 47-86 · 教材页码 40-79 ===== -->\n"
              "## 3.2 函数的基本性质\n\nA！[](images/page_92_image_1.jpg)\n\n"
              "B！[](images/page_131_image_2.jpg)\n")
        marks, _ = source.parse_page_marks(md)
        paras = source.split_paragraphs(md, marks, {47: 40, 86: 79})
        rows, _, _ = structure.build_tree(paras)
        sec = by_id(rows, "3.2")
        self.assertEqual(sec["phys"], [47, 86])
        self.assertEqual(sec["tb"], [40, 79])

    def test_no_content_drop(self):
        """所有段落必然落入某个行——无丢弃分支。"""
        md = ("## 第一章集合\n\n## 1.1 集合\n\nA\n\n## • •\n\nB\n\n## 思考\n\nC\n"
              "\n## 复习参考题1\n\nD\n\n## 后记\n\nE\n")
        marks, _ = source.parse_page_marks(md)
        paras = source.split_paragraphs(md, marks, {})
        rows, _, _ = structure.build_tree(paras)
        total = sum(r["n_paras"] for r in rows)
        self.assertEqual(total, 5)  # A B C D E 全在

    def test_line_ranges_monotonic(self):
        """章区间包含其节；同级（章与章、节与节）不重叠。"""
        md = ("## 第一章集合\n\n## 1.1 集合\n\nA\n\n## 1.2 关系\n\nB\n"
              "\n## 第二章不等式\n\n## 2.1 等式\n\nC\n")
        marks, _ = source.parse_page_marks(md)
        paras = source.split_paragraphs(md, marks, {})
        rows, _, _ = structure.build_tree(paras)
        chs = [(r["line_start"], r["line_end"]) for r in rows if r["kind"] == "chapter"]
        secs = [(r["line_start"], r["line_end"]) for r in rows if r["kind"] == "section"]
        for (s1, e1), (s2, e2) in zip(chs, chs[1:]):
            self.assertLess(e1, s2)
        for (s1, e1), (s2, e2) in zip(secs, secs[1:]):
            self.assertLess(e1, s2)
        for c in chs:
            for s in secs:
                if c[0] <= s[0] <= c[1]:
                    self.assertLessEqual(s[1], c[1])


if __name__ == "__main__":
    unittest.main()
