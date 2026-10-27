# -*- coding: utf-8 -*-
"""抽取指纹实测填充 + baseline 抽样三级优先（2026-10-27 D2 收尾两项）。

1) collect_fingerprint：官方 mineru-kit 无 /version，版本取 GET /v1/health 的
   version 字段（实测 {"status":"ok","version":"4.0.12",...}）。
   纪律：未配置端点/探活失败 → 字段一律 None（禁止占位假值，backend.md §3）。
2) _pick_segments：init 抽样三级优先——pages 显式页列表 > blocks:"all"
   （按账本抽取块全覆盖，免手填页码）> 默认首/中/尾各 2 页。
"""
import unittest
from unittest import mock

from book2md.commands.baseline import _pick_segments
from book2md.extractors import mineru


def _segs(*ranges):
    return [{"s": s, "e": e, "text": "<!-- ===== 原书物理页 %d-%d ===== -->\n内容"
             % (s, e)} for s, e in ranges]


class CollectFingerprint(unittest.TestCase):

    def test_1_no_endpoint_all_none(self):
        with mock.patch.object(mineru, "resolve_api", return_value=None):
            fp = mineru.collect_fingerprint()
        self.assertIsNone(fp["gateway_version"])
        self.assertIsNone(fp["mineru_version"])
        self.assertIn("未配置", fp["note"])

    def test_2_health_version_filled(self):
        health = {"status": "ok", "version": "4.0.12",
                  "features": {"output_formats": ["zip"]}}
        with mock.patch.object(mineru, "resolve_api",
                               return_value="http://127.0.0.1:8000"), \
                mock.patch.object(mineru, "_http_get_json", return_value=health):
            fp = mineru.collect_fingerprint()
        self.assertEqual(fp["gateway_version"], "4.0.12")
        self.assertEqual(fp["mineru_version"], "4.0.12")
        self.assertIn("/v1/health", fp["note"])

    def test_3_probe_failure_stays_none(self):
        with mock.patch.object(mineru, "resolve_api",
                               return_value="http://127.0.0.1:1"), \
                mock.patch.object(mineru, "_http_get_json", return_value=None):
            fp = mineru.collect_fingerprint()
        self.assertIsNone(fp["gateway_version"])
        self.assertIsNone(fp["mineru_version"])
        self.assertIn("探活失败", fp["note"])

    def test_4_health_without_version_stays_none(self):
        with mock.patch.object(mineru, "resolve_api",
                               return_value="http://127.0.0.1:1"), \
                mock.patch.object(mineru, "_http_get_json",
                                  return_value={"status": "ok"}):
            fp = mineru.collect_fingerprint()
        self.assertIsNone(fp["gateway_version"])
        self.assertIn("version", fp["note"])

    def test_5_explicit_api_arg_skips_resolve(self):
        with mock.patch.object(mineru, "resolve_api") as mresolve, \
                mock.patch.object(mineru, "_http_get_json",
                                  return_value={"version": "4.0.12"}) as mget:
            fp = mineru.collect_fingerprint("http://explicit:8000/")
        mresolve.assert_not_called()
        mget.assert_called_once_with("http://explicit:8000/v1/health")
        self.assertEqual(fp["gateway_version"], "4.0.12")


class PickSegments(unittest.TestCase):
    """segs：3 个页界切片 7-7 / 8-9 / 10-10（模拟 40 页块切法的缩小版）。"""

    def setUp(self):
        self.segs = _segs((7, 7), (8, 9), (10, 10))

    def test_1_pages_cfg_has_priority(self):
        got = _pick_segments(self.segs, [7, 10], "all", {"7-7": "done"})
        self.assertEqual([s["s"] for s, _ in got], [7, 10])
        self.assertEqual(got[0][1], [7])
        self.assertEqual(got[1][1], [10])

    def test_2_blocks_all_uses_ledger(self):
        led = {"7-7": "done", "8-9": "done", "10-10": "done"}
        got = _pick_segments(self.segs, None, "all", led)
        self.assertEqual([(s["s"], s["e"]) for s, _ in got],
                         [(7, 7), (8, 9), (10, 10)])
        # 块模式：抽样页 = 块界
        self.assertEqual(got[1][1], [8, 9])

    def test_3_blocks_all_degrades_without_ledger(self):
        got = _pick_segments(self.segs, None, "all", None)
        self.assertEqual([(s["s"], s["e"]) for s, _ in got],
                         [(7, 7), (8, 9), (10, 10)])

    def test_4_blocks_all_degrades_on_ledger_mismatch(self):
        got = _pick_segments(self.segs, None, "all", {"99-100": "done"})
        self.assertEqual(len(got), 3, "账本无匹配块时应退化为全切片，不得返回空样")

    def test_5_default_first_mid_last(self):
        got = _pick_segments(self.segs, None, None, None)
        sampled = sorted(p for _, ps in got for p in ps)
        self.assertEqual(sampled, [7, 8, 9, 10])   # 小范围退化为全页
        self.assertEqual([s["s"] for s, _ in got], [7, 8, 10])

    def test_6_empty_pick_signals_no_cover(self):
        self.assertEqual(_pick_segments([], [7], None, None), [])


if __name__ == "__main__":
    unittest.main(warnings="ignore")
