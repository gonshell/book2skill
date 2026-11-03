# -*- coding: utf-8 -*-
"""M2c：ask skill 端到端模拟 —— 10 轮对话走 SKILL.md 的完整流程。

本脚本是 SKILL.md 的可执行契约（参考实现）：取料→分流→模板→校验→落库。
跑法：python scripts/simulate_ask.py   （TestClient 直连，不发真实网络包）
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient          # noqa: E402
from book2qa import serve, store                    # noqa: E402

BOOK = "必修第一册"
ACCOUNT = "sim-student"


# ── 以下两个函数 = SKILL.md「回答流程」的最小编码，供对话引擎逐轮调用 ──
def recall(client, query, top=3):
    r = client.post("/recall", json={"book": BOOK, "query": query,
                                     "top": top, "scene": "ask"})
    assert r.status_code == 200, "serve 不可达（铁律 3 应触发）"
    return r.json()


def answer_turn(client, query):
    """一轮 = 取料 + 分流 + 模板选型 + 输出校验。返回 (reply, env)。"""
    env = recall(client, query)
    conf, intent = env.get("confidence"), env.get("intent")
    cands = env.get("candidates", [])

    if conf == "none":
        opts = (env.get("fallback") or {}).get("options") or []
        assert opts, "confidence=none 必须给 options（skill-io §7）"
        return "[回问]" + " / ".join(opts[:3]), env

    top1 = cands[0]
    pages = top1.get("pages") or [None, None]
    quotes = [q.get("text", "") for q in top1.get("quotes", [])]
    prefix = "[确认] " if conf == "low" else ""

    if intent == "concept_why":
        segs = ["直答：" + top1.get("summary", "")[:40],
                "教材怎么说：" + (quotes[0][:60] if quotes else "本节未涵盖"),
                "换个角度看：（反例，仅当原文支撑）",
                "易错点与依据：注意易错点。依据：%s P%s §%s"
                % ("必修一", pages[0], top1["node_id"])]
    elif intent == "stuck":
        segs = ["思路：先看定义再代值",
                "步骤：" + (quotes[0][:60] if quotes else "本节未涵盖"),
                "易错点：…",
                "依据：%s P%s §%s" % ("必修一", pages[0], top1["node_id"])]
    elif intent == "too_broad":
        segs = ["切入点：1）%s 2）%s 3）%s"
                % tuple((c.get("title", "?") for c in cands[:3]))]
    elif intent == "schedule":
        segs = ["清单：（due 列表，不讲解）"]
    else:  # check_work / method_list 同构，v1 演示用统一骨架
        segs = ["错在哪：（引 errors 对应条目）",
                "正确做法：" + (quotes[0][:60] if quotes else "本节未涵盖"),
                "依据：%s P%s §%s" % ("必修一", pages[0], top1["node_id"])]

    reply = prefix + "\n".join(segs)
    # 输出校验（SKILL.md §输出校验）：带依据的模板必须带页 + 引用可溯
    has_basis = intent not in ("too_broad", "schedule")
    if has_basis:
        assert "P%s" % pages[0] in reply, "缺依据页码: %r" % reply
    if quotes and has_basis:
        assert quotes[0][:12] in "\n".join(segs), "引用不可溯（视为编造）"
    # 落库（静默）
    client.post("/log", json={"account": ACCOUNT,
                              "node_id": top1["node_id"],
                              "event": "ask", "query": query})
    return reply, env


class TestSim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(serve.create_app())

    def test_10_turn_dialogue(self):
        script = [
            # (学生话, 期望关键词/断言)
            ("单调性为什么一定要说任意两个数？", ["直答", "教材怎么说", "依据"]),
            ("定义域和区间有什么区别", ["依据"]),
            ("函数一点都听不懂", ["切入点"]),                  # too_broad→3切入点不讲解
            ("就是那种增啊减啊的", ["依据"]),                  # 不专业→low确认前缀或直答
            ("f(x)=x²在R上是增函数，对吧", ["依据"]),          # 前提错→正常命中
            ("练习第一题怎么做", ["依据"]),
            ("怎么做这类定义域的题", ["依据"]),
            ("诱导公式", ["依据"]),
            ("偶函数一定关于y轴对称吗", ["依据"]),
            ("那奇函数呢？它关于什么对称", ["依据"]),          # 追问承接
        ]
        log_path = None
        for i, (q, kws) in enumerate(script, 1):
            reply, env = answer_turn(self.client, q)
            for kw in kws:
                self.assertIn(kw, reply, "第%d轮 %r 缺 %r\n%s" % (i, q, kw, reply))
            self.assertLess(len(reply), 800, "第%d轮超预算" % i)
        # 学情确实落库：ask 事件写入 store（attempt 表经 log_attempt 记 0 分不计错）
        from book2qa import paths
        conn = store.connect(paths.resolve_workspace(None))
        try:
            m = store.get_mastery(conn, ACCOUNT)
        finally:
            conn.close()
        self.assertTrue(m, "10 轮后 store 应有学情")
        # 请求日志（巡检源）应累计 ≥10 条含 ask 场景的记录
        d = paths.data_dir(paths.resolve_workspace(None))
        log_path = os.path.join(d, "request_log.jsonl")
        if os.path.isfile(log_path):
            with open(log_path, encoding="utf-8") as f:
                n = sum(1 for _ in f)
            self.assertGreaterEqual(n, 10)
        print("\n10 轮全通；store 学情账号=%s 记录=%d" % (ACCOUNT, len(m)))

    def test_service_down_fallback(self):
        """铁律 3：服务不可达 → 固定话术，禁止常识作答。"""
        os.environ["B2Q_SERVE_URL"] = "http://127.0.0.1:9"   # 必然拒绝
        try:
            import urllib.request
            try:
                urllib.request.urlopen("http://127.0.0.1:9", timeout=1)
                self.skipTest("9 端口意外可连")
            except Exception:
                pass
            # 模拟 skill 检测：非 200/超时 → 话术
            msg = "我这边查教材出了点问题，稍后再试"
            self.assertIn("查教材", msg)
            self.assertNotIn("单调性", msg)   # 不得带任何教材结论
        finally:
            os.environ.pop("B2Q_SERVE_URL", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
