# -*- coding: utf-8 -*-
"""探测器行为保持对账（搬迁施工准绳）：

三个 inspectors 模块在 gzsx-md/final 上重跑，与原脚本（gzsx-md/scan3.py 等）
的完整报告文本比对（原 stdout+stderr 合并 vs 新 stderr）。

前置：环境变量 TBP_PARITY_SOURCE 指向 gzsx-md 原目录（只读）；未设置时整批 skip。
"""
import contextlib
import io
import os
import subprocess
import sys
import unittest

from textbook_pipe.engine.inspectors import detectors, integrity, texmath

SRC = os.environ.get("TBP_PARITY_SOURCE")
PY = sys.executable


def run_original(script):
    """在 gzsx-md 目录以原解释器跑原脚本，合并 stdout+stderr 返回。"""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONHASHSEED="0")
    r = subprocess.run([PY, script], cwd=SRC, capture_output=True,
                       text=True, encoding="utf-8", env=env, timeout=600)
    return (r.stdout or "") + (r.stderr or "")


def run_new(fn, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        fn(**kw)
    return buf.getvalue()


def norm(text):
    """规整：① 尾部空白/空行；② 过滤告警块（原脚本以 __main__ 运行会显示
    DeprecationWarning 等，库方式调用默认忽略——属环境噪音，非行为差异）。"""
    lines = text.replace("\r\n", "\n").split("\n")
    out, skip_next = [], False
    for ln in lines:
        if skip_next:
            skip_next = False
            continue
        if ln.startswith(("C:\\", "C:/")) and "Warning:" in ln:
            skip_next = True   # 告警行之后跟随一行缩进源码，一并过滤
            continue
        out.append(ln.rstrip())
    return "\n".join(out).strip()


@unittest.skipUnless(SRC, "未设置 TBP_PARITY_SOURCE（指向 gzsx-md 原目录），跳过探测器对账")
class InspectorsParityTest(unittest.TestCase):

    def test_detectors_report_parity(self):
        want = norm(run_original("scan3.py"))
        got = norm(run_new(detectors.run, source_dir=os.path.join(SRC, "final")))
        self.assertEqual(got, want, "detectors（scan3）报告不一致")

    def test_integrity_report_parity(self):
        want = norm(run_original("scan_render.py"))
        got = norm(run_new(integrity.scan, source_dir=os.path.join(SRC, "final")))
        self.assertEqual(got, want, "integrity（scan_render）报告不一致")

    def test_texmath_report_parity(self):
        want = norm(run_original("scan_md_preview.py"))
        got = norm(run_new(texmath.run, source_dir=os.path.join(SRC, "final")))
        self.assertEqual(got, want, "texmath（scan_md_preview）报告不一致")


if __name__ == "__main__":
    unittest.main()
