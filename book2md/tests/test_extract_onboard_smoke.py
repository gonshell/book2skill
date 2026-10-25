# -*- coding: utf-8 -*-
"""extract / onboard 命令接线冒烟测试（离线，不依赖网关）。

策略：
- 端点缺失 / PDF 缺失 / 配置模板等错误路径直接走 CLI；
- 成功路径以 mock 替换 convert_block 注入伪造 zip（含 markdown.md + middle_json.json +
  images/），驱动真实的 merge_one/merge_all/contract 落盘链路；
- 网关预检 mock 为可控结果，覆盖 30 退出码映射。
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from textbook_pipe import cli
from textbook_pipe.extractors import mineru

MD = "题图见图 (images/page_1_fig.png)。$x^2$ 检验文本。"


def _fake_block_factory(md_text, page_idx, book_page):
    """构造 convert_block 替身：向 blocks_dir 写入可合并的伪造 zip。"""
    def fake_convert_block(pdf_path, s, e, blocks_dir, api, tier="basic"):
        os.makedirs(blocks_dir, exist_ok=True)
        zpath = os.path.join(blocks_dir, f"block_{s}-{e}.zip")
        middle = {"pages": [{"page_idx": page_idx,
                             "blocks": [{"type": "page_number",
                                         "content": [{"content": book_page}]}]}]}
        with __import__("zipfile").ZipFile(zpath, "w") as z:
            z.writestr("markdown.md", md_text)
            z.writestr("middle_json.json", json.dumps(middle, ensure_ascii=False))
            z.writestr("images/page_1_fig.png", b"\x89PNG-fake")
        return ("done", "0.1s")
    return fake_convert_block


def _mkpdf(tmp, name="fake-book"):
    p = os.path.join(tmp, name + ".pdf")
    with open(p, "wb") as fh:
        fh.write(b"%PDF-1.4 fake")
    return p


def _run(argv):
    """执行 cli.main，返回 (退出码, stdout 信封 dict)；stderr 丢弃。"""
    buf = io.StringIO()
    with redirect_stdout(buf), open(os.devnull, "w", encoding="utf-8") as devnull, \
            redirect_stderr_to(devnull):
        rc = cli.main(argv)
    return rc, json.loads(buf.getvalue())


class redirect_stderr_to:
    def __init__(self, target):
        self.target = target
        self.saved = None

    def __enter__(self):
        self.saved = sys.stderr
        sys.stderr = self.target
        return self

    def __exit__(self, *exc):
        sys.stderr = self.saved


class ExtractSmoke(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tbp-smoke-")
        self.ws = os.path.join(self.tmp, "ws")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_extract_no_endpoint(self):
        with mock.patch("textbook_pipe.commands.extract.resolve_api", return_value=None):
            pdf = _mkpdf(self.tmp)
            rc, out = _run(["extract", "--book", "fake-book", "--pdf", pdf,
                            "--page-range", "7-7", "--workspace", self.ws])
        self.assertEqual(rc, 20)
        self.assertEqual(out["error"]["code"], "NO_ENDPOINT")

    def test_extract_pdf_missing(self):
        pdf = os.path.join(self.tmp, "no.pdf")
        rc, out = _run(["extract", "--book", "x", "--pdf", pdf,
                        "--workspace", self.ws])
        self.assertEqual(rc, 50)
        self.assertEqual(out["error"]["code"], "NOT_FOUND")

    def test_extract_page_range_bad(self):
        from textbook_pipe.commands.extract import parse_page_range
        with self.assertRaises(ValueError):
            parse_page_range("7-3")
        with self.assertRaises(ValueError):
            parse_page_range("abc")
        self.assertEqual(parse_page_range("7"), (7, 7))
        self.assertEqual(parse_page_range(None), (None, None))

    def test_extract_backend_failed_maps_30(self):
        with mock.patch("textbook_pipe.commands.extract.resolve_api",
                        return_value="http://127.0.0.1:1"), \
                mock.patch.object(mineru, "convert_block",
                                  lambda *a, **k: ("failed", "HTTP 000 simulated")):
            pdf = _mkpdf(self.tmp)
            rc, out = _run(["extract", "--book", "fake-book", "--pdf", pdf,
                            "--page-range", "7-7", "--workspace", self.ws])
        self.assertEqual(rc, 30)
        self.assertEqual(out["error"]["code"], "BACKEND_FAILED")

    def test_extract_full_offline(self):
        with mock.patch("textbook_pipe.commands.extract.resolve_api",
                        return_value="http://127.0.0.1:1"), \
                mock.patch.object(mineru, "convert_block",
                                  _fake_block_factory(MD, page_idx=6, book_page=1)):
            pdf = _mkpdf(self.tmp)
            rc, out = _run(["extract", "--book", "不一致名", "--pdf", pdf,
                            "--page-range", "7-7", "--workspace", self.ws])
        self.assertEqual(rc, 0, out)
        # book id 以文件名为准并告警
        self.assertEqual(out["book"], "fake-book")
        self.assertTrue(any("不一致" in w for w in out["warnings"]))

        md = os.path.join(self.ws, "extract", "fake-book", "markdown.md")
        self.assertTrue(os.path.exists(md))
        text = open(md, encoding="utf-8").read()
        self.assertIn("(images/page_7_fig.png)", text)     # 物理页重命名（7+1-1=7）
        self.assertIn("原书物理页 7-7", text)               # 块头注释

        contract = json.load(open(os.path.join(self.ws, "extract", "fake-book",
                                               "contract.json"), encoding="utf-8"))
        self.assertEqual(contract["schema"], "tbpipe.extraction/v1")
        self.assertTrue(contract["source_pdf"]["sha256"])  # 指纹必须含哈希（非 None）
        self.assertEqual(contract["images"],
                         [{"asset": "images/page_7_fig.png",
                           "physical_page": None, "alt_source": "auto"}])
        self.assertEqual(contract["markdown"], md)
        self.assertIsNone(contract["meta"]["backend"]["mineru_version"])  # 未上报 → 显式 null

        ledger = json.load(open(os.path.join(self.ws, "ledger.json"), encoding="utf-8"))
        self.assertEqual(ledger["books"]["fake-book"]["blocks"]["7-7"], "done")


class OnboardSmoke(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tbp-smoke-")
        self.ws = os.path.join(self.tmp, "ws")
        self.cfg_dir = os.path.join(self.tmp, "subject-configs")
        self.pdf = _mkpdf(self.tmp)
        self.argv = ["onboard", "--subject", "tbp-fake", "--pdf", self.pdf,
                     "--page-range", "7-7", "--workspace", self.ws]

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_onboard_full_offline(self):
        import textbook_pipe.commands.onboard as onboard
        api = "http://127.0.0.1:1"
        with mock.patch.object(onboard, "CONFIGS_DIR", self.cfg_dir), \
                mock.patch.object(onboard, "resolve_api", return_value=api):
            # 首跑：科目配置缺失 → 模板落盘 + 退出码 20
            rc, out = _run(self.argv)
            self.assertEqual(rc, 20)
            self.assertEqual(out["error"]["code"], "NO_SUBJECT_CONFIG")
            tpl = json.load(open(os.path.join(self.cfg_dir, "tbp-fake.json"), encoding="utf-8"))
            self.assertEqual(tpl["subject"], "tbp-fake")
            self.assertIn("toc_chapter_pattern", tpl)

            # 网关不可达 → 退出码 30
            with mock.patch.object(onboard, "_precheck_gateway",
                                   lambda a: (False, "refused")):
                rc, out = _run(self.argv)
            self.assertEqual(rc, 30)
            self.assertEqual(out["error"]["code"], "GATEWAY_UNREACHABLE")

            # 预检通过 + 注入伪造块 → 全流程成功，issues + provenance 落盘
            with mock.patch.object(onboard, "_precheck_gateway",
                                   lambda a: (True, "HTTP 200")), \
                    mock.patch.object(mineru, "convert_block",
                                      _fake_block_factory(MD, page_idx=6, book_page=1)):
                rc, out = _run(self.argv)
            self.assertEqual(rc, 0, out)

        out_dir = os.path.join(self.ws, "out", "fake-book")
        issues = json.load(open(os.path.join(out_dir, "issues.json"), encoding="utf-8"))
        self.assertEqual(issues["schema"], "tbp.issues/v1")
        self.assertEqual(issues["book"], "fake-book")
        prov = json.load(open(os.path.join(out_dir, "provenance.json"), encoding="utf-8"))
        self.assertEqual(prov["schema"], "tbp.provenance/v1")
        self.assertEqual(prov["adapter"], "mineru-remote")
        self.assertEqual(prov["gateway"], {"endpoint": api, "tier": "basic"})
        self.assertTrue(prov["source_pdf"]["sha256"])
        self.assertTrue(os.path.exists(os.path.join(self.ws, "extract", "fake-book",
                                                    "contract.json")))
        self.assertEqual(out["artifacts"]["issues"], os.path.join(out_dir, "issues.json"))


if __name__ == "__main__":
    unittest.main(warnings="ignore")
