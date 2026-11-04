# -*- coding: utf-8 -*-
"""plotter — 确定性函数绘图（画图方案层②，2026-11-04 用户批准）。

设计铁律：**LLM 只出表达式，绘图由确定性代码完成。**
数学图必须按计算画，不能按印象画——渐近线、单调区间、交点位置不容许
生成式模型"凭感觉"。表达式过白名单校验，非法直接拒绝。

接口：
  validate_exprs(specs)      → (ok, error)   白名单校验
  render(specs, out_path)    → 渲染 PNG 到指定路径
"""
import hashlib
import json
import re

# 允许出现在表达式中的词法单元（安全 eval 的前置闸）
_ALLOWED_TOKENS = re.compile(
    r"^\s*[-+*/%(),.\d\s xXeE]|\b(sin|cos|tan|asin|acos|atan|sinh|cosh|tanh|"
    r"sqrt|abs|log|log2|log10|ln|exp|floor|ceil|heaviside|minimum|maximum|pi|e)\b")
_FUNCS = {
    "sin": "sin", "cos": "cos", "tan": "tan", "asin": "arcsin",
    "acos": "arccos", "atan": "arctan", "sinh": "sinh", "cosh": "cosh",
    "tanh": "tanh", "sqrt": "sqrt", "abs": "abs", "log": "log",
    "log2": "log2", "log10": "log10", "ln": "log", "exp": "exp",
    "floor": "floor", "ceil": "ceil", "heaviside": "heaviside",
    "minimum": "minimum", "maximum": "maximum",
    "pi": "pi", "e": "e",
}


def validate_exprs(specs):
    """specs: [{expr, domain?, label?}] → (ok, error)。拒绝一切白名单外内容。"""
    if not specs or not isinstance(specs, list) or len(specs) > 4:
        return False, "exprs 必须是 1–4 条"
    for s in specs:
        expr = str(s.get("expr", ""))
        if not expr or len(expr) > 120:
            return False, "expr 缺失或超长（≤120 字符）"
        # 逐词法检查：剥掉白名单 token 后必须只剩空白
        rest = expr
        for _ in range(50):
            m = _ALLOWED_TOKENS.search(rest)
            if not m:
                break
            rest = rest[m.end():] if m.start() == 0 else \
                rest[:m.start()] + rest[m.end():]
        residue = re.sub(r"[\s]", "", _strip_ok(rest))
        if residue:
            return False, "表达式含白名单外内容：%r" % residue[:20]
        dom = s.get("domain") or [-5, 5]
        if not (isinstance(dom, list) and len(dom) == 2
                and all(isinstance(v, (int, float)) for v in dom)
                and -1000 <= dom[0] < dom[1] <= 1000):
            return False, "domain 非法（须 [min,max] 且 |值|≤1000）"
    return True, None


def _strip_ok(rest):
    """剥掉已确认安全的剩余片段（数字/运算符/括号/x/空格）。"""
    return re.sub(r"[-+*/%(),.\d\s xX]", "", rest)


def expr_hash(specs):
    return hashlib.sha256(
        json.dumps(specs, sort_keys=True, ensure_ascii=False)
        .encode("utf-8")).hexdigest()[:16]


def render(specs, out_path):
    """确定性渲染：numpy 求值 + matplotlib Agg。表达式非法抛 ValueError。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    ns = {"__builtins__": {}}
    ns.update({v: getattr(np, k, k) for k, v in _FUNCS.items()})
    ns["x"] = None
    for bad in ("__", "import", "open", "eval", "exec"):
        for s in specs:
            if bad in str(s.get("expr", "")).lower():
                raise ValueError("非法表达式")

    fig, ax = plt.subplots(figsize=(6.4, 4.8), dpi=100)
    all_x = []
    for s in specs:
        expr = str(s["expr"])
        dom = s.get("domain") or [-5, 5]
        xs = np.linspace(dom[0], dom[1], 800)
        ns["x"] = xs
        try:
            ys = eval(expr.replace("^", "**"), ns)   # noqa: S307 白名单前置
        except Exception as exc:
            plt.close(fig)
            raise ValueError("表达式求值失败 %r: %s" % (expr, exc))
        ys = np.asarray(ys, dtype=float)
        ys = np.where(np.abs(ys) > 1e4, np.nan, ys)   # 渐近线断开而非画穿
        ax.plot(xs, ys, linewidth=1.8, label=str(s.get("label") or expr)[:40])
        all_x.append(dom)
    lo = min(d[0] for d in all_x)
    hi = max(d[1] for d in all_x)
    pad = (hi - lo) * 0.05
    ax.set_xlim(lo - pad, hi + pad)
    ax.relim()
    ax.autoscale_view()
    ax.axhline(0, color="#888", linewidth=0.6)
    ax.axvline(0, color="#888", linewidth=0.6)
    ax.grid(True, alpha=0.3)
    if 1 < len(specs) <= 4:
        ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, format="png")
    plt.close(fig)
    return out_path
