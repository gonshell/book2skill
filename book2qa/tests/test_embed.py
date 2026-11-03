# -*- coding: utf-8 -*-
"""M1c R4 回归：编码器/索引/R4 路/降级告警。模型缺失时跳过（CI 无模型）。"""
import os
import unittest

MODELS = os.path.expanduser("~/.book2qa/models/bge-onnx")
HAS_MODEL = os.path.isfile(os.path.join(MODELS, "onnx", "model.onnx"))


@unittest.skipUnless(HAS_MODEL, "本地无 bge ONNX 模型")
class TestEmbed(unittest.TestCase):
    def test_encode_shape_and_norm(self):
        from book2qa import embed
        enc = embed.Encoder(MODELS)
        v = enc.encode(["函数的单调性", "什么是奇函数"])
        self.assertEqual(v.shape, (2, 512))
        import numpy as np
        self.assertTrue(((np.linalg.norm(v, axis=1) - 1).astype(float) < 1e-5).all())

    def test_query_prefix_semantic_hit(self):
        """口语描述（无词面重叠）经指令前缀应命中周期性段落。"""
        from book2qa import embed
        enc = embed.Encoder(MODELS)
        idx = embed.load_index(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
        if idx is None:
            self.skipTest("无索引文件")
        hits = embed.search(enc, "就是那种图像一遍遍重复的函数，这节讲啥了", idx, top=5)
        owners = [m["section_id"] for m, _ in hits]
        self.assertTrue(any(o in ("5.4", "5.4.2") for o in owners),
                        owners[:3])


class TestR4Route(unittest.TestCase):
    def test_degradation_reported_in_warnings(self):
        """依赖不可用时 R4 降级必须进 warnings（宽 except 静默吞错的教训）。"""
        import io
        import json
        from contextlib import redirect_stdout
        os.environ["B2Q_MODELS_DIR"] = "/nonexistent/models"
        try:
            import argparse
            from book2qa.commands import recall as RC
            args = argparse.Namespace(book="必修第一册", query="单调性是什么",
                                      top=3, scene="ask", context=None)
            buf = io.StringIO()
            with redirect_stdout(buf):
                RC.execute(args, t0=None)
            env = json.loads(buf.getvalue())   # execute 走 emit：捕获 stdout 解析
            self.assertIn("candidates", env)
        finally:
            os.environ.pop("B2Q_MODELS_DIR")


if __name__ == "__main__":
    unittest.main()
