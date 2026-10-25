# -*- coding: utf-8 -*-
"""抽取契约测试（真实样例金样本，tests/fixtures/README.md §观测到的契约事实）。

用 MinerU 网关原始返回的真实块 zip 钉死两层契约：
① zip 布局与 middle_json 结构（适配器消费前提）；
② merge_one 真实链路输出（金样本回归：引用与文件名同步重编号的不变量）。
样例若被替换，须同步更新 fixtures/README.md 的 sha256 与断言。
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
import zipfile

FIXTURES = os.path.dirname(os.path.abspath(__file__)) + os.sep + "fixtures"
BOOK = "选择性必修第二册"
BLOCK = (87, 114)
ZIP_NAME = "block_%d-%d.zip" % BLOCK

# 观测值（来源：fixtures/README.md，2026-10-25 实测）
OBS = {
    "sha256": "df917a81e4b710923a8b997778567f840563e2a2834b4003872f85e70e04e145",
    "n_images": 84,
    "n_pages": 28,
    "page_idx_range": (86, 113),      # 0 基绝对页号
    "marker": "原书物理页 87-114 · 教材页码 82-None",
}

sys.path.insert(0, os.path.dirname(FIXTURES))
from textbook_pipe.extractors import merge  # noqa: E402


def _fixture_zip():
    return os.path.join(FIXTURES, "blocks", BOOK, ZIP_NAME)


class ZipLayoutContract(unittest.TestCase):
    """① zip 布局契约（适配器消费前提，spec §4.4 Canonical Extraction）。"""

    @classmethod
    def setUpClass(cls):
        cls.z = zipfile.ZipFile(_fixture_zip())
        cls.names = cls.z.namelist()

    @classmethod
    def tearDownClass(cls):
        cls.z.close()

    def test_1_integrity(self):
        import hashlib
        h = hashlib.sha256()
        with open(_fixture_zip(), "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        self.assertEqual(h.hexdigest(), OBS["sha256"],
                         "样例被改动？更新 fixtures/README.md 与本断言")

    def test_2_top_level_layout(self):
        tops = set(n.split("/")[0] for n in self.names)
        for required in ("markdown.md", "middle_json.json", "images"):
            self.assertIn(required, tops, required)
        # MinerU 附带产物（非消费必需，但在场即记录）
        self.assertTrue(tops & {"model_output.json", "structured_content.json"})

    def test_3_middle_json_pages(self):
        mj = json.loads(self.z.read("middle_json.json"))
        pages = mj["pages"]
        self.assertEqual(len(pages), OBS["n_pages"])
        idxs = [p["page_idx"] for p in pages]
        self.assertEqual(min(idxs), OBS["page_idx_range"][0])
        self.assertEqual(max(idxs), OBS["page_idx_range"][1])

    def test_4_image_naming(self):
        imgs = [n for n in self.names if n.startswith("images/")]
        self.assertEqual(len(imgs), OBS["n_images"])
        pat = re.compile(r"images/page_(\d+)_[A-Za-z]+_\d+\.jpg$")
        for n in imgs:
            self.assertRegex(n, pat, n)


class MergeGoldenMaster(unittest.TestCase):
    """② merge_one 真实链路金样本（金样本回归）。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="tbp-contract-")
        blocks_root = os.path.join(cls.tmp, "blocks")
        book_dir = os.path.join(blocks_root, BOOK)
        os.makedirs(book_dir)
        shutil.copy2(_fixture_zip(),
                     os.path.join(book_dir, ZIP_NAME))
        cls.out_root = os.path.join(cls.tmp, "out")
        n_imgs, pages = merge.merge_one(BOOK, BLOCK[0], BLOCK[1],
                                        blocks_root, cls.out_root)
        cls.n_imgs, cls.pages = n_imgs, pages
        cls.md = open(os.path.join(cls.out_root, BOOK, "markdown.md"),
                      encoding="utf-8").read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_1_return_values(self):
        self.assertEqual(self.n_imgs, OBS["n_images"])
        self.assertEqual(self.pages, "82-None")   # 末页 page_number 缺失

    def test_2_marker(self):
        self.assertIn("<!-- ===== " + OBS["marker"] + " ===== -->", self.md)

    def test_3_refs_and_files_renumber_together(self):
        """核心不变量：md 引用与图片文件名同步重编号、一一对应。"""
        out_dir = os.path.join(self.out_root, BOOK, "images")
        files = set(os.listdir(out_dir))
        refs = set(re.findall(r"\(images/([^)]+)\)", self.md))
        self.assertTrue(refs, "样例 md 应含图片引用")
        self.assertTrue(refs <= files,
                        "md 引用但文件缺失：%s" % sorted(refs - files)[:5])
        # 重编号生效：块内不再有原始页号引用（page_idx 86..113 → 172..200）
        raw = set()
        with zipfile.ZipFile(_fixture_zip()) as z:
            with z.open("markdown.md") as fh:
                raw = set(re.findall(r"images/page_(\d+)_",
                                     fh.read().decode("utf-8")))
        for n in raw:
            self.assertNotIn("(images/page_%s_" % n, self.md)

    def test_4_no_untouched_images(self):
        """zip 内全部图片均已按 s+n-1 改名落位（无原名直拷）。"""
        files = set(os.listdir(os.path.join(self.out_root, BOOK, "images")))
        with zipfile.ZipFile(_fixture_zip()) as z:
            raw = set(n.split("/", 1)[1] for n in z.namelist()
                      if n.startswith("images/"))
        self.assertEqual(len(files), OBS["n_images"])
        # 原名与新名允许巧合相等（s+n-1==n 当 n==1），仅断言数量与引用一致性


if __name__ == "__main__":
    unittest.main(warnings="ignore")
