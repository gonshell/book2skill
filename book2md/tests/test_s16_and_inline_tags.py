# -*- coding: utf-8 -*-
"""S16（结构性损坏公式降级）与 md2html 行内标签白名单的单元测试。

背景（2026-10-26 化学书实战）：
- 抽取层对"双线桥""嵌套圈号"产出不可渲染的垃圾公式，KaTeX 必报错 →
  新增 S16 整条降级 + 报告文件，可安全判定的拆散形态就地修复；
- 化学教材正文含原生 <sup>/<sub>/<u> 标签（数学书没有），此前被整体转义
  打成可见文本 → prose_inline 加白名单只放行这三种无属性标签。

这些用例锁死两件事：**不臆造内容**（降级而非猜测）、**不误伤数学**（$a<b$ 仍转义）。
"""
import os
import re
import sys
import tempfile
import unittest

from book2md.engine import render, rules


class TestS16BrokenFormula(unittest.TestCase):
    def test_nested_textcircled_block_degraded(self):
        md = "前文\n\n$$\n\\textcircled { \\textcircled { \\textcircled { \\textc } } }\n$$\n\n后文"
        out, (n_broken, _) = rules.s16(md)
        self.assertEqual(n_broken, 1)
        self.assertIn(rules.FORMULA_PLACEHOLDER_BLOCK, out)
        self.assertNotIn("textcircled", out)

    def test_truncated_command_inline_degraded(self):
        md = "氢氧燃料电池 $\u00b7 \\frac { \\textc } { \\textcircled { \\textc } }$ 二者"
        out, (n_broken, _) = rules.s16(md)
        self.assertEqual(n_broken, 1)
        self.assertIn(rules.FORMULA_PLACEHOLDER_INLINE, out)

    def test_nested_empty_array_with_spaces(self):
        """首版正则漏了带空格的 { l } 写法，实测残留 2 处错误。"""
        body = "\\begin{array} { l } " * 4
        md = "$$\n\\stackrel{ %s } { x }\n$$" % body
        out, (n_broken, _) = rules.s16(md)
        self.assertEqual(n_broken, 1)
        self.assertIn(rules.FORMULA_PLACEHOLDER_BLOCK, out)

    def test_report_written_with_original_text(self):
        md = "$$\n\\textcircled { \\textcircled { x } }\n$$"
        with tempfile.TemporaryDirectory() as d:
            rp = os.path.join(d, "broken_formulas.tsv")
            rules.s16(md, book="测试册", report_path=rp)
            self.assertTrue(os.path.isfile(rp))
            with open(rp, encoding="utf-8") as fh:
                txt = fh.read()
        self.assertIn("测试册", txt)
        self.assertIn("textcircled", txt)   # 原串留档，供人工按 PDF 补录

    def test_idempotent(self):
        md = "$$\n\\textcircled { \\textcircled { x } }\n$$\n\n正文 $a^2$"
        once, _ = rules.s16(md)
        twice, (n2, _) = rules.s16(once)
        self.assertEqual(once, twice)
        self.assertEqual(n2, 0)

    def test_clean_formula_untouched(self):
        md = "$$\n\\frac{a}{b} + \\sqrt{x}\n$$\n\n行内 $x^{2}+1$ 与 $\\begin{array}{cc}1&2\\end{array}$"
        out, (n_broken, n_fixed) = rules.s16(md)
        self.assertEqual((n_broken, n_fixed), (0, 0))
        self.assertEqual(out, md)


class TestS16SafeRepair(unittest.TestCase):
    def test_decimal_split_by_semicolon(self):
        """OCR 把小数点后数字拆开：1.414\\;3 → 1.4143（数学书历史遗留 6 处同形态）。"""
        md = "幂 $5^{1.414\\;3}$ 与 $\\left[1.375-1.437\\;5\\right]=0.062\\;5$"
        out, (n_broken, n_fixed) = rules.s16(md)
        self.assertEqual(n_broken, 0)
        self.assertEqual(n_fixed, 3)
        self.assertIn("1.4143", out)
        self.assertIn("1.4375", out)
        self.assertIn("0.0625", out)

    def test_bare_superscript_after_semicolon(self):
        """度数被拆散：1 \\; 5 3 8 \\; ^ { \\circ } C → 1538^{\\circ}C。
        不能补 \\, 当基底（间距命令不构成基底，KaTeX 仍报错）。"""
        md = r"温度 $1 \; 5 3 8 \; ^ { \circ } \mathrm { C }$"
        out, (_, n_fixed) = rules.s16(md)
        self.assertGreaterEqual(n_fixed, 1)
        self.assertNotIn(r"\;^", out)

    def test_legit_spacing_not_destroyed(self):
        """公式内的正常间距（非数字间、非上标前）必须保留。"""
        md = r"$$\n\{ x \mid x = 2k+1, \; k \in \mathbf{Z} \}\n$$"
        out, (_, n_fixed) = rules.s16(md)
        self.assertEqual(n_fixed, 0)
        self.assertEqual(out, md)


class TestInlineTagWhitelist(unittest.TestCase):
    def test_sup_sub_u_preserved(self):
        md = "金属性<sup>②</sup>增强，Br<sub>2</sub>为液体，<u>重点</u>在此。"
        html = render.inline_html(md, {}, "测试册")
        self.assertIn("<sup>②</sup>", html)
        self.assertIn("<sub>2</sub>", html)
        self.assertIn("<u>重点</u>", html)
        self.assertNotIn("&lt;sup", html)

    def test_math_comparison_still_escaped(self):
        """数学里的 < > 不是标签：$a<b$ 之外的正文字符仍须转义。"""
        md = "若 x<y 且 y>z，则 $a<b$。"
        html = render.inline_html(md, {}, "测试册")
        self.assertIn("&lt;", html)
        self.assertIn("&gt;", html)

    def test_no_other_tags_passthrough(self):
        """白名单以外的标签（含带属性的 sup）一律转义，避免注入。"""
        md = 'a<script>x</script>b<sup class="x">2</sup>c'
        html = render.inline_html(md, {}, "测试册")
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;sup class=", html)

    def test_tags_inside_table_cells(self):
        """表头单位形态：密度（g·cm<sup>3</sup>）——表格走同一条转义路径。"""
        rows = [["元素", "密度（g·cm<sup>3</sup>）"], ["Li", "0.534"]]
        html = render.table_html(rows, {}, "测试册")
        self.assertIn("<sup>3</sup>", html)
        self.assertNotIn("&lt;sup", html)


if __name__ == "__main__":
    unittest.main()
