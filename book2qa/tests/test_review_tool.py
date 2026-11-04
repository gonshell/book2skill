# -*- coding: utf-8 -*-
"""裁定辅助回归：导出/导入/动作执行/配额报告。"""
import json
import os
import tempfile
import unittest

from book2qa.commands import review


def _mk(cands):
    d = tempfile.mkdtemp(prefix="b2q-rev-")
    os.makedirs(os.path.join(d, "data"), exist_ok=True)
    p = os.path.join(d, "data", "candidates.jsonl")
    with open(p, "w", encoding="utf-8") as f:
        for c in cands:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return d, p


def _c(cid, title="t", type_="concept", pages=(10, 12), ex=2):
    return {"id": cid, "title": title, "type": type_, "book": "测试册",
            "chapter": "第一章", "section": "1.1 测试", "pages": list(pages),
            "summary": "", "anchors": [{"quote": "q", "page": pages[0]}],
            "exercises": [{"eid": "%s#e%d" % (cid, i)} for i in range(ex)],
            "unit": "1.1", "status": "unverified", "built_by": "auto",
            "built_at": "", "aliases": [], "errors": []}


class TestReview(unittest.TestCase):
    def _roundtrip(self, cands, annotate):
        """导出→批注→导入 全链，返回 (新cands, diff, errors)。"""
        d, p = _mk(cands)
        xlsx = os.path.join(d, "r.xlsx")
        review.export_xlsx(cands, xlsx)
        from openpyxl import load_workbook
        wb = load_workbook(xlsx)
        ws = wb["候选"]
        annotate(ws)
        wb.save(xlsx)
        acts, errors = review.import_xlsx(xlsx)
        if errors:
            return None, None, errors
        new, diff = review.apply_actions(json.loads(json.dumps(cands)), acts)
        return new, diff, errors

    def test_export_import_roundtrip_keeps_unannotated(self):
        cands = [_c("A-K01", "旧名"), _c("A-K02")]
        new, diff, errors = self._roundtrip(cands, lambda ws: None)
        self.assertEqual(errors, [])
        self.assertEqual(len(new), 2)
        self.assertEqual(diff, [])

    def test_rename_action(self):
        cands = [_c("A-K01", "单调性与最大（小）值")]
        new, diff, _ = self._roundtrip(cands, lambda ws: ws.append(
            ["A-K01", "", "", "", "", "", "", "改名", "函数的增减", "", ""]))
        self.assertEqual(new[0]["title"], "函数的增减")
        self.assertEqual(new[0]["built_by"], "auto+review")

    def test_split_generates_sequential_ids(self):
        cands = [_c("A-K03", "大杂烩", pages=(10, 16))]
        new, diff, _ = self._roundtrip(cands, lambda ws: ws.append(
            ["A-K03", "", "", "", "", "", "", "拆分",
             "单调的定义｜单调的判定｜求单调区间", "", ""]))
        self.assertEqual(len(new), 3)
        self.assertEqual(new[0]["title"], "单调的定义")
        self.assertEqual([c["id"] for c in new[1:]], ["A-K04", "A-K05"])
        self.assertEqual(new[1]["exercises"], [])   # 新块不带原题
        self.assertTrue(any(d["what"] == "拆分新增" for d in diff))

    def test_merge_moves_exercises(self):
        cands = [_c("A-K01", "甲", ex=3), _c("A-K02", "乙")]
        new, diff, _ = self._roundtrip(cands, lambda ws: ws.append(
            ["A-K01", "", "", "", "", "", "", "并入", "A-K02", "", "小并大"]))
        self.assertEqual([c["id"] for c in new], ["A-K02"])
        self.assertEqual(len(new[0]["exercises"]), 5)   # 题 3+2 随迁

    def test_change_type_and_delete(self):
        cands = [_c("A-K01", type_="concept"), _c("A-K02")]
        new, diff, _ = self._roundtrip(cands, lambda ws: (
            ws.append(["A-K01", "", "", "", "", "", "", "改类型", "", "method", ""]),
            ws.append(["A-K02", "", "", "", "", "", "", "删除", "", "", "纯壳"])))
        self.assertEqual([c["id"] for c in new], ["A-K01"])
        self.assertEqual(new[0]["type"], "method")

    def test_invalid_action_rejected_whole(self):
        cands = [_c("A-K01")]
        d, p = _mk(cands)
        xlsx = os.path.join(d, "r.xlsx")
        review.export_xlsx(cands, xlsx)
        from openpyxl import load_workbook
        wb = load_workbook(xlsx)
        wb["候选"].append(["A-K01", "", "", "", "", "", "", "胡写", "x", "", ""])
        wb.save(xlsx)
        acts, errors = review.import_xlsx(xlsx)
        self.assertEqual(acts, [])
        self.assertTrue(any("动作非法" in e for e in errors))

    def test_quota_report(self):
        cands = [_c("A-K01", type_="method"), _c("A-K02", type_="concept")]
        q = review._quota(cands)
        self.assertEqual(q["total"], 2)
        self.assertEqual(q["types"]["method"], 50.0)


if __name__ == "__main__":
    unittest.main()
