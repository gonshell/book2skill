# -*- coding: utf-8 -*-
"""语料可用性探测（CI 护栏）：recall 链依赖 book2md 原文（含教材原文，不入 git）。

HAS_CORPUS=False 的环境（GitHub Actions）自动跳过语料依赖测试；
语料层由 deploy.sh 的前置测试断言覆盖（那是带语料的真实门）。
"""
import os
import unittest

from book2qa import paths


def has_corpus():
    try:
        files = paths.book_files(paths.resolve_source_root(None), "必修第一册")
        return os.path.isfile(files["markdown"])
    except Exception:
        return False


HAS_CORPUS = has_corpus()
skip_no_corpus = unittest.skipUnless(
    HAS_CORPUS, "无 book2md 产物（CI 无教材原文语料）")
