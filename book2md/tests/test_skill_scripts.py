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

    def test_endpoint_health_probe_ok(self):
        """/v1/health 探活（官方 mineru-kit 无 /version），detail 带版本号。"""
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = b'{"version": "9.9.9"}' if self.path.startswith("/v1/health") else b"nope"
                self.send_response(200 if self.path.startswith("/v1/health") else 404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            ws = tempfile.mkdtemp(prefix="tbp-skill-")
            env = dict(os.environ, TBP_BACKEND_API="http://127.0.0.1:%d" % srv.server_port)
            import subprocess
            proc = subprocess.run([sys.executable, os.path.join(SCRIPTS, "precheck.py"),
                                   "--workspace", ws, "--check-endpoint"],
                                  capture_output=True, text=True, encoding="utf-8",
                                  env=env, timeout=120)
            payload = json.loads([l for l in proc.stdout.splitlines() if l.strip()][-1])
            ep = [c for c in payload["checks"] if c["name"] == "endpoint"][0]
            self.assertTrue(ep["ok"], ep)
            self.assertIn("version=9.9.9", ep["detail"])
            self.assertIn("/v1/health", ep["detail"])
        finally:
            srv.shutdown()

    def test_endpoint_unreachable_maps_30(self):
        """端点不可达 → 退出码 30，但仍非致命（离线命令可用）。"""
        ws = tempfile.mkdtemp(prefix="tbp-skill-")
        import subprocess
        env = dict(os.environ, TBP_BACKEND_API="http://127.0.0.1:1")
        proc = subprocess.run([sys.executable, os.path.join(SCRIPTS, "precheck.py"),
                               "--workspace", ws, "--check-endpoint"],
                              capture_output=True, text=True, encoding="utf-8",
                              env=env, timeout=120)
        payload = json.loads([l for l in proc.stdout.splitlines() if l.strip()][-1])
        self.assertEqual(payload["exit_code"], 30)
        self.assertFalse(payload["ok"])
        ep = [c for c in payload["checks"] if c["name"] == "endpoint"][0]
        self.assertFalse(ep["fatal"])


class VerifyDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.mkdtemp(prefix="tbp-skill-")
        self.book = "测试册"

    def _build_delivery(self, html=True, kb_html=True, images=True, layout="legacy"):
        """layout: legacy=工作区级 html/（历史/手工布局）· real=out/<book>/<variant>/（run 实际布局）"""
        bd = os.path.join(self.ws, "out", self.book)
        os.makedirs(bd, exist_ok=True)
        for f in ("markdown.md", "qa_gate.log", "TOC.md", "质检报告.md"):
            open(os.path.join(bd, f), "w", encoding="utf-8").write("x")
        json.dump({"schema": "tbp.issues/v1", "counts": {"A": 0, "B": 0, "C": 0},
                   "items": []},
                  open(os.path.join(bd, "issues.json"), "w", encoding="utf-8"))
        if images:
            os.makedirs(os.path.join(bd, "images"), exist_ok=True)
            open(os.path.join(bd, "images", "p1.png"), "wb").write(b"png")
        html_body = ('<html><head><style>@font-face{src:url(data:font/woff2;base64,AA==)}'
                     '</style></head><body>公式</body></html>')
        targets = {}
        if html:
            targets["html"] = (os.path.join(bd, "html") if layout == "real"
                               else os.path.join(self.ws, "html"))
        if kb_html:
            targets["kb_html"] = (os.path.join(bd, "kb_html") if layout == "real"
                                  else os.path.join(self.ws, "kb_html"))
        for d in targets.values():
            os.makedirs(d, exist_ok=True)
            open(os.path.join(d, self.book + ".html"), "w",
                 encoding="utf-8").write(html_body)

    def test_complete_delivery_maps_0(self):
        self._build_delivery()
        rc, env = run_script("verify_delivery.py", "--workspace", self.ws, "--book", self.book)
        self.assertEqual(rc, 0, env)
        self.assertEqual(env["gaps"], [])

    def test_real_layout_out_subdir_maps_0(self):
        """run 实际产物布局：out/<book>/html|kb_html/<book>.html 必须被认到。"""
        self._build_delivery(layout="real")
        rc, env = run_script("verify_delivery.py", "--workspace", self.ws, "--book", self.book)
        self.assertEqual(rc, 0, env)
        self.assertEqual(env["gaps"], [])
        self.assertTrue(env["html"]["html"]["path"].endswith(os.path.join("html", self.book + ".html")))

    def test_optional_artifacts_reported(self):
        """provenance/page_map/broken_formulas 存在则记入 checks，缺失不判缺口。"""
        self._build_delivery()
        bd = os.path.join(self.ws, "out", self.book)
        for f in ("provenance.json", "page_map.md", "broken_formulas.tsv"):
            open(os.path.join(bd, f), "w", encoding="utf-8").write("x")
        rc, env = run_script("verify_delivery.py", "--workspace", self.ws, "--book", self.book)
        self.assertEqual(rc, 0, env)
        present = {c["name"]: c["present"] for c in env["checks"]
                   if c["name"].startswith("optional:")}
        self.assertEqual(len(present), 3)
        self.assertTrue(all(present.values()))

    def test_missing_toc_maps_10(self):
        self._build_delivery()
        os.remove(os.path.join(self.ws, "out", self.book, "TOC.md"))
        rc, env = run_script("verify_delivery.py", "--workspace", self.ws, "--book", self.book)
        self.assertEqual(rc, 10)
        self.assertTrue(any("TOC.md" in g for g in env["gaps"]))

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


class IssuesCollectTests(unittest.TestCase):
    """issues.json 两条来源：探测器命中（B 档，带行号）+ S16 降级清单（C 档）。"""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="tbp-issues-")
        self.book = "测试册"
        self.bd = os.path.join(self.root, self.book)
        os.makedirs(os.path.join(self.bd, "images"), exist_ok=True)
        open(os.path.join(self.bd, "markdown.md"), "w", encoding="utf-8").write(
            "# 标题\n\n正文一行\n<div>泄漏标签</div>\n\n$$x^2$$\n")

    def _collect(self):
        sys.path.insert(0, REPO)
        from textbook_pipe.commands import _issues
        return _issues.collect(self.book, self.root, books=[self.book])

    def test_detector_items_carry_line_and_excerpt(self):
        issues = self._collect()
        b_items = [it for it in issues["items"] if it["tier"] == "B"]
        self.assertTrue(b_items, issues["detail"])
        self.assertTrue(any(it["line"] for it in b_items))
        self.assertTrue(all(it["excerpt"] for it in b_items))
        self.assertEqual(issues["counts"]["B"], len(b_items) and issues["counts"]["B"])

    def test_broken_formula_items_become_c_tier(self):
        tsv = os.path.join(self.bd, "broken_formulas.tsv")
        open(tsv, "w", encoding="utf-8", newline="\n").write(
            "# 注释行\n"
            "1\tblock\t$$\n$\\stackrel{ \\begin{array} { l } }\t图1-15\n"
            "2\tinline\t$\\textcircled { \\textcircled {\t氢氧燃料电池\n")
        issues = self._collect()
        self.assertEqual(issues["counts"]["C"], 2)
        self.assertEqual(issues["detail"]["broken_formulas"], 2)
        c_items = [it for it in issues["items"] if it["tier"] == "C"]
        self.assertEqual(len(c_items), 2)
        self.assertTrue(all(it["suggestion"] for it in c_items))
        self.assertNotIn("\n", c_items[0]["excerpt"])      # 摘录折叠为单行
        self.assertIn("stackrel", c_items[0]["excerpt"])   # 块公式跨行原串完整保留
        self.assertIn("S16", c_items[0]["detector"])
        ids = [it["id"] for it in issues["items"]]
        self.assertEqual(len(ids), len(set(ids)))          # 编号无重复

    def test_no_tsv_no_c_items(self):
        issues = self._collect()
        self.assertEqual(issues["counts"]["C"], 0)
        self.assertTrue(all(it["tier"] == "B" for it in issues["items"]))


if __name__ == "__main__":
    unittest.main(verbosity=2, warnings="ignore")
