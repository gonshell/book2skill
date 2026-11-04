# -*- coding: utf-8 -*-
"""画图方案层②回归：表达式白名单 / 确定性渲染 / 缓存幂等 / plotimg 安全。"""
import os
import unittest

from fastapi.testclient import TestClient

from book2qa import plotter, serve


class TestPlotter(unittest.TestCase):
    def test_whitelist_rejects_injection(self):
        bad = [
            {"expr": "__import__('os').system('dir')"},
            {"expr": "x if x>0 else 0"},          # 关键字不在白名单
            {"expr": "open('/etc/passwd')"},
            {"expr": "x; import os"},
            {"expr": "lambda x: x"},
        ]
        for s in bad:
            ok, err = plotter.validate_exprs(s if isinstance(s, list) else [s])
            self.assertFalse(ok, "应拒绝: %s" % s)

    def test_whitelist_accepts_math(self):
        ok, err = plotter.validate_exprs([
            {"expr": "x**2", "domain": [-3, 3], "label": "f(x)=x^2"},
            {"expr": "sin(x)", "domain": [-6.28, 6.28]},
            {"expr": "abs(x+1)-2"},
            {"expr": "heaviside(x-1,0)*(x-1)**2"},
        ])
        self.assertTrue(ok, err)

    def test_render_deterministic_and_graded(self):
        import tempfile
        d = tempfile.mkdtemp(prefix="b2q-plot-")
        specs = [{"expr": "x**2", "domain": [-3, 3]}]
        p1 = os.path.join(d, "a.png")
        plotter.render(specs, p1)
        self.assertTrue(os.path.isfile(p1))
        self.assertGreater(os.path.getsize(p1), 5000)
        # 同表达式哈希一致（缓存键）
        self.assertEqual(plotter.expr_hash(specs), plotter.expr_hash(
            [{"expr": "x**2", "domain": [-3, 3]}]))

    def test_render_rejects_runtime_danger(self):
        import tempfile
        with self.assertRaises(ValueError):
            plotter.render([{"expr": "x.__class__", "domain": [-1, 1]}],
                           os.path.join(tempfile.mkdtemp(), "x.png"))


class TestPlotEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.pop("B2Q_API_KEY", None)
        cls.client = TestClient(serve.create_app())

    def test_plot_roundtrip_and_cache(self):
        body = {"exprs": [{"expr": "x**2", "domain": [-3, 3],
                           "label": "f(x)=x^2"}]}
        r1 = self.client.post("/plot", json=body)
        self.assertEqual(r1.status_code, 200)
        url = r1.json()["url"]
        self.assertRegex(url, r"/plotimg/[0-9a-f]{16}\.png")
        r2 = self.client.post("/plot", json=body)
        self.assertEqual(r2.json()["url"], url)      # 幂等
        img = self.client.get(url)
        self.assertEqual(img.status_code, 200)
        self.assertEqual(img.headers["content-type"], "image/png")
        # 非法表达式 422
        r3 = self.client.post(
            "/plot", json={"exprs": [{"expr": "__import__('os')"}]})
        self.assertEqual(r3.status_code, 422)

    def test_plotimg_name_whitelist(self):
        self.assertEqual(self.client.get(
            "/plotimg/../../etc/passwd").status_code, 404)
        self.assertEqual(self.client.get(
            "/plotimg/zzzz.png").status_code, 404)


if __name__ == "__main__":
    unittest.main()
