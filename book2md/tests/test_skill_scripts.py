# -*- coding: utf-8 -*-
"""技能壳脚本自测（离线）：precheck / verify_delivery / adjudicate_sheet / overlay_scaffold。

脚本以子进程方式调用（覆盖真实调用路径），stdout JSON 信封断言。
不依赖历史产物、不触网。
"""
import io
import json
import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "skill-textbook-pipe", "scripts")


def run_script(name, *args):
    """以子进程跑技能脚本，返回 (exit_code, envelope)。"""
    import subprocess
    proc = subprocess.run([sys.executable, os.path.join(SCRIPTS, name), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=REPO, timeout=120)
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    envelope = json.loads(lines[-1]) if lines else {}
    return proc.returncode, envelope


class PrecheckTests(unittest.TestCase):
    def test_full_pass_in_dev_env(self):
        rc, env = run_script("precheck.py", "--workspace", tempfile.mkdtemp(prefix="tbp-skill-"))
        self.assertEqual(rc, 0, env)
        self.assertTrue(env["ok"])
        names = {c["name"] for c in env["checks"]}
        self.assertTrue({"tbp_import", "tbp_entry", "node", "katex_assets",
                         "workspace_writable"} <= names)
        for c in env["checks"]:
            if c["fatal"]:
                self.assertTrue(c["ok"], c)
        # tbp_entry 非致命（python -m 降级路径），开发环境源码方式未进 PATH 也应通过
        entry = [c for c in env["checks"] if c["name"] == "tbp_entry"][0]
        self.assertFalse(entry["fatal"])

    def test_endpoint_unconfigured_nonfatal(self):
        ws = tempfile.mkdtemp(prefix="tbp-skill-")
        # 保证端点解析干净（环境变量可能继承）
        import unittest.mock as mock
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TBP_BACKEND_API", None)
            rc, env = run_script("precheck.py", "--workspace", ws, "--check-endpoint")
        self.assertEqual(rc, 0)   # 端点缺失仅警告（不致命）
        ep = [c for c in env["checks"] if c["name"] == "endpoint"][0]
        self.assertFalse(ep["ok"])
        self.assertFalse(ep["fatal"])


class VerifyDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.mkdtemp(prefix="tbp-skill-")
        self.book = "测试册"

    def _build_delivery(self, html=True, kb_html=True, images=True):
        bd = os.path.join(self.ws, "out", self.book)
        os.makedirs(bd, exist_ok=True)
        for f in ("markdown.md", "qa_gate.log"):
            open(os.path.join(bd, f), "w", encoding="utf-8").write("x")
        json.dump({"schema": "tbp.issues/v1", "counts": {"A": 0, "B": 0, "C": 0},
                   "items": []},
                  open(os.path.join(bd, "issues.json"), "w", encoding="utf-8"))
        if images:
            os.makedirs(os.path.join(bd, "images"), exist_ok=True)
            open(os.path.join(bd, "images", "p1.png"), "wb").write(b"png")
        html_body = ('<html><head><style>@font-face{src:url(data:font/woff2;base64,AA==)}'
                     '</style></head><body>公式</body></html>')
        if html:
            os.makedirs(os.path.join(self.ws, "html"), exist_ok=True)
            open(os.path.join(self.ws, "html", self.book + ".html"), "w",
                 encoding="utf-8").write(html_body)
        if kb_html:
            os.makedirs(os.path.join(self.ws, "kb_html"), exist_ok=True)
            open(os.path.join(self.ws, "kb_html", self.book + ".html"), "w",
                 encoding="utf-8").write(html_body)

    def test_complete_delivery_maps_0(self):
        self._build_delivery()
        rc, env = run_script("verify_delivery.py", "--workspace", self.ws, "--book", self.book)
        self.assertEqual(rc, 0, env)
        self.assertEqual(env["gaps"], [])

    def test_missing_html_maps_10(self):
        self._build_delivery(html=False, kb_html=False)
        rc, env = run_script("verify_delivery.py", "--workspace", self.ws, "--book", self.book)
        self.assertEqual(rc, 10)
        self.assertEqual(len(env["gaps"]), 2)

    def test_external_ref_maps_10(self):
        self._build_delivery()
        p = os.path.join(self.ws, "html", self.book + ".html")
        open(p, "w", encoding="utf-8").write('<img src="https://cdn.example.com/x.png">')
        rc, env = run_script("verify_delivery.py", "--workspace", self.ws, "--book", self.book)
        self.assertEqual(rc, 10)
        self.assertTrue(any("外部引用" in g for g in env["gaps"]))

    def test_no_delivery_maps_50(self):
        rc, env = run_script("verify_delivery.py", "--workspace", self.ws, "--book", "不存在")
        self.assertEqual(rc, 50)
        self.assertEqual(env["error"]["code"], "NO_DELIVERY")


class AdjudicateOverlayTests(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.mkdtemp(prefix="tbp-skill-")
        self.book = "测试册"
        bd = os.path.join(self.ws, "out", self.book)
        os.makedirs(bd, exist_ok=True)
        self.issues = {"schema": "tbp.issues/v1", "book": self.book,
                       "counts": {"A": 3, "B": 5, "C": 2},
                       "items": [
                           {"id": "I-0001", "tier": "C", "detector": "顶点bar误识",
                            "line": 42, "excerpt": r"\bar{A}|x", "suggestion": None},
                           {"id": "I-0002", "tier": "B", "detector": "D6水印",
                            "line": 7, "excerpt": "images/page_1.png", "suggestion": None}]}
        json.dump(self.issues, open(os.path.join(bd, "issues.json"), "w",
                                    encoding="utf-8"), ensure_ascii=False)

    def test_sheet_generated_with_c_items(self):
        rc, env = run_script("adjudicate_sheet.py", "--workspace", self.ws, "--book", self.book)
        self.assertEqual(rc, 0, env)
        sheet = open(env["sheet"], encoding="utf-8").read()
        self.assertIn("复核裁定表 — 测试册", sheet)
        self.assertIn("顶点bar误识", sheet)
        self.assertIn("| 42 |", sheet.replace("L42", "42"))
        self.assertNotIn("D6水印", sheet)   # B 档默认不进 C 档复核表

    def test_sheet_missing_maps_50(self):
        rc, env = run_script("adjudicate_sheet.py", "--workspace", self.ws, "--book", "无")
        self.assertEqual(rc, 50)
        self.assertEqual(env["error"]["code"], "NO_ISSUES")

    def test_overlay_scaffold_appends_entry(self):
        rc, _ = run_script("adjudicate_sheet.py", "--workspace", self.ws, "--book", self.book)
        self.assertEqual(rc, 0)
        rc, env = run_script("overlay_scaffold.py", "--workspace", self.ws,
                             "--book", self.book, "--note", "首轮裁定完成")
        self.assertEqual(rc, 0, env)
        entry = json.loads(open(env["overlay"], encoding="utf-8").read().splitlines()[-1])
        self.assertEqual(entry["schema"], "tbp.overlay/v1")
        self.assertEqual(entry["status"], "scaffold")
        self.assertIn("首轮裁定完成", entry["note"])
        self.assertTrue(os.path.exists(os.path.join(self.ws, "overlays", self.book, "README.md")))

    def test_overlay_without_sheet_maps_50(self):
        rc, env = run_script("overlay_scaffold.py", "--workspace", self.ws, "--book", self.book)
        self.assertEqual(rc, 50)
        self.assertEqual(env["error"]["code"], "NO_SHEET")


if __name__ == "__main__":
    unittest.main(verbosity=2, warnings="ignore")
