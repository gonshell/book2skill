# -*- coding: utf-8 -*-
"""BATCH-2 互检回归（RV-Q3/Q4/C3/C4/C6/C8 验收）：

① 文档 §3 字段表中每个字段名都能在实现或产物里找到同名字段；
② 实现的 Issue.code 都能在 arch.md（权威声明处）或 report.py 找到；
③ 图号格式：文档不得再出现两段式示例 `图3-5`。
"""
import json
import os
import re
import unittest

DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
PKG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "book2qa")


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


class TestFieldCrossCheck(unittest.TestCase):
    def test_graph_spec_fields_exist_in_code(self):
        spec = read(DOCS, "graph-spec.md")
        m = re.search(r"## 3\. 节点字段(.*?)## 4\.", spec, re.S)
        fields = re.findall(r"\| `(\w+)` \|", m.group(1))
        self.assertIn("aliases", fields)
        self.assertIn("errors", fields)
        self.assertIn("eid", json.dumps(read(PKG, "extract", "exercises.py"),
                                       ensure_ascii=False) or fields)
        code = (read(PKG, "candidate.py") + read(PKG, "graph.py") +
                read(PKG, "extract", "exercises.py"))
        for f in fields:
            # 断言消息必须截断——否则失败时整份源码进测试输出（token 事故）
            hit = f in code
            self.assertTrue(
                hit,
                "字段 %r 文档有、实现无（查找范围：candidate/graph/exercises）" % f)

    def test_no_two_segment_figure_examples(self):
        for name in ("graph-spec.md", "design.md", "transform.md", "pipeline.md"):
            s = read(DOCS, name)
            self.assertNotIn("图3-5", s, "%s 仍有两段式图号示例" % name)

    def test_issue_codes_authority(self):
        """arch.md 声明权威清单在 report.py，不另立一套。"""
        arch = read(DOCS, "arch.md")
        self.assertIn("_CODE_TITLES", arch)
        rp = read(PKG, "report.py")
        self.assertIn("_CODE_TITLES", rp)

    def test_pipeline_lists_para_meta_and_jsonl(self):
        pipe = read(DOCS, "pipeline.md")
        self.assertIn("para_meta.jsonl", pipe)
        self.assertNotIn("figures.json |", pipe)
        self.assertIn("figures.jsonl", pipe)


if __name__ == "__main__":
    unittest.main()
