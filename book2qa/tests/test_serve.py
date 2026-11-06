# -*- coding: utf-8 -*-
"""M1a serve 回归：healthz / recall 契约 / 认证 / 请求日志。"""
import os
import time
import unittest

from fastapi.testclient import TestClient

from book2qa import serve
from tests._corpus import skip_no_corpus


class TestServe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.pop("B2Q_API_KEY", None)   # 开发模式
        cls.client = TestClient(serve.create_app())

    def test_healthz(self):
        r = self.client.get("/healthz")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["index_loaded"])
        self.assertEqual(body["auth"], "off(dev)")
        self.assertGreater(body["nodes"], 0)

    @skip_no_corpus
    def test_recall_contract(self):
        r = self.client.post("/recall", json={
            "book": "必修第一册", "query": "单调性为什么一定要说任意两个数"})
        self.assertEqual(r.status_code, 200)
        e = r.json()
        for k in ("intent", "confidence", "candidates", "fallback"):
            self.assertIn(k, e)
        self.assertEqual(e["intent"], "concept_why")
        self.assertEqual(e["candidates"][0]["node_id"], "M1-C3-S2A-K01")

    def test_recall_empty_query_422(self):
        r = self.client.post("/recall", json={"book": "必修第一册", "query": "  "})
        self.assertEqual(r.status_code, 422)

    @skip_no_corpus
    def test_request_log_written(self):
        from book2qa import paths
        log = os.path.join(paths.data_dir(paths.resolve_workspace(None)),
                           "request_log.jsonl")
        self.assertTrue(os.path.isfile(log))
        self.assertIn("单调性", open(log, encoding="utf-8").read())

    @skip_no_corpus
    def test_auth_on_rejects_missing_key(self):
        os.environ["B2Q_API_KEY"] = "secret1"
        try:
            c = TestClient(serve.create_app())
            r = c.post("/recall", json={"book": "必修第一册", "query": "单调性"})
            self.assertEqual(r.status_code, 401)
            r = c.post("/recall", headers={"X-API-Key": "secret1"},
                       json={"book": "必修第一册", "query": "单调性"})
            self.assertEqual(r.status_code, 200)
        finally:
            os.environ.pop("B2Q_API_KEY")

    def test_node_endpoint(self):
        r = self.client.get("/node/必修第一册/M1-C3-S2A-K01")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["node"]["id"], "M1-C3-S2A-K01")

    # ── M2a：/section 与 /context 过期 ──
    def test_section_returns_node_sequence(self):
        r = self.client.get("/section/必修第一册/3.2")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["title"])               # 3.2 是壳节，标题为节名即可
        self.assertIn("函数", body["title"])
        ids = [n["id"] for n in body["nodes"]]
        self.assertTrue(len(ids) >= 2)
        self.assertEqual(ids, sorted(ids))          # 按 id 有序（学习顺序）
        self.assertTrue(all("prereq" in n and "pages" in n
                            for n in body["nodes"]))

    def test_section_subsection_hit_and_404(self):
        r = self.client.get("/section/必修第一册/5.4.2")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["section_id"], "5.4.2")
        self.assertEqual(self.client.get(
            "/section/必修第一册/9.9").status_code, 404)

    def test_context_expiry_after_7_days(self):
        from book2qa import store
        conn = store.connect(_tmp_ws())
        try:
            store.put_context(conn, "ctx-exp", "acc1", last_node_id="A",
                              history=[{"q": "x"}])
            # 人工把 updated_at 拨回 8 天前 → 应视同不存在
            old = time.strftime("%Y-%m-%d %H:%M:%S",
                                time.localtime(time.time() - 8 * 86400))
            conn.execute("UPDATE context SET updated_at=? WHERE context_id=?",
                         (old, "ctx-exp"))
            self.assertIsNone(store.get_context(conn, "ctx-exp"))
            # 新鲜的仍在
            store.put_context(conn, "ctx-fresh", "acc1", last_node_id="B")
            self.assertIsNotNone(store.get_context(conn, "ctx-fresh"))
        finally:
            conn.close()

    def test_context_roundtrip_via_http(self):
        self.client.put("/context/ctx-http", json={
            "account": "stu1", "last_node_id": "M1-C3-S2A-K01",
            "history": [{"q": "单调性"}]})
        r = self.client.get("/context/ctx-http")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["last_node_id"], "M1-C3-S2A-K01")
        self.assertEqual(body["history"], [{"q": "单调性"}])


def _tmp_ws():
    import tempfile
    d = tempfile.mkdtemp(prefix="b2q-ctx-")
    os.makedirs(os.path.join(d, "data"), exist_ok=True)
    return d


if __name__ == "__main__":
    unittest.main()
