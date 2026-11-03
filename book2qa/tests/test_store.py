# -*- coding: utf-8 -*-
"""M1b store 回归：SM-2 语义 / due 过滤 / mastery / context / serve 端点。"""
import os
import tempfile
import unittest

from book2qa import store


def fresh():
    tmp = tempfile.mkdtemp()
    os.environ["B2Q_WORKSPACE"] = tmp
    return store.connect(tmp), tmp


class TestSm2(unittest.TestCase):
    def setUp(self):
        self.conn, self.ws = fresh()
        self.today = "2026-11-03"

    def test_first_correct_interval_1(self):
        r = store.log_attempt(self.conn, "stu1", "A", correct=True, today=self.today)
        self.assertEqual(r["next_due"], "2026-11-04")
        self.assertEqual(r["interval_days"], 1)
        self.assertEqual(r["mastery"], 1.0)

    def test_second_correct_interval_6(self):
        store.log_attempt(self.conn, "stu1", "A", correct=True, today="2026-11-01")
        r = store.log_attempt(self.conn, "stu1", "A", correct=True, today=self.today)
        self.assertEqual(r["interval_days"], 6)

    def test_wrong_resets(self):
        store.log_attempt(self.conn, "stu1", "A", correct=True, today="2026-11-01")
        r = store.log_attempt(self.conn, "stu1", "A", correct=False, today=self.today)
        self.assertEqual(r["interval_days"], 1)
        self.assertEqual(r["mastery"], 0.5)  # 1 对 1 错

    def test_easiness_bounds(self):
        # 连错多次：easiness 触底 1.3 不再降
        for _ in range(5):
            r = store.log_attempt(self.conn, "stu1", "A", correct=False)
        row = self.conn.execute("SELECT easiness FROM schedule").fetchone()
        self.assertGreaterEqual(row["easiness"], 1.3)


class TestDueAndMastery(unittest.TestCase):
    def setUp(self):
        self.conn, self.ws = fresh()

    def test_due_only_returned_items(self):
        store.log_attempt(self.conn, "stu1", "A", correct=True, today="2026-11-01")
        # 11-02 答的间隔 1 天 → 11-03 到期
        store.log_attempt(self.conn, "stu1", "B", correct=True, today="2026-11-02")
        due = store.get_due(self.conn, "stu1", today="2026-11-03")
        self.assertEqual({d["node_id"] for d in due}, {"A", "B"})
        due = store.get_due(self.conn, "stu1", today="2026-11-02")
        self.assertEqual([d["node_id"] for d in due], ["A"])

    def test_mastery_sorted_ascending(self):
        for i in range(3):
            store.log_attempt(self.conn, "stu1", "A", correct=True)
        store.log_attempt(self.conn, "stu1", "B", correct=False)
        m = store.get_mastery(self.conn, "stu1")
        self.assertEqual(m[0]["node_id"], "B")   # 最弱在前
        self.assertEqual(m[1]["mastery"], 1.0)


class TestContext(unittest.TestCase):
    def test_roundtrip(self):
        conn, _ = fresh()
        store.put_context(conn, "c1", "stu1", last_node_id="M1-C1-S1-K01",
                          history=[{"q": "什么是集合"}])
        got = store.get_context(conn, "c1")
        self.assertEqual(got["last_node_id"], "M1-C1-S1-K01")
        self.assertEqual(got["history"][0]["q"], "什么是集合")

    def test_missing_returns_none(self):
        conn, _ = fresh()
        self.assertIsNone(store.get_context(conn, "nope"))


class TestServeEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.pop("B2Q_API_KEY", None)
        from fastapi.testclient import TestClient
        from book2qa import serve
        cls.c = TestClient(serve.create_app())

    def test_log_due_mastery_chain(self):
        r = self.c.post("/log", json={"account": "stu9", "node_id": "A",
                                      "eid": "1.1#P6 练习1", "correct": True})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["mastery"], 1.0)
        self.assertEqual(body["interval_days"], 1)   # 首答对 → 明天再练
        self.assertNotEqual(body["next_due"], store._today())
        d = self.c.get("/due", params={"account": "stu9"}).json()["due"]
        self.assertTrue(all(x["node_id"] == "A" for x in d))
        m = self.c.get("/mastery", params={"account": "stu9"}).json()["mastery"]
        self.assertEqual(m[0]["attempts"], 1)

    def test_log_validation_422(self):
        r = self.c.post("/log", json={"account": "stu1"})
        self.assertEqual(r.status_code, 422)

    def test_context_endpoints(self):
        r = self.c.put("/context/c9", json={"account": "stu9",
                                            "last_node_id": "A", "history": [1]})
        self.assertEqual(r.status_code, 200)
        g = self.c.get("/context/c9").json()
        self.assertEqual(g["last_node_id"], "A")
        self.assertEqual(self.c.get("/context/none").status_code, 404)


if __name__ == "__main__":
    unittest.main()
