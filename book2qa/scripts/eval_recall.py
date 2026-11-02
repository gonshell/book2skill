# -*- coding: utf-8 -*-
"""gold 评测集跑分：三路融合 Recall@5 / MRR（serving §5 评测先行）。"""
import json
import os
import subprocess
import sys
import tempfile

QA_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
GOLD = os.path.join(QA_ROOT, "data", "eval_gold.jsonl")


def run_recall(query, top=5):
    r = subprocess.run(
        [PY, "-m", "book2qa.cli", "recall", "--book", "必修第一册",
         "--query", query, "--top", str(top)],
        capture_output=True, text=True, encoding="utf-8", cwd=QA_ROOT)
    return json.loads(r.stdout)


def main():
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8")
            if l.strip()]
    recall5 = mrr = n_eval = 0
    intent_ok = 0
    misses = []
    for g in rows:
        if g["intent"] in ("schedule",):
            continue  # 不进检索的信封，单测覆盖
        n_eval += 1
        e = run_recall(g["query"])
        got = [c["node_id"] for c in e.get("candidates", [])]
        gold = set(g["gold_nodes"])
        if not gold:
            continue
        rank = next((i + 1 for i, nid in enumerate(got) if nid in gold), None)
        if rank:
            recall5 += 1
            mrr += 1.0 / rank
        else:
            misses.append((g["qid"], g["query"][:24], got[:2]))
        if e.get("intent") == g["intent"]:
            intent_ok += 1
    print("评测集: %d 条（可检索 %d）" % (len(rows), n_eval))
    print("Recall@5: %d/%d = %.0f%%" % (recall5, n_eval, 100.0 * recall5 / n_eval))
    print("MRR: %.3f" % (mrr / n_eval))
    print("意图识别: %d/%d" % (intent_ok, len(rows)))
    print("未命中:", misses if misses else "无")


if __name__ == "__main__":
    main()
