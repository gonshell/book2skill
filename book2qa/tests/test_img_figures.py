# -*- coding: utf-8 -*-
"""M2 图链回归：recall 挂真图 + /img 出图端点。"""
import os
import unittest

from fastapi.testclient import TestClient

from book2qa import serve


class TestFigures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.pop("B2Q_API_KEY", None)
        root = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", "..", "gzsx-md", "final")
        if not os.path.isdir(os.path.join(root, "必修第一册", "images")):
            raise unittest.SkipTest("无真实语料（CI）")
        os.environ["B2Q_IMAGES_ROOT"] = root
        cls.client = TestClient(serve.create_app())

    def test_top1_has_figures_in_page_range(self):
        r = self.client.post("/recall", json={
            "book": "必修第一册", "query": "单调性为什么一定要说任意两个数"})
        e = r.json()
        figs = e["candidates"][0].get("figures", [])
        self.assertTrue(figs, "单调性节点（P76-82）应挂到图3.2-x")
        self.assertTrue(all(76 <= f["textbook_page"] <= 82 for f in figs))
        self.assertTrue(all(f["file"].startswith("images/") for f in figs))
        self.assertIn("图3.2-2", [f["fig"] for f in figs])

    def test_non_top1_compact_has_no_figures(self):
        r = self.client.post("/recall", json={
            "book": "必修第一册", "query": "函数一点都听不懂", "top": 3})
        for c in r.json()["candidates"][1:]:
            self.assertNotIn("figures", c)

    def test_img_endpoint_auth_and_404(self):
        r = self.client.get("/img/必修第一册/images/page_128_image_4.jpg")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "image/jpeg")
        # 路径穿越 → 404，不泄文件
        self.assertEqual(self.client.get(
            "/img/必修第一册/../secret.txt").status_code, 404)
        self.assertEqual(self.client.get(
            "/img/必修第一册/images/no_such.jpg").status_code, 404)

    def test_img_requires_key_when_auth_on(self):
        os.environ["B2Q_API_KEY"] = "k-img"
        try:
            c = TestClient(serve.create_app())
            self.assertEqual(c.get(
                "/img/必修第一册/images/page_128_image_4.jpg").status_code, 401)
        finally:
            os.environ.pop("B2Q_API_KEY")


if __name__ == "__main__":
    unittest.main()
