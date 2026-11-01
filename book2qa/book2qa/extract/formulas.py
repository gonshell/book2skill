# -*- coding: utf-8 -*-
"""核心层：latex → plain 文本化（graph-spec §6 规则表 + 变体）。

双轨目的：latex 负责显示（AI 引用），plain 负责检索（学生说"根号2""小于等于"）。
转换失败不静默：latex_to_plain 返回 None，由调用方报 issue（formulas_plain_failed）。

变体实测来源（transform.md §S4）：真实书里出现 \\leqslant、\\forall、`{ \\subseteq }`
（命令前带空格）、`x_{1}`、`\\varphi`——规则表先去命令前空白再匹配。
"""
import re

GREEK = {
    "alpha": "alpha", "beta": "beta", "gamma": "gamma", "delta": "delta",
    "epsilon": "epsilon", "varepsilon": "varepsilon", "zeta": "zeta",
    "eta": "eta", "theta": "theta", "vartheta": "vartheta", "iota": "iota",
    "kappa": "kappa", "lambda": "lambda", "mu": "mu", "nu": "nu",
    "xi": "xi", "omicron": "omicron", "pi": "pi", "rho": "rho",
    "sigma": "sigma", "tau": "tau", "upsilon": "upsilon", "phi": "phi",
    "varphi": "varphi", "chi": "chi", "psi": "psi", "omega": "omega",
    "Delta": "Delta", "Omega": "Omega", "Pi": "Pi", "Phi": "Phi",
}

# 长命令在前防前缀吞并（\leqslant 先于 \le，\infty 先于 \in）——由正则
# 交替 + 排序保证；此处只存映射。
SYMBOLS = {
    "leqslant": "<=", "geqslant": ">=", "subseteq": "包含于",
    "supseteq": "包含", "varnothing": "空集", "forall": "任意",
    "exists": "存在", "rightarrow": "→", "leftrightarrow": "↔",
    "Leftrightarrow": "⇔", "rightarrow": "→", "infty": "无穷",
    "leq": "<=", "geq": ">=", "neq": "!=", "equiv": "≡",
    "times": "×", "div": "÷", "cdot": "·", "pm": "±", "mp": "∓",
    "circ": "°", "prime": "'", "angle": "∠", "perp": "⊥",
    "parallel": "∥", "similar": "∽", "cong": "≌", "approx": "≈",
    "propto": "∝", "because": "因为", "therefore": "所以",
    "in": "属于", "notin": "不属于", "cup": "并", "cap": "交",
    "le": "<=", "ge": ">=", "ne": "!=", "sin": "sin", "cos": "cos",
    "tan": "tan", "cot": "cot", "log": "log", "lg": "lg", "ln": "ln",
    "max": "最大值", "min": "最小值",
    "left": "", "right": "", "quad": " ", "qquad": "  ",
    "limits": "", "displaystyle": "",
}
SYMBOLS.update(GREEK)

CMD_RE = re.compile(r"\\([a-zA-Z]+)")
MATH_RE = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$", re.S)


def _strip_ws_in_braces(s):
    """`{ \\subseteq }` → `{ \\subseteq }`：只吃花括号与命令之间的空白，
    不动正文与命令间的空格（`A \\sin(...)` 必须保留 "A sin"）。"""
    s = re.sub(r"(\{)\s+(\\[a-zA-Z]+)", r"\1\2", s)
    s = re.sub(r"(\\[a-zA-Z]+)\s+(\})", r"\1\2", s)
    return s


def _apply_frac(s):
    """\\frac{A}{B} → A/B；内层先行（[^{}]* 只配最内层），循环到稳定。"""
    pat = re.compile(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
    while True:
        new = pat.sub(lambda m: "%s/%s" % (m.group(1).strip(), m.group(2).strip()), s)
        if new == s:
            return s
        s = new


def _apply_sqrt(s):
    """\\sqrt{X} → 根号X；\\sqrt[n]{X} → n次根号X（[n] 可选）。"""
    pat = re.compile(r"\\sqrt\s*(?:\[([^\[\]]*)\])?\s*\{([^{}]*)\}")
    while True:
        def sub(m):
            n = (m.group(1) or "").strip()
            body = m.group(2).strip()
            return ("%s次根号%s" % (n, body)) if n else ("根号%s" % body)
        new = pat.sub(sub, s)
        if new == s:
            return s
        s = new


def latex_to_plain(latex):
    """latex → plain；括号不平衡返回 None（不许静默）。"""
    if latex is None:
        return None
    s = latex.strip()
    if s.count("{") != s.count("}"):
        return None
    s = _strip_ws_in_braces(s)
    s = _apply_frac(s)
    s = _apply_sqrt(s)
    # 上标/下标去括号：x^{2} → x^2，x_{1} → x_1
    s = re.sub(r"\^\s*\{([^{}]*)\}", r"^\1", s)
    s = re.sub(r"_\s*\{([^{}]*)\}", r"_\1", s)

    def cmd_sub(m):
        name = m.group(1)
        return SYMBOLS.get(name, name)  # 未知命令：去反斜杠留名，不静默丢

    s = CMD_RE.sub(cmd_sub, s)
    s = s.replace("{", "").replace("}", "").replace("$", "")
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s if s else None


def extract_math(text):
    """段内数学环境 → [(latex, plain|None)]。$ 与 $$ 均收。"""
    out = []
    for m in MATH_RE.finditer(text):
        latex = (m.group(1) or m.group(2)).strip()
        if latex:
            out.append((latex, latex_to_plain(latex)))
    return out


def validate_plain(rows):
    """exercises 行内 quote 数学转 plain（双轨落行）；失败行报 issue。

    rows: [dict]，就地补 rows[i]["quote_plain"]。
    返回 issues: [dict]。
    """
    issues = []
    for i, r in enumerate(rows):
        quote = r.get("quote") or ""
        segs = extract_math(quote)
        if not segs:
            continue
        plain = quote
        failed = False
        for latex, p in segs:
            if p is None:
                failed = True
                continue
            plain = plain.replace("$%s$" % latex, p).replace("$%s$" % latex, p)
        if failed:
            issues.append({"code": "formulas_plain_failed", "row": i,
                           "label": r.get("label", ""),
                           "detail": "quote 内公式转换失败：%s" %
                                     [l for l, p in segs if p is None][:3]})
        else:
            r["quote_plain"] = re.sub(r"\s+", " ", plain).strip()
    return issues
