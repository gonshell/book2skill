# -*- coding: utf-8 -*-
"""包结构自检：随包资产与版本一致性（安装后最容易坏的地方）。

两个历史教训都来自真实故障：
① v0.1.0 的 pyproject 缺 package-data → wheel 装完 assets/katex 整个缺失，
   非源码安装方式渲染必然失败（安装冒烟才抓到）；
② 版本号三处不同步（pyproject / __version__ / tag）→ --version 报的是旧值。

这两类问题用 shell 内联断言不好维护，固定成单测后本地与 CI 走同一条路径。
"""
import pathlib
import tomllib
import unittest

import book2md

PKG = pathlib.Path(book2md.__file__).parent
ROOT = PKG.parent


class PackageAssets(unittest.TestCase):

    def test_1_version_matches_pyproject(self):
        pyproject = ROOT / "pyproject.toml"
        if not pyproject.is_file():          # wheel 安装场景没有 pyproject，跳过
            self.skipTest("非源码安装（无 pyproject.toml），跳过版本交叉校验")
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        self.assertEqual(book2md.__version__, data["project"]["version"],
                         "包内 __version__ 与 pyproject 的 project.version 不一致")

    def test_2_katex_assets_present(self):
        kdir = PKG / "assets" / "katex"
        for name in ("katex.min.css", "katex.min.js", "auto-render.min.js"):
            self.assertTrue((kdir / name).is_file(), "缺少随包资产：assets/katex/%s" % name)

    def test_3_katex_fonts_complete(self):
        fonts = list((PKG / "assets" / "katex" / "fonts").glob("*.woff2"))
        self.assertGreaterEqual(len(fonts), 20,
                                "KaTeX 字体应为 20 个，实际 %d 个" % len(fonts))

    def test_4_render_script_present(self):
        self.assertTrue((PKG / "assets" / "render_formulas.js").is_file(),
                        "缺少 assets/render_formulas.js（KaTeX 预渲染入口）")


if __name__ == "__main__":
    unittest.main(warnings="ignore")
