# -*- coding: utf-8 -*-
"""b2m run / convert 接线冒烟测试（离线，不依赖网关）。

策略：mock convert_block 注入伪造 zip 生成真实 extract/<book>（含合法 1x1 PNG，
供 D6/PIL 与渲染使用），随后驱动完整六门流水线（真实 rules/render/inspectors，
Node + KaTeX 资产在位即可，全程不触网）。
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from book2md import cli
from book2md.extractors import mineru

MD = "# 第一章 示例\n\n题图见图 (images/page_7_fig.png)。\n\n$x^2+1$ 是多项式。\n\n## 小节\n\n正文。"


def _tiny_png():
    """生成合法内容图（200x120 彩色；过小/过白会被 D6 判为水印裁片）。"""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (200, 120), (200, 220, 240))
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, 189, 109], outline=(60, 60, 160), width=3)
    d.line([10, 10, 189, 109], fill=(160, 60, 60), width=2)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _fake_block_factory(png_bytes):
    def fake_convert_block(pdf_path, s, e, blocks_dir, api, tier="basic"):
        os.makedirs(blocks_dir, exist_ok=True)
        zpath = os.path.join(blocks_dir, f"block_{s}-{e}.zip")
        middle = {"pages": [{"page_idx": 6,
                             "blocks": [{"type": "page_number",
                                         "content": [{"content": 1}]}]}]}
        import zipfile
        with zipfile.ZipFile(zpath, "w") as z:
            z.writestr("markdown.md", MD)
            z.writestr("middle_json.json", json.dumps(middle, ensure_ascii=False))
            z.writestr("images/page_1_fig.png", png_bytes)
        return ("done", "0.1s")
    return fake_convert_block


def _run(argv):
    buf = io.StringIO()
    devnull = open(os.devnull, "w", encoding="utf-8")
    saved_err = sys.stderr
    sys.stderr = devnull
    try:
        with redirect_stdout(buf):
            rc = cli.main(argv)
    finally:
        sys.stderr = saved_err
        devnull.close()
    return rc, json.loads(buf.getvalue())


class RunSmoke(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="b2m-run-")
        cls.ws = os.path.join(cls.tmp, "ws")
        cls.pdf = os.path.join(cls.tmp, "fake-book.pdf")
        with open(cls.pdf, "wb") as fh:
            fh.write(b"%PDF-1.4 fake")
        # 离线生成真实 extract/<book>
        with mock.patch.object(mineru, "convert_block", _fake_block_factory(_tiny_png())), \
                mock.patch("book2md.commands.extract.resolve_api",
                           return_value="http://127.0.0.1:1"):
            rc, out = _run(["extract", "--book", "fake-book", "--pdf", cls.pdf,
                            "--page-range", "7-7", "--workspace", cls.ws])
        assert rc == 0, out
        # 科目配置（run 需要）
        import book2md.commands.onboard as onboard
        os.makedirs(onboard.CONFIGS_DIR, exist_ok=True)
        with open(os.path.join(onboard.CONFIGS_DIR, "b2m-fake.json"), "w", encoding="utf-8") as fh:
            json.dump({"subject": "b2m-fake", "rules_pack": "packs/b2m-fake.json"}, fh)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_1_no_contract_maps_50(self):
        rc, out = _run(["run", "--book", "不存在", "--subject", "b2m-fake",
                        "--workspace", self.ws])
        self.assertEqual(rc, 50)
        self.assertEqual(out["error"]["code"], "NO_CONTRACT")

    def test_2_no_subject_config_maps_20(self):
        rc, out = _run(["run", "--book", "fake-book", "--subject", "没有的科目",
                        "--workspace", self.ws])
        self.assertEqual(rc, 20)
        self.assertEqual(out["error"]["code"], "NO_SUBJECT_CONFIG")

    def test_3_bad_gate_maps_20(self):
        rc, out = _run(["run", "--book", "fake-book", "--subject", "b2m-fake",
                        "--gates", "fix,不存在", "--workspace", self.ws])
        self.assertEqual(rc, 20)
        self.assertEqual(out["error"]["code"], "BAD_GATES")

    def test_4_subset_keeps_staging(self):
        rc, out = _run(["run", "--book", "fake-book", "--subject", "b2m-fake",
                        "--gates", "deps", "--workspace", self.ws])
        self.assertEqual(rc, 0, out)
        self.assertTrue(any("staging" in w for w in out["warnings"]))
        self.assertFalse(os.path.exists(os.path.join(self.ws, "out", "fake-book")))

    def test_5_full_pipeline_promotes(self):
        rc, out = _run(["run", "--book", "fake-book", "--subject", "b2m-fake",
                        "--workspace", self.ws])
        self.assertEqual(rc, 0, out)
        out_dir = os.path.join(self.ws, "out", "fake-book")
        for rel in ("markdown.md", "html/fake-book.html", "kb_html/fake-book.html",
                    "TOC.md", "质检报告.md", "issues.json", "qa_gate.log"):
            self.assertTrue(os.path.exists(os.path.join(out_dir, rel)), rel)
        # 七项 artifacts（spec §6.6）
        for k in ("markdown", "html", "kb_html", "toc", "qa_report", "issues", "qa_gate_log"):
            self.assertIn(k, out["artifacts"])
        # staging 已清场
        self.assertFalse(os.path.exists(os.path.join(self.ws, "out", "fake-book.staging")))
        # 质检报告是"渲染无误 ≠ 内容一致"的复核队列载体
        qa = open(os.path.join(out_dir, "质检报告.md"), encoding="utf-8").read()
        self.assertIn("人工复核队列", qa)
        # 再跑一遍：旧版挪 .prev 且产物仍完整（幂等重跑）
        rc, out = _run(["run", "--book", "fake-book", "--subject", "b2m-fake",
                        "--workspace", self.ws])
        self.assertEqual(rc, 0, out)
        prevs = [d for d in os.listdir(os.path.join(self.ws, "out"))
                 if d.startswith("fake-book.prev-")]
        self.assertEqual(len(prevs), 1)
        self.assertTrue(os.path.exists(os.path.join(out_dir, "markdown.md")))


if __name__ == "__main__":
    unittest.main(warnings="ignore")
