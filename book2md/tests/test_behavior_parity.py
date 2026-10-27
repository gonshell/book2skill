# -*- coding: utf-8 -*-
"""行为保持对账（搬迁施工准绳）：rules.py 五册自抽取基线干净重跑，
与 gzsx-md/final 现有已验收产物**逐字节**比对。

引擎有意演进产生的差异须逐行登记在 `fixtures/parity_delta_allowlist.json`
（当前仅 S16③ 的 OCR 拆散数字修复，共 5 行对）；除此之外任何差异仍判失败。

前置：环境变量 B2M_PARITY_SOURCE 指向 gzsx-md 原目录（只读，不作任何改动）；
未设置时整批 skip（他机 / CI 无原件时不阻塞）。
"""
import os
import shutil
import tempfile
import unittest

from book2md.engine import rules
try:                                       # python tests/x.py（run_tests.sh 口径）
    from parity_util import unexpected_delta
except ImportError:                        # python -m unittest tests.x
    from tests.parity_util import unexpected_delta

SRC = os.environ.get("B2M_PARITY_SOURCE")
BOOKS = ["选择性必修第三册", "选择性必修第二册", "选择性必修第一册", "必修第二册", "必修第一册"]


@unittest.skipUnless(SRC, "未设置 B2M_PARITY_SOURCE（指向 gzsx-md 原目录），跳过行为保持对账")
class BehaviorParityTest(unittest.TestCase):

    def test_book_parity(self):
        backup_dir = os.path.join(SRC, "final_backup_20261022")
        for book in BOOKS:
            with self.subTest(book=book):
                with tempfile.TemporaryDirectory(prefix="b2m_parity_") as tmp:
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
                    if got != want:
                        # 引擎有意演进而产生的差异须逐行登记在
                        # tests/fixtures/parity_delta_allowlist.json；
                        # 未登记的差异（哪怕只差一个字符）仍然判失败。
                        unexpected = unexpected_delta(got, want, "rules", book)
                        if unexpected is None:
                            print("    [已声明改动] %s 差异全部登记（S16③ 数字拆散修复）" % book)
                            continue
                        self.fail("%s 存在未登记的内容差异：\n%s" % (book, unexpected))


if __name__ == "__main__":
    unittest.main(warnings="ignore")
