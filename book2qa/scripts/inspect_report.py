# -*- coding: utf-8 -*-
"""inspect_report — 巡检报告（M3-3a，运营的眼睛）。

读 request_log.jsonl（serve 的每次 /recall 落一行）→ Markdown 报告：
总量/意图与置信分布/低置信查询聚类（2-gram）/处置建议。
处置建议是"人看的行动清单"，不自动改任何数据（aliases/gold 均人工裁定）。
"""
import collections
import json
import os
import re
import time


def load_log(path):
    rows = []
    if not os.path.isfile(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                try:
                    rows.append(json.loads(ln))
                except json.JSONDecodeError:
                    continue          # 半行损坏跳过，不中断巡检
    return rows


def _bigrams(s):
    s = re.sub(r"[\s，。？！、（）()\"\"']", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def cluster(rows, min_sim=2):
    """低置信查询按 2-gram 重叠贪心聚类 → [[query,...], ...]。"""
    lows = [r["query"] for r in rows if r.get("confidence") in ("low", "none")]
    clusters = []
    for q in lows:
        g = _bigrams(q)
        for c in clusters:
            if len(g & _bigrams(c[0])) >= min_sim:
                c.append(q)
                break
        else:
            clusters.append([q])
    return clusters


def build_report(log_path, out_path, book="必修第一册"):
    rows = load_log(log_path)
    if not rows:
        return None
    total = len(rows)
    intents = collections.Counter(r.get("intent", "?") for r in rows)
    confs = collections.Counter(r.get("confidence", "?") for r in rows)
    lows = [r for r in rows if r.get("confidence") in ("low", "none")]
    clusters = cluster(rows)

    # 高频查询（去重计数）——gold 候选素材
    qcount = collections.Counter(r["query"] for r in rows)

    g = ["# 巡检报告（%s）" % time.strftime("%Y-%m-%d %H:%M"), "",
         "数据：`%s`（%d 条，%s ~ %s）"
         % (log_path, total,
            rows[0].get("ts", "?"), rows[-1].get("ts", "?")), "",
         "## 1. 总量与置信分布", "",
         "| 置信 | 次数 | 占比 |", "|---|---|---|"]
    for c, n in confs.most_common():
        g.append("| %s | %d | %.0f%% |" % (c, n, 100.0 * n / total))
    g += ["", "意图分布：" + "、".join("%s %d" % kv for kv in intents.most_common()), ""]

    g += ["## 2. 低置信查询（巡检的主对象：%d 条）" % len(lows), ""]
    if clusters:
        for i, c in enumerate(clusters, 1):
            g.append("%d. %s" % (i, " ／ ".join("「%s」" % q for q in c[:5])
                                 + ("（等 %d 条）" % len(c) if len(c) > 5 else "")))
        g += ["", "**处置建议**：逐组判断——",
              "- 能定位到某节点 → 补该节点 `aliases`（下次 build 生效）",
              "- 是合理问法但搜不到 → 加进 `eval_gold`（防退化基准）",
              "- 问法本身超纲/歧义 → 不处理，属 clarify 正常工作", ""]
    else:
        g.append("无低置信查询。", "")

    g += ["## 3. 高频查询 Top10（gold 候选素材）", "", "| 次数 | 查询 |", "|---|---|"]
    for q, n in qcount.most_common(10):
        g.append("| %d | %s |" % (n, q))
    g.append("")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(g))
    return out_path


if __name__ == "__main__":
    import sys
    log = sys.argv[1] if len(sys.argv) > 1 else "data/inspect/request_log.jsonl"
    out = sys.argv[2] if len(sys.argv) > 2 else \
        "data/inspect/report-%s.md" % time.strftime("%Y%m%d-%H%M")
    p = build_report(log, out)
    print(p or "日志为空")
