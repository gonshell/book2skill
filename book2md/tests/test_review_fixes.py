# -*- coding: utf-8 -*-
"""评审 BATCH-1 回归（book2md 侧）：RV-E1 / RV-N1 / RV-N2。"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock


class TestRvE1(unittest.TestCase):
    """onboard 失败路径：stdout 恒为合法 JSON 信封。"""

    def test_scan_failure_emits_envelope(self):
        from book2md.commands import onboard
        with tempfile.TemporaryDirectory() as tmp:
            cfg = os.path.join(tmp, "math.json")
            json.dump({"subject": "math"}, open(cfg, "w", encoding="utf-8"))
            contract = os.path.join(tmp, "contract.json")
            json.dump({"ok": True}, open(contract, "w", encoding="utf-8"))
            args = mock.Mock(workspace=tmp, pdf=os.path.join(tmp, "x.pdf"),
                             subject="math", page_range=None, force=False)
            open(args.pdf, "w").close()
            buf = io.StringIO()
            with mock.patch("book2md.commands.onboard._subject_config_path",
                            return_value=cfg), \
                 mock.patch("book2md.commands.onboard.resolve_api",
                            return_value="http://mock:8000"), \
                 mock.patch("book2md.commands.onboard._precheck_gateway",
                            return_value=(True, "mock")), \
                 mock.patch("book2md.extractors.mineru.extract_pdf",
                            return_value={"contract": contract}), \
                 mock.patch("book2md.commands.scan.execute", return_value=50), \
                 redirect_stdout(buf):
                rc = onboard.execute(args, t0=None)
            self.assertEqual(rc, 50)
            env = json.loads(buf.getvalue())      # 失败路径也必须是合法 JSON
            self.assertEqual(env["cmd"], "onboard")
            self.assertFalse(env["ok"])


class TestRvN1(unittest.TestCase):
    """无 Pillow：D6 返回空（环境缺陷不得伪装成内容缺陷）。"""

    def test_d6_without_pil_returns_empty(self):
        from book2md.engine.inspectors import detectors
        with mock.patch.dict(sys.modules, {"PIL": None}):
            self.assertEqual(detectors.d6("任意册"), [])


class TestRvN2(unittest.TestCase):
    """MISSING_IMGS 跨册不累积、不双层嵌套。"""

    def test_two_books_no_accumulation(self):
        import book2md.engine.render as R
        tmp = tempfile.mkdtemp()

        def fake_convert(b, variant, source_dir):
            R.MISSING_IMGS.append((b, "images/missing_%s.jpg" % b))
            return "<html>%s</html>" % b, {"img": 1, "formula": 0, "table": 0,
                                           "heading": 0, "page": 0, "code": 0}

        buf = io.StringIO()
        with mock.patch.object(R, "convert", fake_convert), \
             mock.patch.object(R, "render_all", return_value={}), \
             redirect_stdout(buf):
            res = R.run(books=["A册", "B册"], variant="reader",
                        source_dir=tmp, out_dir=tmp)
        self.assertEqual(res["missing"],
                         [("A册", "images/missing_A册.jpg"),
                          ("B册", "images/missing_B册.jpg")])  # 2 条、无嵌套、册名正确


if __name__ == "__main__":
    unittest.main()
