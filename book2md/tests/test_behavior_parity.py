# -*- coding: utf-8 -*-
"""行为保持对账（搬迁施工准绳）：rules.py 五册自抽取基线干净重跑，
与 gzsx-md/final 现有已验收产物**逐字节**比对。

前置：环境变量 TBP_PARITY_SOURCE 指向 gzsx-md 原目录（只读，不作任何改动）；
未设置时整批 skip（他机 / CI 无原件时不阻塞）。
"""
import os
import shutil
import tempfile
import unittest

from textbook_pipe.engine import rules

SRC = os.environ.get("TBP_PARITY_SOURCE")
BOOKS = ["选择性必修第三册", "选择性必修第二册", "选择性必修第一册", "必修第二册", "必修第一册"]


@unittest.skipUnless(SRC, "未设置 TBP_PARITY_SOURCE（指向 gzsx-md 原目录），跳过行为保持对账")
class BehaviorParityTest(unittest.TestCase):

    def test_book_parity(self):
        backup_dir = os.path.join(SRC, "final_backup_20261022")
        for book in BOOKS:
            with self.subTest(book=book):
                with tempfile.TemporaryDirectory(prefix="tbp_parity_") as tmp:
                    out_root = os.path.join(tmp, "out")
                    os.makedirs(os.path.join(out_root, book, "images"))
                    src_img = os.path.join(SRC, "final", book, "images")
                    if os.path.isdir(src_img):
                        shutil.copytree(src_img, os.path.join(out_root, book, "images"),
                                        dirs_exist_ok=True)
                    rules.run(books=[book],
                              source_dir=backup_dir,
                              output_dir=out_root)
                    got = open(os.path.join(out_root, book, "markdown.md"), "rb").read()
                    want = open(os.path.join(SRC, "final", book, "markdown.md"), "rb").read()
                    self.assertEqual(
                        len(got), len(want),
                        "%s 字符数不一致: got=%d want=%d" % (book, len(got), len(want)))
                    self.assertEqual(got, want, "%s 内容逐字节不一致" % book)
                    # 首个差异偏移，便于人工定位
                    if got != want:  # pragma: no cover（assertEqual 已先行失败）
                        for i, (a, b) in enumerate(zip(got, want)):
                            if a != b:
                                print("首个差异偏移:", i, got[max(0, i-40):i+40], want[max(0, i-40):i+40])
                                break


if __name__ == "__main__":
    unittest.main(warnings="ignore")
