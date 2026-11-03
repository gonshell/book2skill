# -*- coding: utf-8 -*-
"""M1a serve 回归：healthz / recall 契约 / 认证 / 请求日志。"""
import os
import unittest

from fastapi.testclient import TestClient

from book2qa import serve


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

    def test_request_log_written(self):
        from book2qa import paths
        log = os.path.join(paths.data_dir(paths.resolve_workspace(None)),
                           "request_log.jsonl")
        self.assertTrue(os.path.isfile(log))
        self.assertIn("单调性", open(log, encoding="utf-8").read())

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


if __name__ == "__main__":
    unittest.main()
