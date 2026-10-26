# -*- coding: utf-8 -*-
"""抽取合并行为保持对账（搬迁施工准绳，切片 4 的离线验证）：

extractors/merge.py 以 gzsx-md/blocks/ 的历史 zip 按页序重合并，补 postprocess 链
（clean_noise + 公式双表示——历史上 rematch 后、fix_md 前执行过一次），
与 final_backup_20261022（修复前快照）比对。

比对口径：
  - 行尾归一：legacy 合并以 Windows 文本模式写盘（CRLF），新链路写 LF——
    行尾差异属写盘模式，非内容差异；
  - images/ 文件清单比对。

前置：环境变量 TBP_PARITY_SOURCE 指向 gzsx-md 原目录（只读）；未设置时整批 skip。
"""
import os
import tempfile
import unittest

from textbook_pipe.extractors import merge
from textbook_pipe.engine import reporting
try:                                       # python tests/x.py（run_tests.sh 口径）
    from parity_util import unexpected_delta
except ImportError:                        # python -m unittest tests.x
    from tests.parity_util import unexpected_delta

SRC = os.environ.get("TBP_PARITY_SOURCE")
BOOKS = ["选择性必修第三册", "选择性必修第二册", "选择性必修第一册", "必修第二册", "必修第一册"]


def _norm(data):
    return data.replace(b"\r\n", b"\n")


@unittest.skipUnless(SRC, "未设置 TBP_PARITY_SOURCE（指向 gzsx-md 原目录），跳过合并对账")
class MergeParityTest(unittest.TestCase):

    def test_merge_parity(self):
        blocks_root = os.path.join(SRC, "blocks")
        ledger = os.path.join(SRC, "ledger.json")
        for book in BOOKS:
            with self.subTest(book=book):
                with tempfile.TemporaryDirectory(prefix="tbp_merge_") as tmp:
                    merge.merge_all(blocks_root=blocks_root, out_root=tmp,
                                    ledger_path=ledger, books=[book])
                    p = os.path.join(tmp, book, "markdown.md")
                    md = open(p, encoding="utf-8").read()
                    md = reporting.clean_noise(md)
                    md = reporting.add_formula_alt(md)
                    open(p, "w", encoding="utf-8", newline="\n").write(md)
                    got = _norm(open(p, "rb").read())
                    want = _norm(open(os.path.join(SRC, "final_backup_20261022",
                                                   book + ".markdown.md"), "rb").read())
                    if got != want:
                        # 已声明改动：merge 现会把 HTML 表格 src="images/..." 引用
                        # 与普通引用同步改写（历史漏改 → 表内图悬空）。逐行登记在
                        # fixtures/parity_delta_allowlist.json 的 merge 段。
                        unexpected = unexpected_delta(got, want, "merge", book)
                        if unexpected is None:
                            print("    [已声明改动] %s 差异全部登记（表格 src 引用同步改写）" % book)
                        else:
                            self.fail("%s 存在未登记的内容差异：\n%s" % (book, unexpected))
                    got_imgs = set(os.listdir(os.path.join(tmp, book, "images")))
                    want_imgs = set(os.listdir(os.path.join(SRC, "final", book, "images")))
                    # 口径：final ⊆ 合并输出（0 缺失）。合并输出多出的部分 = 水印图等
                    # 未引用裁片，由下游 rules S12 移除（属修复阶段职责，非合并阶段）。
                    self.assertEqual(set(), want_imgs - got_imgs,
                                     "%s images 有缺失（final 有而合并输出无）" % book)


if __name__ == "__main__":
    unittest.main(warnings="ignore")
