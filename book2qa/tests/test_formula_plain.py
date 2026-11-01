# -*- coding: utf-8 -*-
"""latex → plain 规则表测试（S1-2a）。样本取自必修一真实公式形态。"""
import unittest

from book2qa.extract.formulas import extract_math, latex_to_plain, validate_plain


class TestTable(unittest.TestCase):
    def test_frac(self):
        self.assertEqual(latex_to_plain(r"\frac{1}{2}"), "1/2")

    def test_frac_nested(self):
        self.assertEqual(latex_to_plain(r"\frac{\frac{1}{2}}{3}"), "1/2/3")

    def test_frac_empty_numerator(self):
        self.assertEqual(latex_to_plain(r"\frac{}{x}"), "/x")

    def test_sqrt(self):
        self.assertEqual(latex_to_plain(r"\sqrt{2}"), "根号2")

    def test_sqrt_nth(self):
        self.assertEqual(latex_to_plain(r"\sqrt[3]{x}"), "3次根号x")

    def test_sup_sub(self):
        self.assertEqual(latex_to_plain("x^{2}"), "x^2")
        self.assertEqual(latex_to_plain("x_{1}"), "x_1")
        self.assertEqual(latex_to_plain("x_{n+1}^{2}"), "x_n+1^2")

    def test_le_variants(self):
        self.assertEqual(latex_to_plain(r"\le"), "<=")
        self.assertEqual(latex_to_plain(r"\leq"), "<=")
        self.assertEqual(latex_to_plain(r"\leqslant"), "<=")
        self.assertEqual(latex_to_plain(r"\geqslant"), ">=")
        self.assertEqual(latex_to_plain(r"\ne"), "!=")

    def test_leq_not_eaten_by_le(self):
        self.assertEqual(latex_to_plain(r"x \leq 1"), "x <= 1")

    def test_set_ops(self):
        self.assertEqual(latex_to_plain(r"A \cup B"), "A 并 B")
        self.assertEqual(latex_to_plain(r"A \cap B"), "A 交 B")
        self.assertEqual(latex_to_plain(r"x \in A"), "x 属于 A")

    def test_subseteq_with_leading_ws(self):
        """transform §S4：`{ \\subseteq }` 命令前空白。"""
        self.assertEqual(latex_to_plain(r"A { \subseteq } B"), "A 包含于 B")

    def test_forall_exists(self):
        self.assertEqual(latex_to_plain(r"\forall x_{1}"), "任意 x_1")
        self.assertEqual(latex_to_plain(r"\exists x"), "存在 x")

    def test_greek(self):
        self.assertEqual(latex_to_plain(r"\alpha"), "alpha")
        self.assertEqual(latex_to_plain(r"\varphi"), "varphi")
        self.assertEqual(latex_to_plain(r"\omega"), "omega")

    def test_real_sin_model(self):
        self.assertEqual(latex_to_plain(r"y = A \sin(\omega x + \varphi)"),
                         "y = A sin(omega x + varphi)")

    def test_unknown_cmd_keeps_name(self):
        self.assertEqual(latex_to_plain(r"\unknowncmd x"), "unknowncmd x")

    def test_unbalanced_returns_none(self):
        self.assertIsNone(latex_to_plain(r"\frac{1}{2"))
        self.assertIsNone(latex_to_plain(r"x^{2"))


class TestExtract(unittest.TestCase):
    def test_inline_and_display(self):
        segs = extract_math(r"设 $f(x_{1}) < f(x_{2})$ 且 $$\frac{1}{2}$$ 结束")
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0][1], "f(x_1) < f(x_2)")
        self.assertEqual(segs[1][1], "1/2")

    def test_no_math(self):
        self.assertEqual(extract_math("纯中文没有公式"), [])

    def test_real_leqslant(self):
        segs = extract_math(r"当 $x \leqslant 0$ 时")
        self.assertEqual(segs[0][1], "x <= 0")


class TestValidatePlain(unittest.TestCase):
    def test_rows_get_plain(self):
        rows = [{"label": "P77 例1", "quote": "研究 $f(x)=kx+b(k\\neq 0)$ 的单调性。"}]
        issues = validate_plain(rows)
        self.assertEqual(issues, [])
        self.assertIn("!=", rows[0]["quote_plain"])   # \neq → !=
        self.assertNotIn("$", rows[0]["quote_plain"])
        self.assertIn("的单调性", rows[0]["quote_plain"])  # 正文保留

    def test_failed_reported(self):
        rows = [{"label": "坏题", "quote": r"$\frac{1}{2$ 破损"}]
        issues = validate_plain(rows)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["code"], "formulas_plain_failed")


if __name__ == "__main__":
    unittest.main()
