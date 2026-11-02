# -*- coding: utf-8 -*-
"""S2 检索层回归：意图规则 / 契约字段 / 兜底三级 / 融合纯函数。"""
import json
import os
import subprocess
import sys
import unittest

QA_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

from book2qa import retrieval


class TestIntent(unittest.TestCase):
    def test_rules(self):
        cases = [
            ("单调性为什么一定要说任意两个数", "concept_why"),
            ("帮我看看这题我算的 x=2 对不对", "check_work"),
            ("求单调区间有几种方法", "method_list"),
            ("函数一点都听不懂", "too_broad"),
            ("今天该复习什么", "schedule"),
            ("那为什么这步要取倒数", "follow_up"),
            ("增啊减啊的那个性质叫什么", "stuck"),
        ]
        for q, want in cases:
            self.assertEqual(retrieval.classify_intent(q), want, q)


class TestFusion(unittest.TestCase):
    def test_rrf_rank_order(self):
        out = retrieval.rrf({"a": {"x": 3, "y": 1}, "b": {"x": 2}})
        self.assertGreater(out["x"], out["y"])

    def test_r1_strong_vs_weak(self):
        nodes = [{"id": "A", "title": "奇偶性", "aliases": [], "errors": [],
                  "summary": "奇偶性的定义。"},
                 {"id": "B", "title": "集合", "aliases": [], "errors": [],
                  "summary": "一定条件下研究对象组成的集合。"}]
        r1 = retrieval.r1_lexicon("奇函数是不是一定过原点", nodes)
        # "奇函数"不该给 B 弱分进 strong（无片段命中）
        strong = {k: v for k, v in r1.items() if v >= 2.0}
        self.assertNotIn("B", strong)

    def test_r2_idf_full_scan(self):
        paras = [{"start_line": 1, "text": "正弦函数是奇函数", "block_kind": "正文",
                  "section_id": "5.4.2"},
                 {"start_line": 2, "text": "集合有确定性", "block_kind": "正文",
                  "section_id": "1.1"}]
        r2 = retrieval.r2_paragraphs("奇函数怎么判断", paras, None)
        self.assertTrue(r2)
        self.assertEqual(list(r2)[0], 1)

    def test_r3_chinese_number(self):
        nodes = [{"id": "A", "title": "集合的概念", "section": "1.1 集合",
                  "pages": [6, 6], "aliases": [], "errors": [], "summary": ""}]
        r3 = retrieval.r3_structural("练习第一题怎么做", nodes,
                                     [{"label": "P6 练习1", "owner_id": "1.1"}])
        # 题号分支的 key 是 owner_id（recall 层负责映射回 node_id）
        self.assertIn("1.1", r3)


class TestRecallContract(unittest.TestCase):
    """G01 端到端：契约字段齐全（skill-io §1.1）。"""

    @classmethod
    def setUpClass(cls):
        r = subprocess.run(
            [PY, "-m", "book2qa.cli", "recall", "--book", "必修第一册",
             "--query", "单调性为什么一定要说任意两个数", "--top", "3"],
            capture_output=True, text=True, encoding="utf-8", cwd=QA_ROOT)
        cls.env = json.loads(r.stdout)

    def test_envelope_fields(self):
        e = self.env
        self.assertEqual(e["exit_code"], 0)
        for k in ("intent", "confidence", "candidates", "fallback"):
            self.assertIn(k, e)
        self.assertEqual(e["intent"], "concept_why")
        c = e["candidates"][0]
        for k in ("node_id", "title", "pages", "score", "why", "summary",
                  "quotes", "formulas", "errors", "exercises"):
            self.assertIn(k, c)
        self.assertTrue(c["quotes"])
        self.assertLessEqual(sum(len(q["text"]) for q in c["quotes"]), 1200)

    def test_top1_is_gold(self):
        self.assertEqual(self.env["candidates"][0]["node_id"],
                         "M1-C3-S2A-K01")

    def test_schedule_short_circuit(self):
        r = subprocess.run(
            [PY, "-m", "book2qa.cli", "recall", "--book", "必修第一册",
             "--query", "今天该复习什么"],
            capture_output=True, text=True, encoding="utf-8", cwd=QA_ROOT)
        e = json.loads(r.stdout)
        self.assertEqual(e["intent"], "schedule")
        self.assertEqual(e["fallback"], {"type": "due"})
        self.assertEqual(e["candidates"], [])

    def test_node_command(self):
        r = subprocess.run(
            [PY, "-m", "book2qa.cli", "node", "M1-C3-S2A-K01"],
            capture_output=True, text=True, encoding="utf-8", cwd=QA_ROOT)
        e = json.loads(r.stdout)
        self.assertEqual(e["exit_code"], 0)
        self.assertEqual(e["node"]["id"], "M1-C3-S2A-K01")


if __name__ == "__main__":
    unittest.main()
