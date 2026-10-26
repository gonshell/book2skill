# -*- coding: utf-8 -*-
"""tbp baseline 接线冒烟测试（离线，不依赖网关，spec §6.10）。

init 走真实链路（out/ 产物切片 → 探测器 + KaTeX 渲染计量）；
run 以 mock convert_block 注入同内容/漂移 zip，验证三态退出码。
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from unittest import mock

from textbook_pipe import cli

SEG7 = "# 第一章 示例\n\n题图见图 (images/page_1_fig.png)。\n\n$x^2+1$ 是多项式。\n\n## 小节\n\n正文。"
SEG8 = "# 第一章 续\n\n$a+b=c$ 且 $\\frac{1}{2}>0$。\n\n段落文字若干，用于字符计数。"
SEG10 = "# 第二章\n\n$\\sqrt{2}$ 是无理数，图表见表 (images/page_1_t.png)。"


def _renumber(text, s):
    """模拟 merge_one 的图片页号重编号（page_1_* → page_{s}_*）。"""
    return text.replace("(images/page_1_", "(images/page_%d_" % s)


def _tiny_png():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (200, 120), (200, 220, 240))
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, 189, 109], outline=(60, 60, 160), width=3)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _merged_md():
    """模拟 merge_all 产物：页界标记 + 块内容（图片页号已重编号）。"""
    parts = []
    for s, e, raw in ((7, 7, SEG7), (8, 9, SEG8), (10, 10, SEG10)):
        parts.append("\n\n<!-- ===== 原书物理页 %d-%d ===== -->\n\n%s"
                     % (s, e, _renumber(raw, s)))
    return "".join(parts) + "\n"


def _block_factory(md_by_block):
    """convert_block 假实现：产出单块 zip（merge_one 可真实消费）。

    md_by_block: {(s, e): md_text} 或单值（所有块同文，仅用于漂移注入）。
    """

    def fake(pdf_path, s, e, blocks_dir, api, tier="basic"):
        md = md_by_block[(s, e)] if isinstance(md_by_block, dict) else md_by_block
        os.makedirs(blocks_dir, exist_ok=True)
        zpath = os.path.join(blocks_dir, "block_%d-%d.zip" % (s, e))
        middle = {"pages": [{"page_idx": s - 1,
                             "blocks": [{"type": "page_number",
                                         "content": [{"content": 1}]}]}]}
        with zipfile.ZipFile(zpath, "w") as z:
            z.writestr("markdown.md", md)
            z.writestr("middle_json.json", json.dumps(middle, ensure_ascii=False))
            z.writestr("images/page_1_fig.png", _tiny_png())
        return ("done", "0.1s")

    return fake


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


class BaselineSmoke(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="tbp-bl-")
        cls.ws = os.path.join(cls.tmp, "ws")
        book_dir = os.path.join(cls.ws, "out", "fake-book", "images")
        os.makedirs(book_dir)
        with open(os.path.join(cls.ws, "out", "fake-book", "markdown.md"),
                  "w", encoding="utf-8", newline="\n") as fh:
            fh.write(_merged_md())
        with open(os.path.join(book_dir, "page_7_fig.png"), "wb") as fh:
            fh.write(_tiny_png())
        cls.pdf = os.path.join(cls.ws, "fake-book.pdf")
        with open(cls.pdf, "wb") as fh:
            fh.write(b"%PDF-1.4 fake")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ---------- init ----------

    def test_1_init_no_books_maps_50(self):
        rc, out = _run(["baseline", "init", "--subject", "tbp-bl",
                        "--book", "不存在", "--workspace", self.ws])
        self.assertEqual(rc, 50)
        self.assertEqual(out["error"]["code"], "NO_BOOKS")

    def test_2_init_ok(self):
        rc, out = _run(["baseline", "init", "--subject", "tbp-bl",
                        "--workspace", self.ws])
        self.assertEqual(rc, 0, out)
        bpath = os.path.join(self.ws, "baselines", "tbp-bl", "baseline.json")
        with open(bpath, encoding="utf-8") as fh:
            base = json.load(fh)
        self.assertEqual(base["schema"], "tbp.baseline/v1")
        self.assertEqual(base["books"]["fake-book"][0]["block"], "7-7")
        item = base["books"]["fake-book"][0]
        self.assertGreater(item["chars"], 0)
        self.assertIn("detectors", item)
        self.assertEqual(item["detectors_total"], 0)   # 已验收产物应零命中
        # 样本抽取产物与图片入库
        self.assertTrue(os.path.exists(
            os.path.join(self.ws, "baselines", "tbp-bl", "fake-book", "seg_7-7.md")))
        self.assertTrue(os.path.exists(
            os.path.join(self.ws, "baselines", "tbp-bl", "fake-book", "images",
                         "page_7_fig.png")))

    # ---------- run ----------

    def test_3_run_no_baseline_maps_20(self):
        rc, out = _run(["baseline", "run", "--subject", "没有的科目",
                        "--workspace", self.ws])
        self.assertEqual(rc, 20)
        self.assertEqual(out["error"]["code"], "NO_BASELINE")

    def test_4_run_no_endpoint_maps_30(self):
        with mock.patch("textbook_pipe.commands.baseline.resolve_api",
                        return_value=None):
            rc, out = _run(["baseline", "run", "--subject", "tbp-bl",
                            "--workspace", self.ws])
        self.assertEqual(rc, 30)
        self.assertEqual(out["error"]["code"], "NO_ENDPOINT")

    def test_5_run_consistent_maps_0(self):
        # 重抽 zip 内是原始页号（page_1_*），经 merge_one 重编号后与基线一致
        same = {(7, 7): SEG7, (8, 9): SEG8, (10, 10): SEG10}
        with mock.patch("textbook_pipe.commands.baseline.resolve_api",
                        return_value="http://127.0.0.1:1"), \
                mock.patch.object(sys.modules["textbook_pipe.extractors.mineru"],
                                  "convert_block", _block_factory(same)):
            rc, out = _run(["baseline", "run", "--subject", "tbp-bl",
                            "--workspace", self.ws])
        self.assertEqual(rc, 0, out)
        self.assertEqual(out["status"], "一致")
        self.assertEqual(out["segments"], 3)
        self.assertFalse(out["fingerprint"]["drift"])

    def test_6_run_drift_maps_40(self):
        drifted = {(7, 7): SEG7 + "\n\n后端漂移注入的额外段落内容。",
                   (8, 9): SEG8, (10, 10): SEG10}
        with mock.patch("textbook_pipe.commands.baseline.resolve_api",
                        return_value="http://127.0.0.1:1"), \
                mock.patch.object(sys.modules["textbook_pipe.extractors.mineru"],
                                  "convert_block", _block_factory(drifted)):
            rc, out = _run(["baseline", "run", "--subject", "tbp-bl",
                            "--workspace", self.ws])
        self.assertEqual(rc, 40)
        self.assertEqual(out["status"], "漂移")
        metrics = {d["metric"] for d in out["drifts"]}
        self.assertIn("chars", metrics)
        self.assertTrue(out["fingerprint"] is not None)


class BaselineMeasureParity(unittest.TestCase):
    """测量口径对等（整册化学书实战暴露的两个假漂移源）。

    1) init 基线取自 out/ 的**修复后**产物，run 侧重抽产物必须过同一套 S1–S20：
       否则 S12 清掉的 HTML 表格标记 / S16 修掉的拆散数字会被判成后端漂移
       （化学书实测假漂移 +67% 字符、D7 标签泄漏 0→23、KaTeX 0→3）。
    2) 测量临时目录必须带上被引用的图片：否则 D10 悬空引用全量误报
       （化学书 init 实测 22 处，KaTeX 缺图 144）。
    """

    # raw = 网关原始产物形态；fixed = 过完规则的形态（= out/ 里的基线）
    RAW = ("# 第一章\n\n温度 $1538\\;^{\\circ}\\mathrm{C}$ 熔融，常数 $1.414\\;3$。\n\n"
           "见图 (images/page_1_fig.png)。")
    FIXED = ("# 第一章\n\n温度 $1538^{\\circ}\\mathrm{C}$ 熔融，常数 $1.4143$。\n\n"
             "见图 (images/page_7_fig.png)。")

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="tbp-blp-")
        cls.ws = os.path.join(cls.tmp, "ws")
        bdir = os.path.join(cls.ws, "out", "chem-book")
        os.makedirs(os.path.join(bdir, "images"))
        with open(os.path.join(bdir, "markdown.md"), "w",
                  encoding="utf-8", newline="\n") as fh:
            fh.write("\n\n<!-- ===== 原书物理页 7-7 ===== -->\n\n" + cls.FIXED + "\n")
        with open(os.path.join(bdir, "images", "page_7_fig.png"), "wb") as fh:
            fh.write(_tiny_png())
        cls.pdf = os.path.join(cls.ws, "chem-book.pdf")
        with open(cls.pdf, "wb") as fh:
            fh.write(b"%PDF-1.4 fake")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_1_init_copies_images_so_no_dangling_false_positive(self):
        rc, out = _run(["baseline", "init", "--subject", "chem-blp",
                        "--workspace", self.ws])
        self.assertEqual(rc, 0, out)
        bpath = os.path.join(self.ws, "baselines", "chem-blp", "baseline.json")
        with open(bpath, encoding="utf-8") as fh:
            base = json.load(fh)
        item = base["books"]["chem-book"][0]
        self.assertEqual(item["detectors_total"], 0,
                         "带图测量时不应有 D10 悬空假阳性：%s" % item["detectors"])
        self.assertEqual(item["katex_missing"], 0,
                         "引用图已随测量目录落地，不应报缺图")

    def test_2_rule_fixable_raw_is_not_drift(self):
        raw = {(7, 7): self.RAW}
        with mock.patch("textbook_pipe.commands.baseline.resolve_api",
                        return_value="http://127.0.0.1:1"), \
                mock.patch.object(sys.modules["textbook_pipe.extractors.mineru"],
                                  "convert_block", _block_factory(raw)):
            rc, out = _run(["baseline", "run", "--subject", "chem-blp",
                            "--workspace", self.ws])
        self.assertEqual(rc, 0,
                         "重抽产物经 S1–S20 后应与基线一致（口径对等），实际：%s"
                         % json.dumps(out.get("drifts"), ensure_ascii=False))
        self.assertEqual(out["status"], "一致")


if __name__ == "__main__":
    unittest.main(warnings="ignore")
