# -*- coding: utf-8 -*-
"""渲染行为保持对账（搬迁施工准绳）：render.py 双版本重渲，与 gzsx-md 现有产物逐字节比对。

reader 版比对 gzsx-md/html/<book>.html；kb 版比对 gzsx-md/final/kb_html/<book>.html。
前置：环境变量 B2M_PARITY_SOURCE 指向 gzsx-md 原目录（只读）；未设置时整批 skip。
"""
import os
import tempfile
import unittest

from book2md.engine import render

SRC = os.environ.get("B2M_PARITY_SOURCE")
BOOKS = ["必修第一册", "必修第二册", "选择性必修第一册", "选择性必修第二册", "选择性必修第三册"]


@unittest.skipUnless(SRC, "未设置 B2M_PARITY_SOURCE（指向 gzsx-md 原目录），跳过渲染对账")
class RenderParityTest(unittest.TestCase):

    def test_reader_and_kb_parity(self):
        cases = (("reader", os.path.join(SRC, "html")),
                 ("kb", os.path.join(SRC, "final", "kb_html")))
        for variant, want_dir in cases:
            for book in BOOKS:
                with self.subTest(variant=variant, book=book):
                    with tempfile.TemporaryDirectory(prefix="b2m_render_") as out:
                        render.run(books=[book], variant=variant,
                                   source_dir=os.path.join(SRC, "final"), out_dir=out)
                        got = open(os.path.join(out, book + ".html"), "rb").read()
                        want = open(os.path.join(want_dir, book + ".html"), "rb").read()
                        self.assertEqual(
                            len(got), len(want),
                            "%s/%s 大小不一致: got=%d want=%d" % (variant, book, len(got), len(want)))
                        self.assertEqual(got, want, "%s/%s 内容逐字节不一致" % (variant, book))


if __name__ == "__main__":
    unittest.main(warnings="ignore")
