# -*- coding: utf-8 -*-
"""M4b：learn/drill/review 三场景端到端模拟（SKILL.md 的可执行契约）。

跑法：python scripts/simulate_m4.py   （TestClient 直连）
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient          # noqa: E402
from book2qa import serve, store, paths            # noqa: E402

BOOK = "必修第一册"
ACCOUNT = "sim-m4-" + __import__("time").strftime("%Y%m%d%H%M%S")


class TestLearn(unittest.TestCase):
    """learn：/section 取序列 → 逐节点带学 → 讲完即练 → log。"""

    def test_learn_flow(self):
        c = TestClient(serve.create_app())
        # ① 学生："带我学 3.2"
        r = c.get("/section/必修第一册/3.2")
        self.assertEqual(r.status_code, 200)
        nodes = r.json()["nodes"]
        self.assertGreaterEqual(len(nodes), 2)
        # ② 前置检查字段在
        self.assertIn("prereq", nodes[0])
        # ③ 逐节点取料 + 出 1 题验证
        for n in nodes[:2]:
            rr = c.post("/recall", json={"book": BOOK, "query": n["title"],
                                         "top": 1, "scene": "learn"})
            self.assertEqual(rr.status_code, 200)
            ev = rr.json()["candidates"][0]
            # 带学素材存在（原文或公式）
            self.assertTrue(ev.get("quotes") or ev.get("formulas"))
            # 讲完即练：log 一次（答对）
            lg = c.post("/log", json={"account": ACCOUNT,
                                      "node_id": n["id"], "correct": True})
            self.assertEqual(lg.status_code, 200)
        # ④ 会话承接
        c.put("/context/%s-learn" % ACCOUNT,
              json={"account": ACCOUNT, "last_node_id": nodes[0]["id"],
                    "history": [{"learned": nodes[0]["id"]}]})
        ctx = c.get("/context/%s-learn" % ACCOUNT)
        self.assertEqual(ctx.status_code, 200)
        self.assertEqual(ctx.json()["last_node_id"], nodes[0]["id"])


class TestDrill(unittest.TestCase):
    """drill：弱项驱动 → 出教材原题 → 判分 → log（错因）。"""

    def test_drill_flow(self):
        c = TestClient(serve.create_app())
        # 先制造弱项：答错一次
        c.post("/log", json={"account": ACCOUNT, "node_id": "M1-C3-S2A-K01",
                             "eid": "3.2#P77 例1", "correct": False,
                             "error_type": "忽略区间前提"})
        r = c.get("/mastery", params={"account": ACCOUNT})
        m = r.json()["mastery"]
        weak = min(m, key=lambda x: x["mastery"])
        self.assertLess(weak["mastery"], 1.0)
        # 取弱项节点的教材原题
        r = c.get("/node/必修第一册/%s" % weak["node_id"])
        exs = r.json()["node"].get("exercises") or []
        self.assertTrue(exs, "弱项节点应有教材题")
        # 学生重做答对 → 错因被覆盖，mastery 回升
        c.post("/log", json={"account": ACCOUNT, "node_id": weak["node_id"],
                             "eid": exs[0].get("eid"),
                             "correct": True})
        r = c.get("/mastery", params={"account": ACCOUNT})
        now = {x["node_id"]: x["mastery"] for x in r.json()["mastery"]}
        self.assertGreater(now[weak["node_id"]], weak["mastery"])


class TestReview(unittest.TestCase):
    """review：due 出题不讲解；答错明天再见（SM-2 重置）。"""

    def test_review_due_cycle(self):
        c = TestClient(serve.create_app())
        # 制造到期项：今天答错 → SM-2 排明天（iv=1）
        lg = c.post("/log", json={"account": ACCOUNT, "node_id": "M1-C5-S4B-K01",
                                  "correct": False}).json()
        import time as _t
        tomorrow = _t.strftime("%Y-%m-%d", _t.localtime(_t.time() + 86400))
        self.assertEqual(lg["next_due"], tomorrow)
        # 明天视角：该节点出现在 due
        from book2qa import paths
        conn = store.connect(paths.resolve_workspace(None))
        try:
            due = store.get_due(conn, ACCOUNT, today=tomorrow)
        finally:
            conn.close()
        self.assertTrue(any(x["node_id"] == "M1-C5-S4B-K01" for x in due))
        # 复习链：明天答对（reps=1→iv 仍 1）→ 再答对（reps=2→iv 6）
        lg2 = c.post("/log", json={"account": ACCOUNT, "node_id": "M1-C5-S4B-K01",
                                   "correct": True}).json()
        self.assertEqual(lg2["interval_days"], 1)
        lg3 = c.post("/log", json={"account": ACCOUNT, "node_id": "M1-C5-S4B-K01",
                                   "correct": True}).json()
        self.assertEqual(lg3["interval_days"], 6)
        # "我忘了诱导公式" → recall 复习模式素材存在
        rr = c.post("/recall", json={"book": BOOK, "query": "我忘了诱导公式",
                                     "top": 1, "scene": "review"})
        ev = rr.json()["candidates"][0]
        self.assertTrue(ev.get("quotes"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
