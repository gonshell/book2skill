# -*- coding: utf-8 -*-
"""graph 段测试（S1-4c）：prereq 规则 + 质量闸各失败路径。"""
import unittest

from book2qa import graph as G


def cand(cid, **kw):
    c = {"id": cid, "title": "测试知识点" + cid[-2:], "type": "concept",
         "book": "必修第一册", "chapter": "第一章集合", "section": "1.1 集合",
         "pages": [6, 7], "summary": "一句话。", "status": "unverified",
         "built_at": "2026-11-01T00:00:00", "built_by": "auto",
         "anchors": [{"quote": "一般地，某些对象组成的整体叫集合。",
                      "page": 6, "role": "definition", "estimated": False}],
         "exercises": [], "unit": "1.1"}
    c.update(kw)
    return c


MD_OK = "前言。一般地，某些对象组成的整体叫集合。正文继续。"
MD_BAD = "前言。别的内容，锚点引用不到。"


class TestPrereq(unittest.TestCase):
    def test_chain_within_unit(self):
        cands = [cand("M1-C1-S1-K01"), cand("M1-C1-S1-K02"),
                 cand("M1-C1-S1-K03")]
        p = G.generate_prereq(cands)
        self.assertEqual(p["M1-C1-S1-K02"], ["M1-C1-S1-K01"])
        self.assertEqual(p["M1-C1-S1-K03"], ["M1-C1-S1-K02"])
        self.assertNotIn("M1-C1-S1-K01", p)  # 首节点无前置（缺省不写空数组）

    def test_cross_chapter_link(self):
        cands = [cand("M1-C1-S1-K01", chapter="第一章", unit="1.1"),
                 cand("M1-C2-S1-K01", chapter="第二章", unit="2.1")]
        p = G.generate_prereq(cands)
        self.assertEqual(p["M1-C2-S1-K01"], ["M1-C1-S1-K01"])

    def test_first_node_of_first_chapter_no_prereq(self):
        p = G.generate_prereq([cand("M1-C1-S1-K01")])
        self.assertEqual(p, {})

    def test_unit_order_independent(self):
        cands = [cand("M1-C1-S1-K02", unit="1.1"),
                 cand("M1-C1-S1-K01", unit="1.1")]
        p = G.generate_prereq(cands)
        self.assertEqual(p["M1-C1-S1-K02"], ["M1-C1-S1-K01"])


class TestGate(unittest.TestCase):
    def base(self, cands, md=MD_OK):
        return G.quality_gate(cands, md, [], [])

    def test_pass_clean(self):
        ok, issues = self.base([cand("M1-C1-S1-K01")])
        self.assertTrue(ok)
        self.assertEqual(issues, [])

    def test_fail_duplicate_id(self):
        ok, issues = self.base([cand("M1-C1-S1-K01"), cand("M1-C1-S1-K01")])
        self.assertFalse(ok)
        self.assertTrue(any(i["code"] == "graph_duplicate_id" for i in issues))

    def test_fail_missing_field(self):
        c = cand("M1-C1-S1-K01")
        del c["summary"]
        ok, issues = self.base([c])
        self.assertFalse(ok)
        self.assertTrue(any(i["code"] == "graph_missing_field" for i in issues))

    def test_fail_bad_type(self):
        ok, _ = self.base([cand("M1-C1-S1-K01", type="知识点")])
        self.assertFalse(ok)

    def test_issue_anchor_not_found(self):
        ok, issues = self.base([cand("M1-C1-S1-K01")], md=MD_BAD)
        self.assertTrue(ok)  # 内容级不阻断
        self.assertTrue(any(i["code"] == "anchor_not_found" for i in issues))

    def test_broken_formula_forces_unverified(self):
        c = cand("M1-C1-S1-K01")
        c["exercises"] = [{"label": "", "page": 6,
                           "quote": r"$A = \{ x \mid x$ 是长方形}"}]
        ok, issues = self.base([c])
        self.assertTrue(ok)
        self.assertTrue(any(i["code"] == "broken_formula_in_quote" for i in issues))
        self.assertEqual(c["status"], "unverified")

    def test_no_pages_issue_not_block(self):
        c = cand("M1-C1-S1-K01", pages=None)
        ok, issues = self.base([c])
        self.assertTrue(ok)
        self.assertTrue(any(i["code"] == "graph_no_pages" for i in issues))

    def test_unknown_exercise_label(self):
        c = cand("M1-C1-S1-K01")
        c["exercises"] = [{"label": "P999 习题9", "page": 99, "quote": "x" * 10}]
        ex = [{"label": "P40 习题1", "page": 40, "quote": "y" * 10}]
        ok, issues = G.quality_gate([c], MD_OK, ex, [])
        self.assertTrue(ok)
        self.assertTrue(any(i["code"] == "exercise_label_unknown" for i in issues))

    def test_unknown_figure(self):
        c = cand("M1-C1-S1-K01", figures=["图9.9-9"])
        ok, issues = G.quality_gate([c], MD_OK, [],
                                    [{"fig": "图1.2-1", "file": "images/a.jpg"}])
        self.assertTrue(ok)
        self.assertTrue(any(i["code"] == "figure_unknown" for i in issues))


class TestBuildGraph(unittest.TestCase):
    def test_prereq_applied_and_missing_omitted(self):
        cands = [cand("M1-C1-S1-K01"), cand("M1-C1-S1-K02")]
        p = G.generate_prereq(cands)
        rows = G.build_graph(cands, p, [])
        self.assertEqual(rows[0].get("prereq"), None)  # 无前置则缺省
        self.assertEqual(rows[1]["prereq"], ["M1-C1-S1-K01"])


if __name__ == "__main__":
    unittest.main()
