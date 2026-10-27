# -*- coding: utf-8 -*-
"""markdown 公式/标点误识修复（A 档：安全规则批量修复）。

修复规则（按顺序执行，每步独立计数）：
  S1  正文汉字间英文标点 → 中文标点（. , : ; 四种，公式段占位保护）
  S2  公式内数学符号误识成汉字 → 正确符号（一→-, 十→+, 上/丄/丿→⊥, 空→∽,
      业→∥, 区→⊥, 二→⊆, 亿→⊆, 夆→∩, 互→∥）
  S2b \\mathrm{单符号} 解包（OCR 把运算符塞进 \\mathrm{}）
  S3  纯中文公式解包（$式$ → 式，$甘心$ → 甘心）
  S4  连接词/介词误入公式拆分（$A 与 B$ → $A$ 与 $B$）
  S4b 拆分后新产生的纯中文公式再解包一轮
  S5  单位类文本精确修复（$4\\ 200 元 / m ^2$ → $4\\ 200$ 元/m^2 等 8 条）
  S6  公式尾孤立标点移出公式外（$\\mathbf { R } .$ → $\\mathbf { R }$。）
      跳过：跨行未闭合 \\left、\\right./\\left. 结尾、\\cdots 类结尾
  S10 定点修复：逐册精确串替换（事件定义引号垃圾、游离 $$、\\mathcal{X/Y/O}、
      厂/口→□、PM2.5 下标等）+ 整行重写（OCR 搅碎的行）+ 批量正则
  S12 内容级修复：水印图移除（图存在但图里无内容）、HTML 表格转 Markdown、
      HTML 标签泄漏清理、数学区 HTML 实体还原、表内 img 路径错位重映射
  S13 排版层修复：思考框问号标题归一、标题前 emoji 图标清理
  S15 页边图标清理：习题类别/思考问号/探究图标（47-72px 装饰小图，信息由标题承载）
  S16 结构性损坏公式降级：不可还原的 OCR 垃圾（嵌套 \\textcircled、命令截断、
      空 array 嵌套）→ 显式占位 + 原串清单（broken_formulas.tsv）；同时安全修复
      数字被 \\; 拆散、裸 ^ 无基底等形态
  S7  清理行内公式的历史残留 alt 注释（合法 alt 前一行必是 $$）
  S8  删除全部 alt → add_formula_alt 重生（与修复后公式同步）

B 档（不自动修，输出清单）: 剩余公式内嵌中文（事件定义引号、aligned 环境中文等）
"""

# ------------------------------------------------------------- 搬迁说明（2026-10-24）
# 搬迁自 gzsx-md/fix_md.py，行为保持型参数化（docs/conventions.md 附录 A）：
#   1) 移除 sys.stdout 包装与 sys.path 注入（stdout 归 CLI 的 JSON 信封；改包内相对导入）
#   2) ROOT/FINAL/final_backup 常量 → run(source_dir, output_dir) 参数注入
#   3) s12/s15 增加 imgdir 形参（原由全局 FINAL 推导）
#   4) S1–S20 规则本体（四元组/正则/TARGETED 串）逐字未动
import os, re, shutil, sys
from html.parser import HTMLParser

from .reporting import add_formula_alt  # 搬迁自 postprocess.py → engine/reporting.py


def _quarantine_image(fp, imgdir, qroot):
    """裁片文件处理：配了隔离根则移入隔离区（rename，可回溯），否则删除。

    隔离而非 unlink 的三个理由：
      1) 受保护环境（企业安全策略 / EDR / safe-delete 钩子）会拦截批量 unlink，
         引擎会在 S15 中途被打断——move 语义不触发此类策略；
      2) 跨学科阈值误伤可回溯（如化学书图标密度高于数学书，<100px 判定会误删）；
      3) 符合项目"不删用户文件"纪律：清掉的裁片留档，供人工复核。
    """
    if qroot and imgdir:
        try:
            os.makedirs(qroot, exist_ok=True)
            base, ext = os.path.splitext(os.path.basename(fp))
            dest = os.path.join(qroot, base + ext)
            # 重跑时同名冲突必须换名，不能让 move 走到覆盖分支：
            # Windows 上 move 到已存在文件会抛 OSError → 回退 os.remove → 触发批量删除拦截
            i = 1
            while os.path.exists(dest):
                dest = os.path.join(qroot, "%s-%d%s" % (base, i, ext))
                i += 1
            shutil.move(fp, dest)
            return
        except OSError as e:
            print("    [隔离失败转删除] %s: %s" % (os.path.basename(fp), e))
    os.remove(fp)

# 原全局常量 ROOT/FINAL 已参数化（run(source_dir, output_dir)）；BOOKS 为默认册序（数据）
BOOKS = ["选择性必修第三册", "选择性必修第二册", "选择性必修第一册", "必修第二册", "必修第一册"]
HAN = "\u4e00-\u9fa5"
NB = "(?<![" + HAN + "])"   # 前非汉字
NA = "(?![" + HAN + "])"    # 后非汉字


# ---------------- S1: 正文汉字间英文标点 ----------------
def s1(md):
    slots = []
    def protect(m):
        slots.append(m.group(0))
        return "\x00%d\x00" % (len(slots) - 1)
    prose = re.sub(r"\$[^$\n]+\$", protect, md)
    total = 0
    PUNCT = [(".", "\u3002"), (",", "\uff0c"), (":", "\uff1a"), (";", "\uff1b"),
             ("?", "\uff1f"), ("!", "\uff01")]
    for a, c in PUNCT:
        # 形态A: 汉字间英文标点（仅限同行——[ \t]* 不可跨换行，
        # 否则 "解.\n\n逻辑用语是……" 会被吞成一段，段落空行全丢）
        pat = re.compile("(?<=[" + HAN + "])[ \t]*" + re.escape(a) + r"[ \t]*(?=[" + HAN + "])")
        prose, n = pat.subn(c, prose)
        total += n
    for a, c in PUNCT:
        # 形态B: 汉字后接行尾英文标点（句读在行尾，后接换行或文件结束；
        # 负向预查跳过 "……" 省略号，避免把省略号首点改成句号）
        pat = re.compile("(?<=[" + HAN + "])[ \t]*" + re.escape(a) +
                         r"(?![.,;:!?])[ \t]*(?=\n|$)")
        prose, n = pat.subn(c, prose)
        total += n
    md = re.sub(r"\x00(\d+)\x00", lambda m: slots[int(m.group(1))], prose)
    return md, total


# ---------------- S2: 公式内符号误识 ----------------
SYM_FIX = [
    ("\u4e00", "-"), ("\u5341", "+"),                       # 一→减号, 十→加号
    ("\u4e0a", r"\perp"), ("\u4e04", r"\perp"), ("\u4e3f", r"\perp"),  # 上/丄/丿→⊥
    ("\u7a7a", r"\sim"), ("\u4e1a", r"\parallel"), ("\u533a", r"\perp"),  # 空→∽, 业→∥, 区→⊥
    ("\u4e8c", r"\subseteq"), ("\u4ebf", r"\subset"),       # 二→⊆, 亿→⊆
    ("\u5906", r"\cap"), ("\u4e92", r"\parallel"),          # 夆→∩, 互→∥
]

def s2(md):
    cnt = [0]
    def fix(m):
        inner = m.group(1)
        new = inner
        for ch, rep in SYM_FIX:
            new = re.sub(NB + ch + NA, lambda _, r=rep: r, new)
        if new != inner:
            cnt[0] += 1
        return "$" + new + "$"
    return re.sub(r"\$([^$\n]+)\$", fix, md), cnt[0]


# ---------------- S2b: \mathrm{单符号} 解包 ----------------
def _unpack_mathm(m):
    ch = m.group(1)
    if ch == "\u4e00":
        return "-"
    if ch == "\u5341":
        return "+"
    return ch


def s2b(md):
    n = 0
    # \mathrm{;} \mathrm{,} 等：OCR 把运算符塞进 \mathrm{}
    new, k = re.subn(r"\\mathrm\s*\{\s*([+\-<>=;:,])\s*\}", r"\1", md)
    n += k
    # \mathrm{~-} \mathrm{~一} \mathrm{~十}：运算符被识别成 ~X 塞进 \mathrm{}
    new, k = re.subn(r"\\mathrm\s*\{\s*~\s*([+\-\u4e00\u5341])\s*\}", _unpack_mathm, new)
    n += k
    return new, n


# ---------------- S3: 纯中文公式解包 ----------------
def s3(md):
    cnt = [0]
    def fix(m):
        inner = m.group(1)
        # 纯中文+标点（含全角），或纯标点（$。$/$,$ 等误识）
        if re.fullmatch(r"[\s" + HAN + r",.;:\uff0c\u3002\uff1b\uff1a]*", inner) and \
           (re.search("[" + HAN + "]", inner) or re.search("[\u3002\uff0c\uff1b\uff1a]", inner)):
            txt = inner.strip()
            txt = txt.replace(",", "\uff0c").replace(".", "\u3002")
            txt = txt.replace(";", "\uff1b").replace(":", "\uff1a")
            txt = re.sub(r"\s+", "", txt)
            if txt:
                cnt[0] += 1
                return txt
        return m.group(0)
    return re.sub(r"\$([^$\n]+)\$", fix, md), cnt[0]


# ---------------- S9: 伪块公式解包（OCR 把正文段误标为 $$ 块公式） ----------------
MATH_CMD = re.compile(
    r"\\(frac|sum|int|sqrt|left|right|begin|end|prod|lim|overrightarrow|overline"
    r"|hat|bar|vec|cdot|times|div|leq|geq|neq|approx|in|notin|subset|cup|cap"
    r"|emptyset|infty|pm|ldots|cdots|alpha|beta|pi|theta|lambda|mu|omega|Delta"
    r"|Sigma|text|mathrm|mathbf|boldsymbol|mathit|mathcal|quad|therefore|dot)")

def s9(md):
    """伪块公式解包：OCR 把"正文句子(+裸露公式行)"误标为 $$ 块公式。

    判据（逐行）：块内任一行在剥离行内 $...$/图片/HTML 后，
    汉字>=6 且无裸露 LaTeX 痕迹（\\命令/_{/^{/竖线）→ 该行是纯正文句 → 整块解包。
    合法块公式（纯公式行、\\frac{中文}{中文} 公式）不含纯正文行，不受影响。
    解包时删 $$ 对与紧随的历史 alt 行；块内裸露公式行原样保留在正文中。
    """
    lines = md.split("\n")
    out, n = [], 0
    i = 0
    while i < len(lines):
        if lines[i].strip() == "$$":
            j = i + 1
            while j < len(lines) and lines[j].strip() != "$$":
                j += 1
            if j >= len(lines):
                out.append(lines[i])
                i += 1
                continue
            body_lines = lines[i + 1:j]
            is_pseudo = False
            for bl in body_lines:
                prose = re.sub(r"\$[^$\n]+\$", "", bl)
                prose = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", prose)
                prose = re.sub(r"<[^>]+>", "", prose)
                han = len(re.findall("[" + HAN + "]", prose))
                bare = re.search(r"\\[a-zA-Z{}]|[_^]\{|\|", prose)
                if han >= 6 and not bare:
                    is_pseudo = True
                    break
            if is_pseudo:
                out.extend(body_lines)
                n += 1
                k = j + 1
                if k < len(lines) and lines[k].strip().startswith("<!-- alt:"):
                    k += 1
                i = k
                continue
            out.extend(lines[i:j + 1])
            i = j + 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out), n


# ---------------- S4: 连接词/介词误入公式拆分 ----------------
WORDS = "\u4e0e\u6216\u53ca\u4e14\u5373\u548c\u5728\u662f\u7531\u53ef\u793a\u91cf\u5fc3\u4e2d\u6c42\u4e8e"
# 与 或 及 且 即 和 在 是 由 可 示 量 心 中 求 于
SP = r"(?:\\ |[ \t]+)"   # 公式内空格或 \ 空格

def _split_inner(s):
    """对单个公式的内容（不含 $ 与换行）做连接词拆分，返回替换文本；无需拆分返回 None。

    必须先锁定公式边界再拆分：早期版本直接用 $...$ 模式匹配全文，
    会从公式 A 的闭合 $ 匹配到公式 B 的开放 $，把公式间正文当公式内容，
    产生游离 $；形态4 的中文组含 \\s 还会跨行吞掉空行甚至 $$ 标记。
    """
    # 形态4: 词后紧跟汉字（无空格） A 词汉字... → $A$ 词汉字...
    m = re.fullmatch(r"(.+?)" + SP + "([" + WORDS + r"])([\u4e00-\u9fa5][\u4e00-\u9fa5\s.,;:]*?)", s)
    if m:
        rest = m.group(3).strip()
        for a, c in [(".", "\u3002"), (",", "\uff0c"), (":", "\uff1a"), (";", "\uff1b")]:
            rest = rest.replace(a, c)
        rest = re.sub(r"\s*([\u3002\uff0c\uff1b\uff1a])", r"\1", rest)  # 去中文标点前空格
        return "$" + m.group(1).rstrip() + "$ " + m.group(2) + rest
    # 形态1: 词在中间  A 词 B → $A$ 词 $B$
    m = re.fullmatch(r"(.+?)" + SP + "([" + WORDS + "])" + SP + r"(.+)", s)
    if m:
        return "$" + m.group(1).rstrip() + "$ " + m.group(2) + " $" + m.group(3).lstrip() + "$"
    # 形态2: 词在开头  词 B → 词 $B$
    m = re.fullmatch(r"([" + WORDS + "])" + SP + r"(.+)", s)
    if m:
        return m.group(1) + " $" + m.group(2).lstrip() + "$"
    # 形态3: 词在结尾  A 词 → $A$ 词
    m = re.fullmatch(r"(.+?)" + SP + "([" + WORDS + r"])", s)
    if m:
        return "$" + m.group(1).rstrip() + "$ " + m.group(2)
    return None

def s4(md):
    total = 0
    for _ in range(6):  # 循环直到无新拆分（一条公式可能含多个词）
        round_n = [0]

        def fix(m):
            new = _split_inner(m.group(1))
            if new is None:
                return m.group(0)
            round_n[0] += 1
            return new
        # 外层正则锁定公式边界（$...$ 非重叠、不跨行），只在公式内容内拆分
        md = re.sub(r"\$([^$\n]+)\$", fix, md)

        total += round_n[0]
        if round_n[0] == 0:
            break
    return md, total


# ---------------- S5: 单位类精确修复 ----------------
UNIT_FIXES = [
    (r"$4\ 200 元 / m ^2$", r"$4\ 200$ 元/m^2"),
    (r"$80  元/m ^2$", r"$80$ 元/m^2"),
    (r"$P_{1} / 万元$", r"$P_{1}$/万元"),
    (r"$P_{2} / 万元$", r"$P_{2}$/万元"),
    (r"$z  元 ,$", r"$z$ 元，"),
    (r"$位 : C$", r"单位: ℃"),
    (r"$位: \mathrm{m/s})$", r"单位: m/s)"),
    (r"$( 单位: m)$", r"(单位: m)"),
]

def s5(md):
    total = 0
    for old, new in UNIT_FIXES:
        if old in md:
            md = md.replace(old, new)
            total += 1
    return md, total


# ---------------- S6: 公式尾孤立标点移出 ----------------
def s6(md):
    cnt = [0]
    CN = {".": "\u3002", ",": "\uff0c", ":": "\uff1a", ";": "\uff1b"}
    def fix(m):
        inner, p = m.group(1), m.group(2)
        s = inner.rstrip()
        # 跳过跨行未闭合 \left ... \right
        if len(re.findall(r"\\left\b", s)) > len(re.findall(r"\\right\b", s)):
            return m.group(0)
        if s.endswith("\\right") or s.endswith("\\left"):
            return m.group(0)  # \right. / \left. 隐形定界符的点不是标点
        if re.search(r"(ldots|cdots|dots|vdots|dot|quad|prime)$", s):
            return m.group(0)
        new_inner = re.sub(r"\s*" + re.escape(p) + r"$", "", inner).rstrip()
        if not new_inner:
            return m.group(0)
        cnt[0] += 1
        return "$" + new_inner + "$" + CN[p]
    return re.sub(r"\$([^$\n]*?)[ \t]*([.,;:])[ \t]*\$", fix, md), cnt[0]


# ---------------- S7: 清理行内公式的历史残留 alt ----------------
def s7(md):
    lines = md.split("\n")
    out, removed = [], 0
    for i, ln in enumerate(lines):
        if ln.strip().startswith("<!-- alt:"):
            prev = lines[i - 1].strip() if i > 0 else ""
            if prev != "$$":
                removed += 1
                continue
        out.append(ln)
    return "\n".join(out), removed


# ---------------- S8: alt 重生 ----------------
# ---------------- S10: 定点修复（逐册精确串 + 批量误识模式） ----------------
# 说明：TARGETED 的 key 是册名，value 是 [(旧串, 新串), ...]。
# 每条旧串在所在册中必须恰好出现 1 次，否则报错（防止文档变动后静默失配）。

TARGETED = {
    "必修第一册": [
        # L2056 相似三角形：$$\triangle ACD$ $\mathcal{O}\triangle DCB$ → 单个公式
        ("可证 $$\\triangle ACD$ $\\mathcal { O } \\triangle D C B$，",
         "可证 $\\triangle ACD \\sim \\triangle D C B$，"),
        # L2056 后半：CD = \sqrt{ab} 缺左 $（S10 修好前段后暴露）
        ("，因而CD = \\sqrt{ab}$ .由于CD小于或等于圆的半径",
         "，因而$CD = \\sqrt{ab}$。由于CD小于或等于圆的半径"),
        # L4506 表头重建：√2 不足/过剩近似值 x/y
        ("| 的不足近似值■$\\sqrt{2}$$x$ | 5的近似值 | "
         "$\\sqrt { 2 }$的过剩近似值$\\mathcal { Y }$ | $5 ^ { y }$的近似值 |",
         "| $\\sqrt { 2 }$的不足近似值$x$ | $5^x$的近似值 | "
         "$\\sqrt { 2 }$的过剩近似值$y$ | $5 ^ { y }$的近似值 |"),
        # L4502 5^x / 5^y 的 ^ 丢失
        ("计算相应的$5 x$ $5 y$ 的近似值", "计算相应的$5^x$，$5^y$的近似值"),
        # L4519 5^y 的 ^ 丢失 + 数列中的 "9" 实为逗号
        ("$5^{x}$ 和 $5 y$ 都趋向于同一个数", "$5^{x}$ 和 $5^y$ 都趋向于同一个数"),
        ("5^{1.41}$ 9 51.414，51.4142", "5^{1.41}$，$5^{1.414}$，$5^{1.4142}$"),
        # L5611 表格：\mathcal{X}→x，去掉游离下划线
        ("| $\\mathcal { X }$ | $y = 2^{x}$ | _$y = 2x$ |",
         "| $x$ | $y = 2^{x}$ | $y = 2x$ |"),
        # L9268 游离 $$：试以 $$\mathrm{cos}\alpha$表示
        ("试以 $$\\mathrm { { \\bf ~ c o s } } ~ \\alpha$表示",
         "试以 $\\mathrm { { \\bf ~ c o s } } ~ \\alpha$表示"),
        # L9268 后半：\sin^2... 缺左 $
        ("~ \\alpha$表示\\sin ^{2}\\frac{\\alpha }{2}",
         "~ \\alpha$表示$\\sin ^{2}\\frac{\\alpha }{2}"),
        # L3173 \left\{ … \right. 缺右花括号
        ("$\\left\\{ x \\mid -3 \\leqslant x \\leqslant 8 \\right.$",
         "$\\left\\{ x \\mid -3 \\leqslant x \\leqslant 8 \\right\\}$"),
        # L5971 二分法步骤4：aligned 中文垃圾 + ,则→，则
        ("4. 判断是否达到精确度 $\\begin{aligned} & 也 ,\\\\ & 也 ,\\\\ \\end{aligned}$ "
         "若 $| a - b | < \\varepsilon$ ,则得到零点近似值 $a$ (或b)；否则重复步骤 $2 \\sim 4$",
         "4. 判断是否达到精确度：若 $| a - b | < \\varepsilon$，则得到零点近似值 "
         "$a$ (或b)；否则重复步骤 $2 \\sim 4$"),
        # L9671 / L9691 时间单位 S → s
        ("$\\mathcal { X } \\mathrm { ~ S ~ }$， ，那么",
         "$x\\ \\mathrm{s}$，那么"),
        ("$\\mathcal { X } _ { 1 } \\mathrm { ~ S ~ }$当 $\\omega = 2$",
         "$x _ { 1 }\\ \\mathrm{s}$，当 $\\omega = 2$"),
        ("$\\mathcal { X } _ { 2 } \\mathbb { S }$。",
         "$x _ { 2 }\\ \\mathrm{s}$。"),
        # L7215 正弦记号：乏 → y
        ("锐角x的正弦记为 $乏 _1$", "锐角x的正弦记为 $y _ { 1 }$"),
        # L2264 公式头冒号跑进公式
        ("求证$：\\left( x + y \\right)\\left( y + z \\right)\\left( z + x \\right) "
         "\\geqslant 8xyz.$",
         "求证：$\\left( x + y \\right)\\left( y + z \\right)\\left( z + x \\right) "
         "\\geqslant 8xyz$。"),
        # L9520 提示公式头冒号 + 尾句号
        ("（提示$：\\beta = ( \\alpha + \\beta ) - \\alpha.$",
         "（提示：$\\beta = ( \\alpha + \\beta ) - \\alpha$"),
        # L6833 连同-32°角
        ("连同一 $: 3 2 ^ { \\circ }$ 角在内", "连同 $-32^{\\circ}$ 角在内"),
        # L10180 公式尾句号
        ("+\\frac{1}{4}\\sin 4x+\\cdots.$", "+\\frac{1}{4}\\sin 4x+\\cdots$"),
        # L2684 恩格尔系数公式断行：$) 跑到公式外
        ("恩格尔系数 $r(r=\\frac{ 食物支出金额 }{ 总支出金额 }\\times$ 100%)反映",
         "恩格尔系数 $r\\left(r=\\frac{ 食物支出金额 }{ 总支出金额 }\\times 100\\%\\right)$ 反映"),
        # L2830 集合描述：中文连接词在公式内（教科书原样，保留）
        # L6078 人口数据：句号+逗号重复垃圾
        ("$t = 1, 2, \\cdots, 8$。 ，由", "$t=1,2,\\cdots,8$，由"),
        # L9942 公式尾分号垃圾
        ("$t = \\frac{1}{600}$ 时， ； $i = 5$", "$t=\\frac{1}{600}$ 时，$i=5$"),
        # ===== S11：用户截图报告轮（2026-10-22）=====
        # L95 数集表：正整数集记号 N_+ 被 OCR 识成 N_{中}
        ("$\\mathbf{N}_{$ 中 $}$", "$\\mathbf{N}_{+}$"),
        # L229 练习2题头：∉ 被 OCR 识成 \oint（环积分，高中教材不应出现）
        ("2. 用符号 $\\text{\" } \\in  \\text{\" }$ 或 $\\text{\" } \\oint  \\text{\" }$ 填空：",
         "2. 用符号“∈”或“∉”填空："),
        # L247 习题1.1题头：统一为纯文本符号（原 $“\in “$ 数学包裹冗余）
        ("1. 用符号 $\\text{\" }\\in  \\text{\" }$ 或“∉”填空：",
         "1. 用符号“∈”或“∉”填空："),
        # L612 补集记号：∁_U 被 OCR 识成 \int_{U}（积分号）
        ("记作 $\\int_{U} A$", "记作 $\\complement _ { U } A$"),
        # L615 补集定义：\mathbb{C}_{U}A → \complement _ { U } A（与全文 14 处惯例一致）
        ("\\mathbb{C}_{U}A = \\{ x \\mid x \\in U,   且   x \\notin A \\},",
         "\\complement _ { U } A = \\{ x \\mid x \\in U,   且   x \\notin A \\},"),
        # ===== S12：截图报告第二轮 =====
        # L2711 定义域解：且 把集合描述拦腰拆断 + \left[ \left[ 双括号垃圾
        ("= \\left\\{ x \\mid x \\geqslant - 3,$ 且 $x \\neq - 2 \\right\\}$即 "
         "$\\left[ \\left[ - 3 , - 2 \\right) \\cup \\left( - 2 , + \\infty \\right) \\right.$ .",
         "= \\left\\{ x \\mid x \\geqslant - 3, 且 x \\neq - 2 \\right\\}$，即 "
         "$\\left[ - 3, - 2 \\right) \\cup \\left( - 2, + \\infty \\right)$."),
        # ===== S14：排版二期（题项合并行拆分 + 图注归位，逐条人工核实） =====
        # L3172 习题3.1：题4与题5合并一行；“问”被 OCR 成 9
        ("的值. 5. 已知函数", "的值。\n\n5. 已知函数"),
        ("； 9（1）点（3，14）", "，问：（1）点（3，14）"),
        # L6655 习题3.2：题11/12/13 三题合并一行，夹带 OCR 垃圾 Y32、游离 1 和 0
        ("并说明理由. 12.对于函数", "并说明理由。\n\n12.对于函数"),
        ("$ Y32 (1) 探索", "$，(1) 探索"),
        ("为奇函数? 1 13.如图", "为奇函数？\n\n13.如图"),
        ("直线段AB 构成. 0 (1) 写出", "直线段AB 构成，(1) 写出"),
        # L7508 习题5.1：题2与题3合并一行
        ("哪些有可能取负值？3. 确定", "哪些有可能取负值？\n\n3. 确定"),
        # L9602 习题5.5：题2/3/4 三题合并一行；提示括号未闭合
        ("- \\alpha$ 3. 已知", "- \\alpha$）\n\n3. 已知"),
        ("求 $\\cos \\alpha$ 的值. 4. 在", "求 $\\cos \\alpha$ 的值。\n\n4. 在"),
        # L9624 复习参考题5：题13与题14合并一行
        ("求 $\\angle C$， 14. 在", "求 $\\angle C$。\n\n14. 在"),
        # 图5.6-3：图（page_444_image_2）与图注分离 11 行，注归位到图后
        ("![](images/page_444_image_2.jpg)\n\n所以，盛水筒M距离水面的高度H与时间t的关系是",
         "![](images/page_444_image_2.jpg)\n\n图5.6-3\n\n所以，盛水筒M距离水面的高度H与时间t的关系是"),
        ("我们可以只研究函数①的性质\n\n图5.6-3\n\n## 5.6.2",
         "我们可以只研究函数①的性质\n\n## 5.6.2"),
        # ===== S16：KaTeX 预渲染暴露的公式级错误（md2html 构建期验证） =====
        # L330 集合包含于：OCR 把右括号啃成 ^\infty（A包含于B，不是 B 的无穷次方）
        ("读作“A包含于 $B^{\\infty}$ (或“B包含 $A^{\\infty}$ ).",
         "读作“A包含于 $B$（或B包含 $A$）."),
        # L6501 对数引入：公式被 \ 截断 + \$ 转义美元符（KaTeX 不接受行尾裸 \）
        ("在 $a^{x}=N\\ (a>0,\\$ 且 $\\ a\\neq1)$ 中",
         "在 $a^{x}=N$（$a>0$，且 $a \\neq 1$）中"),
        # L6634 茶水温度：\text 内嵌 ^{ 上标（KaTeX 的 text 模式不允许上标）
        ("$8 5 \\text { ^ { \\circ } C }$", "$85^{\\circ}\\mathrm{C}$"),
        # L355 真包含于：OCR 把引号啃成上标垃圾（^{64}=左引号、^{a}=右引号、\bullet/\rightarrow）
        ("读作 $^ { 6 4 } A$ 真包含于 $B^{\\bullet}$ (或 $^ { a } B$ 真包含 $A^{\\rightarrow}$",
         "读作“A真包含于B”（或“B真包含A”）"),
        # L520 交集读法：$B^{$ 与 $} )$ 是被拦腰拆断的公式（KaTeX 报未闭合）
        ("(读作 $^ { 4 4 } A$ 交 $B^{$ 中 $} )$", "（读作“A交B”）"),
        # ===== S18：texmath 渲染规则实测暴露的问题 =====
        # （scan_md_preview.py 复刻 markdown-it-texmath dollars 规则：
        #  $ 后带空格不算公式；闭 $ 前/后紧跟数字不算公式）
        # L1081：$ 后带空格 → texmath 判为非公式，预览显示裸 LaTeX
        ("那么 $. \\triangle ABC$ 为直角三角形", "那么 $\\triangle ABC$ 为直角三角形"),
        # L1131：\\boldsymbol{i} 实为 r 的误识；后半段公式被 OCR 拆碎
        # （$r_{1}$ ,r2，r3$，r _ { 4 }$ 中闭 $ 前是数字 3，texmath 跳过）
        ("记 $\\boldsymbol{i} \\boldsymbol{r}_{1}$", "记 $r_{1}$"),
        ("即 $r_{1}$ ,r2，r3$，r _ { 4 }$ 分别给出了",
         "即 $r_{1}, r_{2}, r_{3}, r_{4}$ 分别给出了"),
        # L4502：过剩近似值数列，OCR 把 5^{1.42} 等啃成 ,51.42, 51.415$
        ("$5^{1.5}$ ,51.42, 51.415$，5^{1.414\\;3}$",
         "$5^{1.5}$，$5^{1.42}$，$5^{1.415}$，$5^{1.414\\;3}$"),
        # L4895：小数点被 OCR 啃成 $。，闭 $ 前是数字 0 → texmath 跳过
        ("所以0$。8^{-\\sqrt{2}} < 0.8^{-\\sqrt{3}}$",
         "所以 $0.8^{-\\sqrt{2}} < 0.8^{-\\sqrt{3}}$"),
        # L6281：同上，1$。002^{x_{0}} = 5$
        ("满足1$。002^{x_{0}} = 5$", "满足 $1.002^{x_{0}} = 5$"),
        # L6675：数据值被包进公式，,x=6$ 的闭 $ 前是数字 6 → texmath 跳过
        ("$\\omega = \\frac{\\pi}{8}$ ,x=6$，y = 10$ 代入①式",
         "$\\omega = \\frac{\\pi}{8}$，x=6，y=10 代入①式"),
        # 表5.7-3 港口水深：时刻行被 OCR 啃坏（冒号→。/；/：，小时数包进公式，
        # 闭 $ 后紧跟数字使 texmath 规则作废）。原书为 0:00~23:00，多源核对一致；
        # \\mathrm{T}_{2}=1、Z_{2}=2 系 OCR 垃圾
        ("| 时刻 | $0$。00 | $\\mathrm{T}_{2}$00 | $Z_{2}$00 | $3$；00 | $4 \\cdot$00 | $5$：00 | $6$：00 | $7$。00 | $8$。00 | 9:00 | 10:00 | 11:00 |",
         "| 时刻 | 0:00 | 1:00 | 2:00 | 3:00 | 4:00 | 5:00 | 6:00 | 7:00 | 8:00 | 9:00 | 10:00 | 11:00 |"),
        ("| 时刻 | $12$；00 | 13:00 | 14:00 | 15:00 | 16:00 | $1 7$；00 | 18:00 | 19:00 | 20:00 | 21:00 | 22:00 | 23:00 |",
         "| 时刻 | 12:00 | 13:00 | 14:00 | 15:00 | 16:00 | 17:00 | 18:00 | 19:00 | 20:00 | 21:00 | 22:00 | 23:00 |"),
        ("| 水深$/ \\mathrm { m }$ | 5.000 | 6.213", "| 水深/m | 5.000 | 6.213"),
        # L757：⑥ 被啃成上标垃圾 $3 ^ { \\textcircled { 6 } }$
        ("先填上 $3 ^ { \\textcircled { 6 } }$", "先填上⑥"),
        # L7454 练习4：①~⑥ 编号三种形态混用（\\textcircled{l}、裸 2/3/4、\\textcircled{⑤}）
        ("对于 $\\textcircled{l} \\sin \\theta > 0$ $2\\sin\\theta<0$ $3\\cos \\theta > 0$ "
         "$4\\cos\\theta<0$ $\\textcircled{5}  \\tan \\theta > 0$ 与 $\\textcircled{6}  "
         "\\tan \\theta < 0$ ，选择恰当的关系式序号填空：",
         "对于 ①$\\sin \\theta > 0$ ②$\\sin\\theta<0$ ③$\\cos \\theta > 0$ "
         "④$\\cos\\theta<0$ ⑤$\\tan \\theta > 0$ 与 ⑥$\\tan \\theta < 0$ ，"
         "选择恰当的关系式序号填空："),
        # ===== S20：C 档清理（用户批准，逐条有出处） =====
        # L2791 区间记法：引号被啃成 ^{66}\bigcirc^{99}；正负号被啃成空分式
        # （下一句"读作正无穷大"互证 ±∞）
        ("$^ { 6 6 } \\bigcirc \\bigcirc ^ { 9 9 }$", "“”"),
        ("$\\frac{\\infty}{} \\frac{\\infty}{}$", "$-\\infty$ 和 $+\\infty$"),
        ("$\\text{\" } + \\infty  \\text{\" }$", "“$+\\infty$”"),
        # L891 思考框：空基座+9 上标纯垃圾，卡在两句之间 → 删除（含前导空格）
        (" $\\overset{9}{\\underset{\\bullet}{}}$", ""),
        # 表3.1-2 区间表"数轴表示"列：4 行全被 OCR 打崩。按表格正上方的约定重建
        # （实心点=含端点、空心点=不含端点）：[a,b]●● (a,b)○○ [a,b)●○ (a,b]○●
        ("| $[ a , b ]$ | $\\longleftarrow$a |", "| $[ a , b ]$ | a ●————● b |"),
        ("| $(a, b)$ | o $\\overset { \\rightharpoonup } { b }$a |",
         "| $(a, b)$ | a ○————○ b |"),
        ("| $[ a , b )$ | $\\overset { \\circ } { b }$a |", "| $[ a , b )$ | a ●————○ b |"),
        ("| $(a, b]$ | O $\\xrightarrow{\\quad}$a |", "| $(a, b]$ | a ○————● b |"),
        # 公式内引号：$\text{" }p\Rightarrow q \text{" }$ → “$p\Rightarrow q$”
        ("$\\text{\" }p\\Rightarrow q \\text{\" }$", "“$p\\Rightarrow q$”"),
    ],
    "必修第二册": [
        # L513 例4：整行重写（70 层 \begin{aligned} 垃圾），见 REWRITE
        # L555 练习2：还原为块公式
        ("2. 填空:$$\\overrightarrow { A B } - \\overrightarrow { A D } \\colon$$ "
         "$\\overrightarrow{BA}-\\overrightarrow{BC}=$ $\\overrightarrow{BC}-\\overrightarrow{BA}=$ "
         "$\\overrightarrow{OD}-\\overrightarrow{OA}=$ $\\overrightarrow{OA}-\\overrightarrow{OB}=$",
         "2. 填空：\n\n$$\n\\begin{array}{l}\n"
         "\\overrightarrow { A B } - \\overrightarrow { A D } = \\quad ; "
         "\\overrightarrow { B A } - \\overrightarrow { B C } = \\quad ; "
         "\\overrightarrow { B C } - \\overrightarrow { B A } = \\quad ; \\\\\n"
         "\\overrightarrow { O D } - \\overrightarrow { O A } = \\underline {{\\quad}}; "
         "\\overrightarrow { O A } - \\overrightarrow { O B } = \\underline {{\\quad}}. \\\\\n"
         "\\end{array}\n$$"),
        # L1079 引号误入公式 + 游离 $$ + 游离 R
        ("c表示“向北走 $1 0  km  ''$ ，d表示“向南走 $5\\  km  ^{\\prime\\prime}$ ，",
         "c表示“向北走 $1 0\\ \\mathrm{km}$”，d表示“向南走 $5\\ \\mathrm{km}$”，"),
        ("； R (4) $$\\pmb { b } \\pmb { + } \\pmb { d }$ ;$ (5)",
         "； (4) $\\pmb { b } \\pmb { + } \\pmb { d }$; (5)"),
        # L1144 游离 $$ + 双分号
        ("(1) $$\\overrightarrow { A D } { = } \\overrightarrow { B C }$；$ (2)",
         "(1) $\\overrightarrow { A D } { = } \\overrightarrow { B C }$； (2)"),
        ("\\overrightarrow{BC}$； ; (3)", "\\overrightarrow{BC}$； (3)"),
        # L2837 游离 $$
        ("若 $$\\overrightarrow{AC}{=}\\overrightarrow{AB}{+}\\overrightarrow{AD}$$ ，则",
         "若 $\\overrightarrow{AC}{=}\\overrightarrow{AB}{+}\\overrightarrow{AD}$，则"),
        # L2903 直线 $$l$ 与 $\triangle ABC$$
        ("直线 $$l$  与 $\\triangle ABC$$ 的边AB",
         "直线 $l$ 与 $\\triangle ABC$ 的边AB"),
        # L3841 欧拉公式：游离 $$ + isin→i\sin + 第(2)题漏 i
        ("(1) $$\\mathrm { c o s } ~ \\pi + \\mathrm { i s i n } ~ \\pi$；$ (2) "
         "$6 \\left( \\cos \\frac{11\\pi}{6} + \\sin \\frac{11\\pi}{6} \\right)$",
         "(1) $\\mathrm { c o s } ~ \\pi + \\mathrm { i } \\sin ~ \\pi$； (2) "
         "$6 \\left( \\cos \\frac{11\\pi}{6} + \\mathrm { i } \\sin \\frac{11\\pi}{6} \\right)$"),
        # L5845 行尾游离 $$
        ("求证: $$\\triangle ABC  \\sim  \\triangle A^{\\prime}B^{\\prime}C^{\\prime}$$",
         "求证: $\\triangle ABC  \\sim  \\triangle A^{\\prime}B^{\\prime}C^{\\prime}$"),
        # L10650 指数函数条件 + 空集符号
        ("如对于$y = a^{x} \\left( a > 0 \\right)$$a \\ne 1), a^{0} = 1$。",
         "如对于$y = a^{x} \\left( a > 0 , 且 a \\ne 1 \\right) , a^{0} = 1$。"),
        ("（1） $P ( \\mathcal { D } ) = 0$", "（1） $P(\\varnothing)=0$"),
        # L7578 视力 5.0 的 OCR 垃圾（劈/參）+ 引号方向
        ("“视力不低于 $5.\\;0^{ 劈 }$ 为1，“视力低于 $5.\\;0^{ 參 }$ 为0",
         "“视力不低于 $5.0$ ”为1，“视力低于 $5.0$ ”为0"),
        # L701 C三点：汉字误入公式
        ("B， $C  三$ 点是否共线", "B， $C$ 三点是否共线"),
        # L6859 平面垂直判定：平 字误入公式
        ("要证平面 $A^{\\prime}BD \\perp   平$ 面",
         "要证平面 $A^{\\prime}BD \\perp$ 平面"),
        # L6567 连接 BC1：\text{。} 实为逗号 + 句号
        ("解：连接 $BC_{1}  \\text{。 } BC_{1}$ 与 $B _ { 1 } C$ 相交于点O，"
         "连接 $A _ { 1 } O$ 设正方体的棱长为 a.",
         "解：连接 $BC_{1}$，$BC_{1}$ 与 $B _ { 1 } C$ 相交于点O，"
         "连接 $A _ { 1 } O$。设正方体的棱长为 $a$."),
        # L5630 判断对错：\bigtriangledown 实为 √，引号垃圾
        ("正确的在括号内画 $\\text{\" } \\bigtriangledown  \\text{\" }$ ，错误的画“×”.",
         "正确的在括号内画“√”，错误的画“×”."),
        # L7048 命题判断：引号垃圾
        ("则 $\\text{\" } \\alpha \\perp \\beta  \\text{\" }$ 是“m⊥β”的（）",
         "则 “$\\alpha \\perp \\beta$” 是“m⊥β”的（）"),
        # L7066 命题判断：引号垃圾 + 半角括号
        ("则 $\\text{\" }l\\text{\" } \\bot \\alpha  \\text{\" }$ 是 "
         "$\\text{\" }l\\perp m$ 且 $l \\perp n  ''$ 的().",
         "则 “$l \\perp \\alpha$” 是 “$l\\perp m$ 且 $l \\perp n$” 的（）."),
        # L3258 复数模：\boxed{z} 实为 |z| + 缺左 $
        ("不等式 $\\boxed{z}  之  1$ 的解集是 圆\\boxed { z } = 1$外部",
         "不等式 $| z | > 1$ 的解集是圆 $| z | = 1$ 外部"),
        ("满足条件1 \\leq | z | \\leq 2$ 的点Z的集合",
         "满足条件 $1 \\leq | z | \\leq 2$ 的点Z的集合"),
        # L328 / L361 平行四边形符号
        ("作 $厂 ABCD$ ，容易发现", "作 □ABCD，容易发现"),
        ("作 $(   口  ABCD$ ，则", "作 □ABCD，则"),
        # L9395 事件定义引号垃圾（点数）——注意前一条已把 D_{3} = 改成 $D _ { 3 }=$
        ("$C_{i} =  \\text{\" }$ 点数为 $i ^ { \\star }$",
         "$C_{i}=$ “点数为 $i$”"),
        ("$D _ { 1 } = ^ { \\leftrightarrow }$ 点数不大于 $2 \\text{\" }, \\; "
         "D_{2} =  \\text{\" }$ 点数大于 $2 \\text{\" }, \\; D_{3} =",
         "$D _ { 1 }=$ “点数不大于 $2$”，$D _ { 2 }=$ “点数大于 $2$”，$D _ { 3 }=$"),
        ("$D _ { 3 }=$  \\text{\" }$ 点数大于 $4 ^ { \\mathfrak { H } }$；",
         "“点数大于 $4$”；"),
        ("$E = { } ^ { \\leftrightarrow }$ 点数为奇数”， $F = { } ^ { \\leftrightarrow }$ 点数为偶数”.",
         "$E=$ “点数为奇数”， $F=$ “点数为偶数”。"),
        # L9301 对立事件：{1,2} → {1,2,3,4,5,6}，去掉 OCR 溢流
        ("= \\left\\{ 1, 2 \\right\\}$ $^ \\textrm { \\scriptsize 3 , 4 , 5 , 6 ) }$ ，",
         "= \\left\\{ 1, 2, 3, 4, 5, 6 \\right\\}$，"),
        # L9321 互为对立：A∪B=∅ → A∪B=Ω（OCR 错值）
        ("$A \\cap B = \\varnothing , A \\cup B = \\varnothing$",
         "$A \\cap B = \\varnothing , A \\cup B = \\Omega$"),
        # L9389 缺标点
        ("包含事件 $R$因为 $R   \\bigcap   \\overline { { G } }   =   \\varnothing$",
         "包含事件 $R$，因为 $R   \\bigcap   \\overline { { G } }   =   \\varnothing$"),
        ("\\right\\}$ N={(1，3)", "\\right\\}$，N={(1，3)"),
        # L1151 且 误入公式
        ("$\\overrightarrow{AB}=\\overrightarrow{DC},  且  "
         "\\left|\\overrightarrow{AB}\\right|=\\left|\\overrightarrow{AD}\\right|$",
         "$\\overrightarrow{AB}=\\overrightarrow{DC}$，且 "
         "$\\left|\\overrightarrow{AB}\\right|=\\left|\\overrightarrow{AD}\\right|$"),
        # L2028 |G| 吗
        ("能等于 $\\boxed{G}  吗  ?$ 为什么？",
         "能等于 $| G |$ 吗？为什么？"),
        # L3180 建立一一对应
        ("之间可以建 $\\begin{aligned} 立   \\text{— } \\text{— }\\end{aligned}$ 对应关系。",
         "之间可以建立一一对应关系。"),
        # L2852 游离 $ EF$
        ("$\\overrightarrow{DE}, \\overrightarrow{AD}, \\overrightarrow{BC}$ EF$，"
         "\\overrightarrow{FA}, \\overrightarrow{AB}, \\overrightarrow{CE}.$",
         "$\\overrightarrow{DE}, \\overrightarrow{AD}, \\overrightarrow{BC}, "
         "\\overrightarrow{FA}, \\overrightarrow{AB}, \\overrightarrow{CE}$."),
        # L6288 求证$:
        ("求证 $: \\frac{AB}{BC} = \\frac{DE}{EF}$", "求证：$\\frac{AB}{BC} = \\frac{DE}{EF}$"),
        # ---- S10 第二轮：事件定义引号垃圾漏网行 ----
        # L9242
        ("事件 $C =  \"摸$到球的号码是偶数”.",
         "事件 $C=$ “摸到球的号码是偶数”."),
        # L9357 例6：6 个事件定义全部被引号垃圾打碎
        ("$R_{1} =  \"第$； 一次摸到红球”", "$R_{1}=$ “第一次摸到红球”"),
        ("$R _ { 2 }   =   ^ { \\mathrm { ~ d ~ } }$ 第二次摸到红球”",
         "$R_{2}=$ “第二次摸到红球”"),
        ("$R   =   ^ { \\mathrm { ~ \\textleftarrow ~ } }$ 两次都摸到红球”",
         "$R=$ “两次都摸到红球”"),
        ("$G   =   ^ { \\mathrm { ~ \\textleftarrow ~ } }$ 两次都摸到绿球”",
         "$G=$ “两次都摸到绿球”"),
        ("$M { = } { \\it \\Delta } ^ { \\it \\Delta }$ 两个球颜色相同”",
         "$M=$ “两个球颜色相同”"),
        ("$N   =   ^ { \\mathrm { ~ \\textleftarrow ~ } }$ 两个球颜色不同”.",
         "$N=$ “两个球颜色不同”."),
        # L9835 例：两罐中奖（注意原文第3/4个是 A₁Ā₂ / Ā₁A₂）
        ("事件 $A =  \"中奖\"$", "事件 $A=$ “中奖”"),
        ("事件 $A _ { 1 }   =   ^ { \\mathrm { ~  ~~ } }$ 第一罐中奖”",
         "事件 $A_{1}=$ “第一罐中奖”"),
        ("事件 $A _ { 2 } = ~ ^ { \\mathrm { ~ d ~ } }$ 第二罐中奖”",
         "事件 $A_{2}=$ “第二罐中奖”"),
        ("那么事件 $A_{1}A_{2}= \\begin{aligned} \\text{\" } \\end{aligned}$ 两罐都中奖”",
         "那么事件 $A_{1}A_{2}=$ “两罐都中奖”"),
        ("$A_{1}A_{2}= \\mathbf{\\Omega}^{\\circ}$ 第一罐中奖，第二罐不中奖”",
         "$A_{1}\\overline{A}_{2}=$ “第一罐中奖，第二罐不中奖”"),
        ("$A _ { 1 } A _ { 2 } { = }$ “第一罐不中奖，第二罐中奖”",
         "$\\overline{A}_{1}A_{2}=$ “第一罐不中奖，第二罐中奖”"),
        # L10143 例1
        ("设事件 $A   =   ^{\\circ}  第$； 一次摸出球的标号小于 $3 ^ { \\bullet \\bullet }$ ，"
         "事件 $B =$ “第二次摸出球的标号小于3”",
         "设事件 $A=$ “第一次摸出球的标号小于 $3$”，"
         "事件 $B=$ “第二次摸出球的标号小于 $3$”"),
        # L10173 分析
        ("设 $A = { \\it \\Delta \\Psi } ^ { \\mathrm { e q } }$ 甲中靶”， $B = \\frac{\\pi}{4}  乙$ 中靶”.",
         "设 $A=$ “甲中靶”，$B=$ “乙中靶”."),
        # L10175 解
        ("设 $A = { \\it \\Delta } ^ { \\it \\Delta }$ 甲中靶”， $B = \\text{\" } 乙$ 中靶”",
         "设 $A=$ “甲中靶”，$B=$ “乙中靶”"),
        ("则 $A = { \\it \\Delta } ^ { \\mathrm { ~  ~~ } }$ 甲脱靶”， $B = \\mathrm { ~  ~~ }$ 乙脱靶”.",
         "则 $\\bar{A}=$ “甲脱靶”，$\\bar{B}=$ “乙脱靶”."),
        ("所以A与B相互独立，A与 $B \\cdot A$ 与 $B , , A$ 与B都相互独立。",
         "所以A与B相互独立，A与 $\\bar{B}$，$\\bar{A}$ 与 $B$，$\\bar{A}$ 与 $\\bar{B}$ 都相互独立。"),
        # L10241 练习1
        ("设事件 $A = { \\it \\Delta } ^ { \\omega }$ 第1枚正面朝上”",
         "设事件 $A=$ “第1枚正面朝上”"),
        ("事件 $B = \\begin{aligned}  \"第   2  \\end{aligned}$ 枚正面朝上”",
         "事件 $B=$ “第2枚正面朝上”"),
        # L10657 表格：重复全角分号
        ("$P(\\Omega) = 1$；；（3）设", "$P(\\Omega) = 1$；（3）设"),
        # ---- S10 第三轮：等号后垃圾上标（10.1.2 探究 + 事件定义） ----
        # L9252 探究：C_i
        ("$C _ { i }   =   ^ { \\mathrm { ~ \\textleftarrow ~ } }$ 点数为 "
         "$i = 1, \\quad 2, \\quad 3, \\quad 4, \\quad 5, \\quad 6$",
         "$C_i=$ 点数为 $i$（$i=1,2,\\cdots,6$）"),
        # L9254 D_1 / D_2
        ("$D _ { 1 }   =   ^ { \\mathrm { ~  ~~ } }$ 点数不大于 $3 : D_{2}=  “$ 点数大于3”；",
         "$D_1=$ 点数不大于 $3$，$D_2=$ 点数大于 $3$；"),
        # L9256 E_1 / E_2（\frac{a}{b} 与 ♭♭ 均为垃圾）
        ("$E _ { 1 }   =   ^ { \\mathrm { ~  ~~ } }$ 点数为1或 $2 : E_{2}= \\frac{a}{b}$ "
         "点数為2或 $3 ^ { \\flat \\flat }$ :",
         "$E_1=$ 点数为1或 $2$，$E_2=$ 点数为2或 $3$；"),
        # L9258 F / G
        ("$F   =   ^ { \\mathrm { ~ \\textleftarrow ~ } }$ 点数为偶数”； "
         "$G   =   ^ { \\mathrm { ~  ~~ } }$ 点数为奇数”；",
         "$F=$ 点数为偶数”；$G=$ 点数为奇数”；"),
        # L9264 第1题
        ("事件 $C _ { 1 }   =   ^ { \\mathrm { ~  ~~ } }$ 点数为1”和事件 "
         "$G   =   ^ { \\mathrm { ~ \\textleftarrow ~ } }$ 点数为奇数”，它们分别是"
         "$C _ { 1 }   =   \\{ 1 \\}$ 和 $G = \\{ 1, 3, 5 \\}$",
         "事件 $C_1=$ 点数为1”和事件 $G=$ 点数为奇数”，它们分别是 "
         "$C_1=\\{1\\}$ 和 $G=\\{1,3,5\\}$"),
        # L9276 第2题
        ("事件 $D _ { 1 }   =   ^ { \\mathrm { ~  ~~ } }$ 点数不大于 $3 ^ { \\bullet \\bullet }$ 、"
         "事件 $E _ { 1 }   =   ^ { \\mathrm { ~ d ~ } }$ 点数为1或 $2 ^ { \\bullet }$ 和事件"
         "$E _ { 2 }   =   ^ { \\mathrm { ~  ~~ } }$ 点数为2或 $3 ^ { \\bullet \\bullet }$ ，",
         "事件 $D_1=$ 点数不大于 $3$、事件 $E_1=$ 点数为1或 $2$ 和事件 "
         "$E_2=$ 点数为2或 $3$，"),
        # L9286 第3题
        ("事件 $C _ { 2 }   =   ^ { \\mathrm { ~ d ~ } }$ 点数为 $2 ^ { \\circ }$ 可以用集合的形式表示为",
         "事件 $C_2=$ 点数为 $2$ 可以用集合的形式表示为"),
        # L9288
        ("事件 $E _ { 1 }   =   ^ { \\mathrm { ~  ~~ } }$ 点数为1或 $2 ^ { \\bullet }$ 和事件 "
         "$E _ { 2 } = ~ 9$ 点数为2或 $3 ^ { \\bullet \\bullet }$ 同时发生",
         "事件 $E_1=$ 点数为1或 $2$ 和事件 $E_2=$ 点数为2或 $3$ 同时发生"),
        # L9296 第4题
        ("事件 $C _ { 3 } = ~ ^ { \\omega }$ 点数为 $3 ^ { \\bullet \\bullet }$ 和事件 "
         "$C _ { 4 } = ~ ^ { \\omega }$ 点数为 $4 ^ { \\bullet \\bullet }$ ，它们分别是",
         "事件 $C_3=$ 点数为 $3$ 和事件 $C_4=$ 点数为 $4$，它们分别是"),
        # L9306 第5题
        ("事件 $F = ~ ^ { \\mathrm { ~  ~~ } }$ 点数为偶数”", "事件 $F=$ 点数为偶数”"),
        # L9373 例6
        ("事件 $R _ { 1 } = ~ ^ { \\omega }$ 第一次摸到红球”，即 $x _ { 1 }   =   1$ 或2，于是",
         "事件 $R_1=$ 第一次摸到红球”，即 $x_1=1$ 或 $2$，于是"),
        # L9377 例6 续（R_2 部分已被通用条目修复，只剩 x_2 间距）
        ("，即 $x _ { 2 }   =   1$ 或2，于是", "，即 $x_2=1$ 或 $2$，于是"),
        # L9730 例6 回顾
        ("$R \\cup G   =   ^ { \\circ }$ “两次摸到的球颜色相同”.",
         "$R \\cup G=$ “两次摸到的球颜色相同”."),
        # L9833 分析（左引号被垃圾上标吞掉，需补）
        ("如果设 $A = { \\it \\Delta } ^ { \\mathrm { ~  ~~ } }$ 中奖”， "
         "$A _ { 1 } = ~ ^ { \\leftrightarrow }$ 第一罐中奖”， "
         "$A _ { 2 } = ~ ^ { \\omega }$ 第二罐中奖”，那么",
         "如果设 $A=$ “中奖”，$A_1=$ “第一罐中奖”，$A_2=$ “第二罐中奖”，那么"),
        # L10015 习题17
        ("设 $A _ { k } = ^ { \\mathrm { { \\textellipsis } } }$。 保修期内需要维修k次”，k=0，1，2，3，请填写下表：",
         "设 $A_k=$ “保修期内需要维修 $k$ 次”，$k=0,1,2,3$，请填写下表："),
        # ---- S10 第三轮：句号+逗号重复垃圾 ----
        # L1855
        ("\\overrightarrow{AB}$。 ，求点C，D，E的坐标.", "\\overrightarrow{AB}$，求点C，D，E的坐标."),
        # L2664
        ("$d = 5 0 0 ~ \\mathrm { m }$。 ，一艘船", "$d=500\\ \\mathrm{m}$，一艘船"),
        # L7115
        ("已知平面 $\\alpha   , \\beta   , \\gamma$。 ，且", "已知平面 $\\alpha,\\beta,\\gamma$，且"),
        # L10316 频率试验：事件定义引号垃圾 + 漏字
        ("设事件 $A = { \\it \\Delta } ^ { \\mathrm { ~ e ~ } }$ 一个正面朝上，个反面朝上”",
         "设事件 $A=$ “一个正面朝上，一个反面朝上”"),
        # L10350 计算机模拟
        ("得到事件 $A = { \\it \\Delta } ^ { \\mathrm { ~  ~~ } }$ 一个正面朝上，一个反面朝上”发生的频数",
         "得到事件 $A=$ “一个正面朝上，一个反面朝上”发生的频数"),
        # ===== S16：KaTeX 预渲染暴露的公式级错误 =====
        # L4211 复数题：$z\$ 的 \$ 是转义美元符垃圾 → $z$
        ("求 $z\\$ 及", "求 $z$ 及"),
        # L2993 向量运算：\overrightarrow{FB} 后多一个 }（array 内容组被提前闭合，\\ 跑到组外）
        ("\\overrightarrow { F B } } \\\\", "\\overrightarrow { F B } \\\\"),
        # ===== S18 =====
        # L2211 例6：$ a = 7, b = 8$ 的 $ 后带空格 → texmath 跳过
        ("中 $, a = 7, b = 8$ ，锐角C满足", "中，$a = 7, b = 8$ ，锐角C满足"),
        # L7232：数据值被包进公式且闭 $ 前是数字（, CD=1$、A D = 3$）→ texmath 跳过
        ("$AB \\parallel CD$ $\\angle DAB = 90^{\\circ}$ $A B = 2$ , CD=1$，A D = 3$ $A A _ { 1 }   =   4$。",
         "$AB \\parallel CD$，$\\angle DAB = 90^{\\circ}$，$AB=2$，$CD=1$，$AD=3$，$AA_{1}=4$。"),
        # ===== S20 =====
        # 表9.2-1 频数累计列：4 画被 OCR 识成带上划线的正（多源课件转录一致为"正"）
        ("$\\overline{ 正 }$", "正"),
        # \mathcal{Z} 一处是 arg z（辐角主值）、一处是 ∅（互斥事件 A∩B 为不可能事件），
        # 无法统一规则，必须逐条定点
        ("$\\mathtt { a r g } ~ \\mathcal { Z }$", "$\\arg z$"),
        ("$A \\bigcap B   =   \\mathcal { Z }$", "$A \\bigcap B = \\varnothing$"),
    ],
    "选择性必修第一册": [
        # L1293 打勾：\sqrt[6]{} 实为 √
        ("正确的在括号内打 $\\sqrt[6]{}$ ，错误的打 $\\text{\" } \\times  \\text{\" }$。",
         "正确的在括号内打“√”，错误的打“×”。"),
        # L2322 P1/P2 间 \text{。}
        ("直线l由点 $P_{1}  \\text{。 } P_{2}$ 唯一确定",
         "直线l由点 $P_{1}$，$P_{2}$ 唯一确定"),
        # L2406 坡度：公式尾 \text{。} 移出为句号
        ("坡度 $= \\frac{ 铅直高度 }{ 水平宽度 } \\text{。 }$ 当直线",
         "坡度 $= \\frac{ 铅直高度 }{ 水平宽度 }$。当直线"),
        # L4902 / L5429 / L5549 焦点 F1/F2 间 \text{。}
        ("经过椭圆两焦点 $F_{1}  \\text{。 } F_{2}$ 的直线为x轴",
         "经过椭圆两焦点 $F_{1}$，$F_{2}$ 的直线为x轴"),
        ("且以点P及焦点 $F_{1}  \\text{。 } F_{2}$ 为顶点的三角形",
         "且以点P及焦点 $F_{1}$，$F_{2}$ 为顶点的三角形"),
        ("那么，焦点 $F_{1}  \\text{。 } F_{2}$ 的坐标分别是",
         "那么，焦点 $F_{1}$，$F_{2}$ 的坐标分别是"),
        # L3729 / L3747 平行四边形符号
        ("8. $口 ABCD$ 的一组对边AB和CD所在直线的方程分别是",
         "8. □ABCD 的一组对边AB和CD所在直线的方程分别是"),
        ("过$厂 ABCD$ 的两条对角线的交点作与AB所在直线的平行线l",
         "过□ABCD 的两条对角线的交点作与AB所在直线的平行线l"),
        ("15. $厂 ABCD$ 的四条边所在直线的方程分别是",
         "15. □ABCD 的四条边所在直线的方程分别是"),
        ("求 $厂 ABCD$ 的面积。", "求 □ABCD 的面积。"),
        # L498 / L575 公式头冒号跑进公式
        ("那么用它表示下列向量$：\\overrightarrow{OB'}, \\overrightarrow{BA'}, "
         "\\overrightarrow{CA'}, \\overrightarrow{OG}.$",
         "那么用它表示下列向量：$\\overrightarrow{OB'}, \\overrightarrow{BA'}, "
         "\\overrightarrow{CA'}, \\overrightarrow{OG}$"),
        ("求证$：OA \\perp BC.$", "求证：$OA \\perp BC$"),
        # L6468 公式头 $： + 公式尾句号
        ("求证$：OA \\bot OB.$", "求证：$OA \\bot OB$"),
        # L391 游离 9（实为分号）
        ("$OA \\perp BC$ 9 $OB \\perp AC$ 求证$：OC \\perp AB$",
         "$OA \\perp BC$；$OB \\perp AC$。求证：$OC \\perp AB$"),
        # L2083 公式尾句号
        ("求证$：a(x - x_{0}) + b(y - y_{0}) + c(z - z_{0}) = 0.$",
         "求证：$a(x - x_{0}) + b(y - y_{0}) + c(z - z_{0}) = 0$"),
        # L2159 平行六面体：P, M 后的句号+逗号垃圾
        ("\\boldsymbol{c}.\\quad P,\\quad M$。 ，N分别是",
         "\\boldsymbol{c}$. $P, M, N$ 分别是"),
        # ---- S10 第四轮：\widehat 误识（线/面平行垂直被 OCR 成弧号） ----
        # L1600 线线平行
        ("所以 $\\widehat{FC} / / \\widehat{EC}_{1}$", "所以 $FC // EC_{1}$"),
        # L2055 面面平行
        ("平面 $\\widehat{EFG}/$ 平面 $P Q R$", "平面 $EFG//$ 平面 $PQR$"),
        # L2229 线线垂直（两个条件间补逗号）
        ("且 $AE \\perp A_{1}B$ $\\widehat{AF} \\perp A_{1}\\widehat{D}$。",
         "且 $AE \\perp A_{1}B$，$AF \\perp A_{1}D$。"),
        # L5541 双曲线定义：\widetilde{MF_1} 实为 |MF₁|，\widehat{AB} 实为 AB
        ("$\\left[ \\widetilde{MF_{1}} \\right]$ 一$\\left| \\boldsymbol{M} \\boldsymbol{F}_{2} \\right| "
         "= \\left| \\boldsymbol{A} \\boldsymbol{B} \\right|$",
         "$|MF_{1}|-|MF_{2}|=|AB|$"),
        ("距离的差的绝对值 $| \\widehat{AB} |$ 是一个常数",
         "距离的差的绝对值 $|AB|$ 是一个常数"),
        # L5453 撇号位置：\overrightarrow{GR}' → \overrightarrow{GR^{\prime}}
        ("$\\overrightarrow{GR}'$", "$\\overrightarrow{GR^{\\prime}}$"),
        # ===== S18 =====
        # L3270：①② 编号被 OCR 包进公式（\\textcircled 在 KaTeX 数学模式报警）
        ("$\\textcircled{1} \\times 2 - \\textcircled{2}$", "①$\\times 2-②$"),
    ],
    "选择性必修第二册": [
        # L2919 等差常用性质：$$ 实为分隔
        ("= \\cdots$$a_{n - k} + a_{n + k} = 2a_{n}",
         "= \\cdots$；$a_{n - k} + a_{n + k} = 2a_{n}"),
        # L2036 存栏数数列：\text{。} + "9" 实为逗号
        ("依次为 $c_{1} \\text{。 } c_{2}$ 9 $c_{3}, \\cdots$",
         "依次为 $c_{1}, c_{2}, c_{3}, \\cdots$"),
        # L2359 右边 误入公式
        ("左边 $k+1=(k+1)+1= 右边$", "左边 $k+1=(k+1)+1=$，右边"),
        # L122 / L162 公式尾分号/逗号移出
        ("(1) 1, $-\\frac{1}{2}, \\frac{1}{3}, -\\frac{1}{4}, \\cdots;$",
         "(1) 1, $-\\frac{1}{2}, \\frac{1}{3}, -\\frac{1}{4}, \\cdots$；"),
        ("(1) 1, $\\frac{1}{3}, \\frac{1}{5}, \\frac{1}{7}, \\frac{1}{9}, \\cdots,$",
         "(1) 1, $\\frac{1}{3}, \\frac{1}{5}, \\frac{1}{7}, \\frac{1}{9}, \\cdots$，"),
        # L410 斐波那契：公式尾句号
        ("$F _ { 1 } ^ { 2 }, \\quad F _ { 2 } ^ { 2 }, \\quad F _ { 3 } ^ { 2 }, "
         "\\quad F _ { 4 } ^ { 2 }, \\quad \\cdots.$",
         "$F _ { 1 } ^ { 2 }, \\quad F _ { 2 } ^ { 2 }, \\quad F _ { 3 } ^ { 2 }, "
         "\\quad F _ { 4 } ^ { 2 }, \\quad \\cdots$"),
        # L3968 公式尾逗号
        ("如果可以找到一步一步逼近r的 $x_{0}, x_{1}, \\cdots,$ $x_{n}$",
         "如果可以找到一步一步逼近r的 $x_{0}, x_{1}, \\cdots$，$x_{n}$"),
        # L3085 斜率后的点_0 垃圾
        ("的斜率 $点 _{0}$ 呢？", "的斜率呢？"),
        # L1737 麦粒：分号+逗号重复垃圾 + 单位
        ("$40\\  g$； ，据查", "$40\\ \\mathrm{g}$，据查"),
        # L2189 九章算术：数±中平里 → 数”和“中平里（± 为 ”和“ 的 OCR 垃圾）
        ("数±中平里”", "数”和“中平里”"),
        # ===== S20 =====
        # 平均速度的 v：\overset{-}{\underset{\mathcal{V}}{}} 是 \overline{v} 的 OCR 垃圾
        ("$\\overset { - } { \\underset { \\mathcal { V } } { } }$", "$\\overline{v}$"),
        # 平均速度的 u：\overset{\rightharpoonup}{\mathcal{{U}}} 是 \overline{u} 的 OCR 垃圾
        # （双花括号形态，花体规则只清 \mathcal 不清外壳）
        ("$\\overset { \\rightharpoonup } { \\mathcal { { U } } }$", "$\\overline{u}$"),
    ],
    "选择性必修第三册": [
        # L2109 事件定义
        ("设 $A   =   ^ { \\mathrm { ~ \\textleftarrow ~ } }$ 第1次抽到代数题”， "
         "$B   =   ^ { \\mathrm { ~ \\textleftarrow ~ } }$ 第2次抽到几何题”，则",
         "设 $A=$ “第1次抽到代数题”， $B=$ “第2次抽到几何题”，则"),
        # L2202 事件定义
        ("设 $B   =   ^ { \\mathrm { ~  ~ } }$ 最后1位密码为偶数”，则",
         "设 $B=$ “最后1位密码为偶数”，则"),
        # L2264 事件定义
        ("设 $A_{1} =  \"第  1$ 天去A餐厅用餐”， $B_{1} =  \"第  1$ 天去B餐厅用餐”， "
         "$A _ { 2 }   =   ^ { \\mathrm { ~  ~ } }$ 第2天去A餐厅用餐”，则",
         "设 $A_{1}=$ “第1天去A餐厅用餐”， $B_{1}=$ “第1天去B餐厅用餐”， "
         "$A _ { 2 }=$ “第2天去A餐厅用餐”，则"),
        # L2286 事件定义
        ("设 $B   =   ^ { \\mathrm { ~ \\textleftarrow ~ } }$ 任取一零件为次品”，"
         "$A _ { i } = ~ ^ { \\circ }$ 零件为第i台车床加工”（i=1，2，3)，",
         "设 $B=$ “任取一零件为次品”，$A _ { i }=$ “零件为第i台车床加工”（i=1，2，3)，"),
        # L2290 事件定义
        ("设 $B   =   ^ { \\mathrm { ~  ~~ } }$ 任取一个零件为次品” "
         "$A_{i} = \\begin{array}{c} \\end{array}$ 零件为第i台车床加工” "
         "$(i = 1, 2, 3)$ ，则",
         "设 $B=$ “任取一个零件为次品”， $A_{i}=$ “零件为第i台车床加工” "
         "$(i = 1, 2, 3)$ ，则"),
        # L2347 / L2355 信号事件
        ("设 $A = ~ ^ { \\leftrightarrow }$ 发送的信号为 $0 \\text{\" },\\ B =$ "
         "“接收到的信号为 $0 ^ { \\bullet \\bullet }$ .",
         "设 $A=$ “发送的信号为 $0$”， $B=$ “接收到的信号为 $0$”。"),
        ("设 $A   =   ^ { \\mathrm { ~  ~ } }$ 发送的信号为 $0 \\text{\" }, B =  "
         "\\text{\" }$ 接收到的信号为 $0 ^ { \\bullet \\bullet }$ ，则",
         "设 $A=$ “发送的信号为 $0$”， $B=$ “接收到的信号为 $0$”，则"),
        # L2631 次品/正品
        ("$\\{ X   =   1 \\} = { \\it \\Delta \\Psi } ^ { \\alpha }$ 抽到次品”， "
         "$\\{ X   =   0 \\} = \\cdot$ “抽到正品”",
         "$\\{ X   =   1 \\}=$ “抽到次品”， $\\{ X   =   0 \\}=$ “抽到正品”"),
        # L2666 五级评价
        ("且$\\{ X   =   1 \\}   = ~ { } ^ { \\alpha }$ 不及格”， "
         "$\\{ X   =   2 \\} = { \\it \\Delta \\Psi } ^ { \\alpha }$ 及格”， "
         "$\\{ X   =   3 \\} = { \\it \\Delta \\Psi } ^ { \\alpha }$ 中等”， "
         "$\\{ X   =   4 \\} = { \\it \\Delta \\Psi } ^ { \\alpha }$ 良”，"
         "$\\{ X   =   5 \\}   =   \\mathrm { ~  ~~ }$ 优”.",
         "且$\\{ X   =   1 \\}=$ “不及格”， $\\{ X   =   2 \\}=$ “及格”， "
         "$\\{ X   =   3 \\}=$ “中等”， $\\{ X   =   4 \\}=$ “良”，"
         "$\\{ X   =   5 \\}=$ “优”."),
        # L3397 / L3419 正反面/左右下落
        ("设 $A   =   ^ { \\mathrm { ~  ~~ } }$ 正面朝上”，则",
         "设 $A=$ “正面朝上”，则"),
        ("设 $A   =   ^ { \\mathrm { ~ \\textleftarrow ~ } }$ 向右下落”，则 "
         "$\\overline { { A } } = \\mathrm { ~  ~~ }$ 向左下落”，且",
         "设 $A=$ “向右下落”，则 $\\overline { { A } }=$ “向左下落”，且"),
        # L4908 残差均值 0
        ("残差应是均值为 $0 _ { \\mathrm { ~ x ~ }}$ 方差为",
         "残差应是均值为 $0$、方差为"),
        # L5049 待定参数 c1/c2
        ("其中 $c _ { \\mathrm { ~ 1 ~ } } , \\quad c _ { \\mathrm { ~ 2 ~ } }$ 是待定参数",
         "其中 $c _ { 1 }, \\quad c _ { 2 }$ 是待定参数"),
        # L6015 / L6039 PM2.5 下标
        ("控制空气中 $\\mathrm { P M } _ { 2, \\mathrm { ~ } 5 }$ 浓度的目的",
         "控制空气中 $\\mathrm { P M } _ { 2 . 5 }$ 浓度的目的"),
        ("建立 $\\mathrm { P M _ { 2, } }$ 浓度与汽车流量之间的回归方程",
         "建立 $\\mathrm { P M } _ { 2 . 5 }$ 浓度与汽车流量之间的回归方程"),
        ("我们得到了 $\\mathrm { P M _ { 2 .5 } }$ 浓度关于汽车流量的回归方程",
         "我们得到了 $\\mathrm { P M } _ { 2 . 5 }$ 浓度关于汽车流量的回归方程"),
        # L6039 R 代码：data=w 的 OCR 垃圾
        ("浓度～汽车流量， $_ \\mathrm { w } ) ^ { \\mathrm { ~\\tiny ~ \\theta ~ } }$ ，建立",
         "浓度～汽车流量， $data = w)$ ，建立"),
        # L1040 排列数 A_n^m 的 师 / °C 垃圾
        ("排列数 $\\mathrm{A}_{n}^{m  师 }$ ，可以看作",
         "排列数 $\\mathrm { A } _ { n } ^ { m }$ ，可以看作"),
        ("共有 $\\mathrm { ^ { \\circ } C } _ { n } ^ { m }$ 种不同的取法",
         "共有 $\\mathrm { C } _ { n } ^ { m }$ 种不同的取法"),
        # L730 / L778 \Lambda → \mathrm{A}
        ("表示为 $\\Lambda _ { 3 } ^ { 2 }$。", "表示为 $\\mathrm { A } _ { 3 } ^ { 2 }$。"),
        ("排列数 $\\Lambda _ { n } ^ { m }$", "排列数 $\\mathrm { A } _ { n } ^ { m }$"),
        # L1024 A_4^3 后的引号垃圾
        ("排列数 $\\mathrm{A_4^{3}}^{\\mathfrak{99}}$第1步",
         "排列数 $\\mathrm { A } _ { 4 } ^ { 3 }$。第1步"),
        # L1132 \mathbb{C} → \mathrm{C}
        ("组合数 $\\mathbb { C } _ { n } ^ { m }$ 的内置函数",
         "组合数 $\\mathrm { C } _ { n } ^ { m }$ 的内置函数"),
        # L5635 相互独立
        ("分类变量X与 $Y$ 相互独 $\\frac{ 立 }{ 立 }$ ，即",
         "分类变量X与 $Y$ 相互独立，即"),
        # L5555 希腊 Χ → 拉丁 X
        ("成对分类变量 Χ 和Y", "成对分类变量 X 和Y"),
        # L1274 公式头 $. 垃圾 + 公式内 {: } 垃圾
        ("选法种数 $\\mathrm { { : } C _ { 1 2 } ^ { 5 } }$ ，即有",
         "选法种数 $\\mathrm { C } _ { 1 2 } ^ { 5 }$ ，即有"),
        # L1785 提示公式：$：55…（批处理会把 $： 挪到公式外）+ 公式尾句号
        ("（提示$：55^{55}+9=(56-1)^{55}+9.$",
         "（提示：$55^{55}+9=(56-1)^{55}+9$"),
        ("证明 $5 5 ^ { 5 5 }   \\pm 9$ 能被8整除", "证明 $55^{55} \\pm 9$ 能被8整除"),
        # L2186 事件定义（左引号被垃圾上标吞掉）
        ("设 $A _ { i } = ~ ^ { \\leftrightarrow }$ 第 i 次按对密码” $(i = 1, 2)$ ，则",
         "设 $A_i=$ 第 $i$ 次按对密码”（$i=1,2$），则"),
        # L2355 信号传递：\overline{B} 后的垃圾上标 + 公式内 ♭
        ("$\\overline { { B } }   =   ^ { \\mathrm { ~ \\textleftarrow ~ } }$ "
         "接收到的信号为 $1 ^ { \\flat }$。",
         "$\\overline{B}=$ 接收到的信号为 $1$。"),
        # L3529 二项式系性质：\not p 实为 p
        ("令 $q   =   1   -   \\not p$", "令 $q=1-p$"),
        # ===== S11：用户截图报告轮（2026-10-22）=====
        # L1842 杨辉三角：t 垃圾前缀 + \mathbf{C} 误识（全书用 \mathrm{C}，107 处）
        ("$t \\mathbf { C } _ { n } ^ { r - 1 }$", "$\\mathrm{C}_{n}^{r-1}$"),
        # ===== S18 =====
        # L1268：$ \\mathrm { C } _ { 1 2 } ^ { 5 }$ 的 $ 后带空格 → texmath 跳过
        ("如果把 $. \\mathrm { C } _ { 1 2 } ^ { 5 }$ 解释为",
         "如果把 $\\mathrm { C } _ { 1 2 } ^ { 5 }$ 解释为"),
        # ===== S20：图3 杨辉三角数表重建 =====
        # OCR 吞掉每行首 1、把第5/6行并成一行、末两行 C 记号崩坏。按 Pascal 三角
        # 重建（数学内容确定：第 n 行第 r 个数 = C(n, r-1)，与紧接的正文互证）。
        # 版式为合理设计（两列：行号/数值），非原书排版
        ("| 第0行 |\n| --- |\n| 第1行 1 1 |\n| 第2行 2 1 1 |\n| 第3行 3 3 1 1 |\n"
         "| 第4行 4 6 4 1 1 |\n| 第5行 10 10 5 5 1 1 第6行 |\n| 15 20 15 1 6 6 1 |\n"
         "| : : |\n| Cn-1 C-1 Cn=1 Cn−1 第n—1行 Cn−1 1 1 |\n"
         "| Cn−1 C2 Cn−1 Cr+1 Cn 第 n行 Cn 1 1 : |",
         "| 行号 | 数值 |\n| --- | --- |\n"
         "| 第0行 | $1$ |\n| 第1行 | $1,\\;1$ |\n| 第2行 | $1,\\;2,\\;1$ |\n"
         "| 第3行 | $1,\\;3,\\;3,\\;1$ |\n| 第4行 | $1,\\;4,\\;6,\\;4,\\;1$ |\n"
         "| 第5行 | $1,\\;5,\\;10,\\;10,\\;5,\\;1$ |\n"
         "| 第6行 | $1,\\;6,\\;15,\\;20,\\;15,\\;6,\\;1$ |\n| ⋮ | ⋮ |\n"
         "| 第n-1行 | $1,\\;\\mathrm{C}_{n-1}^{1},\\;\\cdots,\\;\\mathrm{C}_{n-1}^{n-2},\\;1$ |\n"
         "| 第n行 | $1,\\;\\mathrm{C}_{n}^{1},\\;\\cdots,\\;\\mathrm{C}_{n}^{r},\\;\\cdots,\\;"
         "\\mathrm{C}_{n}^{n-1},\\;1$ |"),
    ],
    # ===== 化学（2026-10-26 B4 实战首册）：OCR 噪音数字贴在行内公式定界符上 =====
    # texmath dollars 规则把"数字紧贴 $"视为非公式，预览会显示裸 LaTeX；
    # 两处内容均由表格语义唯一确定（饱和 NaHCO₃ 溶液 / 碳酸根离子方程式），无歧义。
    "【人教版】高中必修 第一册化学电子课本": [
        # 表「加入的试剂」列：原文"饱和 NaHCO₃ 溶液"，OCR 在"饱和"后多吐一个 1
        ("饱和1$\\mathrm{NaHCO}_{3}$溶液", "饱和$\\mathrm{NaHCO}_{3}$溶液"),
        # 实验设计表③行结论列：离子方程式闭 $ 后多吐一个噪音 2
        ("$\\mathrm{CO}_{3}^{2-}+\\mathrm{H}^{+}=\\mathrm{HCO}_{3}^{-}$2",
         "$\\mathrm{CO}_{3}^{2-}+\\mathrm{H}^{+}=\\mathrm{HCO}_{3}^{-}$"),
    ],
}

# 整行重写（正则锚定 ^...$，re.M）：OCR 把整行搅碎、无法用串替换挽救的行
# 新整行用函数返回，避免 re 把 \overrightarrow 当作模板转义
REWRITE = {
    "必修第一册": [
        # L3152 单调性定义：2699 字符退化垃圾（\text{N} \quad 连排），原文仅"（严"两字
        (re.compile(r"^如果函数 \$y = f\(x\)\$ 在区间Ⅰ上单调递增或单调递减.*$", re.M),
         lambda m: ("如果函数 $y = f(x)$ 在区间Ⅰ上单调递增或单调递减，那么就说函数 "
                    "$y = f(x)$ 在这一区间具有（严格的）单调性，区间Ⅰ叫做 $y = f(x)$ 的单调区间。")),
        # L231 练习2：OCR 把整题打成 2183 字符退化垃圾（\text{1} 连续重复 91 次）
        # 按教材原题（人教A版必修第一册 P5 练习T2，三个独立来源交叉验证）还原六小题
        (re.compile(r"^\$\\begin\{aligned\}& \\text\{1 \} \\mathbf\{N\};.*$", re.M),
         lambda m: ("(1) 0＿＿＿＿$N$；\n\n"
                    "(2) -3＿＿＿＿$N$；\n\n"
                    "(3) 0.5＿＿＿＿$Z$；\n\n"
                    "(4) $\\sqrt{2}$＿＿＿＿$Z$；\n\n"
                    "(5) $\\frac{1}{3}$＿＿＿＿$Q$；\n\n"
                    "(6) $\\pi$＿＿＿＿$R$。")),
    ],
    "必修第二册": [
        (re.compile(r"^例4 如图 6\.2-13，.*吗？\s*$", re.M),
         lambda m: ("例4 如图 6.2-13，在□ABCD中，$\\overrightarrow{AB}=\\boldsymbol{a}$，"
                    "$\\overrightarrow{AD}=\\boldsymbol{b}$，你能用a，b表示向量"
                    "$\\overrightarrow{AC}$，$\\overrightarrow{DB}$吗？")),
    ],
}


# 批量模式：(说明, 正则, 替换, 期望册或 None=全部)
# 替换串用函数返回，避免 re 把 \mathrm 当作模板转义
_PM = "\\mathrm { P M } _ { 2 . 5 }"
_CIRCLED = {"0": "\u24ea", "1": "\u2460", "2": "\u2461", "3": "\u2462",
            "4": "\u2463", "5": "\u2464", "6": "\u2465", "7": "\u2466",
            "8": "\u2467", "9": "\u2468"}
# 花体字母 → 正解（OCR 把斜体拉丁字母/空集识别成 \mathcal）。
# 依据：人教 A 版官网教学设计等多源一致——命题条件用 p、结论用 q（小写）；
# Δ=0 时 ax²+bx+c<0 解集为 ∅；对立事件 A∩B=∅；P(∅)=0；工资 w；cos x；平均速度 u/v
_CAL_MAP = {"D": "\\varnothing", "P": "p", "W": "w", "x": "x", "U": "u", "V": "v"}
BATCH = [
    # 花体 X/Y/O → 正体（坐标轴字母被 OCR 成 \mathcal）
    ("花体X/Y/O→正体", re.compile(r"\\mathcal\s*\{\s*([XYO])\s*\}"), r"\1", None),
    # \text{。} → 中文逗号（点间逗号误识；公式尾情形已在 TARGETED 处理）
    ("\\text{。}→，", re.compile(r"\\text\s*\{\s*。\s*\}"), "，", None),
    # 引号垃圾 \text{"} → 左引号
    ("引号垃圾→左引号", re.compile(r"\\text\s*\{\s*\"\s*\}"), "“", None),
    # 重复全角逗号
    ("重复逗号", re.compile("，\\s*，"), "，", None),
    # 公式头标点跑进公式：求证$：… → 求证：$…（含半角 , ; :）
    ("公式头标点移出", re.compile("(?<=[" + HAN + "])[ \\t]*\\$([：，,;:])"), r"\1$", None),
    # $. 垃圾前缀（OCR 在公式起始符后多写一个句点）：$. X → $ X
    ("公式头$.垃圾", re.compile("([" + HAN + "])[ \\t]*\\$\\."), r"\1 $", None),
    # PM2.5 下标归一
    ("PM2.5下标归一A", re.compile(r"\\mathrm\s*\{\s*PM\s*_\s*\{[^}]*\}\s*\}"),
     lambda m: _PM, None),
    ("PM2.5下标归一B", re.compile(r"\\mathrm\s*\{\s*PM\s*\}\s*_\s*\{[^}]*\}"),
     lambda m: _PM, None),
    # L9469 巨型引号垃圾：设 M = ^{...上百层嵌套...\text{$
    ("L9469巨型垃圾", re.compile(r"设 \$M\s*=\s*\^\s*\{.*?\\text\s*\{[^$]*\$"),
     lambda m: "设 $M=$ “选中正确答案”", "必修第二册"),
    # 句号/分号/冒号后紧跟逗号（OCR 重复标点，首个标点是垃圾）
    ("句分号后逗号垃圾", re.compile("[。；：]\\s*，"), "，", None),
    # 逗号后紧跟分号（OCR 重复标点）
    ("逗号后分号垃圾", re.compile("，\\s*；"), "，", None),
    # \textless/\textgreater → 裸 < >（部分渲染器不识别该命令，裸符号兼容性最好）
    ("\\textless→<", re.compile(r"\\textless"), "<", None),
    ("\\textgreater→>", re.compile(r"\\textgreater"), ">", None),
    # ===== S16：KaTeX 预渲染暴露的公式级错误（md2html 构建期验证） =====
    # 视力数据数组：OCR 把 50 位数据表崩坏成 226 格（7 列声明 vs 上百单元格，KaTeX 报
    # "Expected & or \\"）→ 按教材原文重建。数据经 4 个独立来源交叉一致；
    # 27 个 1 与文中样本平均数 0.54 = 27/50 精确吻合
    ("视力数据数组重建",
     re.compile(r"\\begin\{array\}\s*\{\s*c\s+c\s+c\s+c\s+c\s+c\s+c\s*\}.*?\\end\{array\}"),
     lambda m: ("\\begin{array}{l}1\\ 1\\ 0\\ 1\\ 0\\ 0\\ 1\\ 0\\ 1\\ 1\\ 1\\ 0\\ 0\\ 0\\ 1\\ 1\\ 0\\ 1\\ 0\\ 0"
                "\\\\0\\ 1\\ 1\\ 1\\ 0\\ 1\\ 1\\ 0\\ 1\\ 1\\ 1\\ 1\\ 0\\ 1\\ 1\\ 0\\ 1\\ 0\\ 1\\ 0"
                "\\\\0\\ 0\\ 1\\ 0\\ 0\\ 1\\ 1\\ 1\\ 0\\ 0\\end{array}"),
     "必修第二册"),
    # 同页另一段 20 位误提数组（与权威序列任何一段都不匹配）→ 整块删除（含 $$ 行）
    ("误提视力数据清除",
     re.compile(r"(?m)^\$\$[ \t]*\n\\begin\{array\}\s*\{l\}\s*1\\ 1\\ 0\\ 1\\ 1\\ 0.*?\\end\{array\}[ \t]*\n\$\$[ \t]*\n?"),
     "", "必修第二册"),
    # 样本空间 Ω₁：aligned 枚举重复粘贴 + 行尾截断（(\mathrm{G}_{2 未闭合，
    # KaTeX 报 "Expected '}'"）→ 重建为 16 个有序对（4 人有放回抽取 2 人）
    ("样本空间Ω₁重建",
     re.compile(r"\\begin\{aligned\}\\Omega\s*_\s*\{\s*1\s*\}.*?\\end\{aligned\}"),
     lambda m: ("\\begin{aligned}\\Omega_{1} = & \\{(\\mathrm{B}_{1},\\ \\mathrm{B}_{1}),\\ "
                "(\\mathrm{B}_{1},\\ \\mathrm{B}_{2}),\\ (\\mathrm{B}_{1},\\ \\mathrm{G}_{1}),\\ "
                "(\\mathrm{B}_{1},\\ \\mathrm{G}_{2}),\\\\ & (\\mathrm{B}_{2},\\ \\mathrm{B}_{1}),\\ "
                "(\\mathrm{B}_{2},\\ \\mathrm{B}_{2}),\\ (\\mathrm{B}_{2},\\ \\mathrm{G}_{1}),\\ "
                "(\\mathrm{B}_{2},\\ \\mathrm{G}_{2}),\\\\ & (\\mathrm{G}_{1},\\ \\mathrm{B}_{1}),\\ "
                "(\\mathrm{G}_{1},\\ \\mathrm{B}_{2}),\\ (\\mathrm{G}_{1},\\ \\mathrm{G}_{1}),\\ "
                "(\\mathrm{G}_{1},\\ \\mathrm{G}_{2}),\\\\ & (\\mathrm{G}_{2},\\ \\mathrm{B}_{1}),\\ "
                "(\\mathrm{G}_{2},\\ \\mathrm{B}_{2}),\\ (\\mathrm{G}_{2},\\ \\mathrm{G}_{1}),\\ "
                "(\\mathrm{G}_{2},\\ \\mathrm{G}_{2})\\}.\\end{aligned}"),
     "必修第二册"),
    # 图7.1-2 全概率括号公式：三层嵌套 + 行尾截断（_ { \begin 断头，KaTeX 报
    # "Unexpected end of input"）→ 重建为括号标注形式，数学内容与紧随其后的
    # 推导公式 P(R₂)=P(R₁)P(R₂|R₁)+P(B₁)P(R₂|B₁) 一致
    ("全概率括号公式重建",
     re.compile(r"\\overbrace\s*\{\s*\\overbrace.*$", re.M),
     lambda m: ("\\overbrace{\\underbrace{P(\\mathrm{R}_{1})P(\\mathrm{R}_{2}\\mid \\mathrm{R}_{1})}"
                "_{P(\\mathrm{R}_{1}\\mathrm{R}_{2})}+\\underbrace{P(\\mathrm{B}_{1})"
                "P(\\mathrm{R}_{2}\\mid \\mathrm{B}_{1})}_{P(\\mathrm{B}_{1}\\mathrm{R}_{2})}}"
                "^{P(\\mathrm{R}_{2})}"),
     "选择性必修第三册"),
    # 公式围栏还原：诱导公式（公式二/三/四）被 MinerU 包成 ```txt 代码围栏，
    # md 里渲染成等宽代码块 → 还原为 $$ 块公式。判据：行内含 (π 或 (—（R 语言
    # 输出围栏无此特征，保持代码块不动）
    ("公式围栏还原为块公式",
     re.compile(r"(?ms)^```[a-z]*\n((?:[^\n`]*\((?:\u03c0|\u2014)[^\n`]*\n)+)```"),
     lambda m: "$$\n" + "\\\\\n".join(_fence_latex(l) for l in m.group(1).strip().split("\n")) + "\n$$",
     "必修第一册"),
    # ===== S18：\textcircled 垃圾（KaTeX 数学模式不支持该命令，且 OCR 把
    # ⊙O 圆记号啃成 \textcircled{e/o/\circ} O，渲染出 "e◯O" 错误内容） =====
    ("\\textcircled{e} O→\\odot O",
     re.compile(r"\\textcircled\s*\{\s*e\s*\}\s*O"),
     lambda m: "\\odot O", None),
    ("\\textcircled{o} O→\\odot O",
     re.compile(r"\\textcircled\s*\{\s*o\s*\}\s*O"),
     lambda m: "\\odot O", None),
    ("\\textcircled{\\circ} O→\\odot O",
     re.compile(r"\\textcircled\s*\{\s*\\circ\s*\}\s*O"),
     lambda m: "\\odot O", None),
    # 相似符号 ∽ 被啃成 \textcircled{\triangle}
    ("\\textcircled{\\triangle}→\\sim",
     re.compile(r"\\textcircled\s*\{\s*\\triangle\s*\}\s*"),
     lambda m: "\\sim ", None),
    # 52℃：\textcircled { c } 实为 °C
    ("\\textcircled{c}→°C",
     re.compile(r"\$\s*5\s*2\s*\\textcircled\s*\{\s*c\s*\}\s*\$"),
     lambda m: "$52^{\\circ}\\mathrm{C}$", None),
    # 公式四前的 OP₄：\textcircled{O} P _ { 4 } → OP_{4}
    ("\\textcircled{O}P₄→OP₄",
     re.compile(r"\\textcircled\s*\{\s*O\s*\}\s*P\s*_\s*\{\s*4\s*\}"),
     lambda m: "OP_{4}", None),
    # $\textcircled{数字}$ → 带圈数字（整公式形式；与同行其他 ①② 写法一致）
    ("$\\textcircled{数字}$→带圈数字",
     re.compile(r"\$\\textcircled\s*\{\s*([0-9])\s*\}\$"),
     lambda m: _CIRCLED.get(m.group(1), m.group(1)), None),
    # \textcircled{数字} → 数字（KaTeX 数学模式不支持该命令；编号应作文本。
    # ⊙O/相似符号等特异形态已由上面几条处理，此处兜底纯数字编号）
    ("\\textcircled{数字}→数字",
     re.compile(r"\\textcircled\s*\{\s*([0-9])\s*\}"),
     lambda m: m.group(1), None),
    # ===== S18：块公式顶层 \\ 换行修复 =====
    # 顶层 \\ 在 display 模式下不换行（KaTeX 原话："\\ or \newline does nothing
    # in display mode"），诱导公式三行挤成一行 → 包 \begin{gathered} 恢复分行
    ("块公式 gathered 包裹",
     re.compile(r"\$\$\n(.*?)\n\$\$", re.S),
     lambda m: (m.group(0) if ("\\\\" not in m.group(1) or "\\begin{" in m.group(1))
                else "$$\n\\begin{gathered}\n" + m.group(1) + "\n\\end{gathered}\n$$"),
     None),
    # ===== S20：花体字母 → 正解 =====
    # OCR 把斜体拉丁字母/空集识别成 \mathcal。P→p（63 处，人教 A 版官网教学设计
    # 等多源一致：命题条件用 p、结论用 q，小写）；D→∅（Δ=0 时 ax²+bx+c<0 解集、
    # 对立事件 A∩B、P(∅)=0）；W→w（工资）；x→x（cos x）；U/V→u/v（平均速度）
    # 只吃 \mathcal 自己的花括号：旧写法 \{?…\}? 会把外层构造的右括号一并吞掉
    # （\overline { { \mathcal{U} } } → \overline { { u } ，KaTeX 括号失衡），
    # 故用二选一结构把双花括号形态锁死在 \mathcal 内部，外层括号原样保留
    ("花体字母→正解",
     re.compile(r"\\mathcal\s*\{\s*(?:\{\s*([A-Za-z])\s*\}|([A-Za-z]))\s*\}"),
     lambda m: _CAL_MAP.get(m.group(1) or m.group(2),
                            m.group(1) or m.group(2)), None),
    # ===== S20：右引号被 OCR 啃成上标 → 移到公式外 =====
    # "若p，则q”形式" 的 ” 被识成 ^{\flat}/^{99}/^{39}/^{\ast 9}/^{\mathfrak{D}}/^{\\infty}。
    # 只匹配内容为单个命题符号（p/q/\\bar{p}）的公式——合法的 (x+1)^{99} 内容长，
    # 不会误匹配（已实测：选必二 (x+1)^{99} 零误中）
    ("引号啃成上标→移出公式",
     re.compile(r"\$(\s*\\bar\s*\{\s*[a-z]\s*\}\s*|\s*[a-z]\s*)\^"
                r"\s*\{\s*(?:\\flat|99|39|\\ast\s*9|\\mathfrak\s*\{\s*D\s*\}|\\infty)\s*\}\$"),
     lambda m: "$" + m.group(1).strip() + "$”", None),
]



def _fence_latex(line):
    """公式围栏行 → LaTeX：sin→\\sin、π→\\pi、α→\\alpha、—→-、= 两侧空格压掉"""
    s = line.strip().replace("\u2014", "-")
    s = re.sub(r"\b(sin|cos|tan)\b", lambda m: "\\" + m.group(1), s)
    s = s.replace("\u03c0", "\\pi").replace("\u03b1", "\\alpha")
    s = re.sub(r"\s*=\s*", "=", s)
    return s


_WS = "[ \\t]*"


def _tolerant(old):
    """把字面串转成逐 token、token 之间允许任意空白的正则。
    OCR 输出的 ~ 间距与空格位置不稳定（如 `}}` vs `} }`、`2,` vs `2 ,`、
    `~\\tiny` vs `~ \\tiny`），精确串常因一个空格失配，故切掉全部空白后
    用 [ \\t]* 重新连接，~ 连续段折叠为 ~+。"""
    toks, i = [], 0
    while i < len(old):
        ch = old[i]
        if ch in " \t":
            i += 1
            continue
        if ch == "~":
            j = i
            while j < len(old) and old[j] == "~":
                j += 1
            toks.append("~+")
            i = j
            continue
        if ch == "“":
            # 左引号在 OCR 原文里常以 \text{" } 垃圾形态出现（BATCH 后置转换），
            # 容忍匹配两种写法
            toks.append("(?:“|\\\\text[ \\t]*\\{[ \\t]*\"[ \\t]*\\})")
            i += 1
            continue
        toks.append(re.escape(ch))
        i += 1
    return re.compile(_WS.join(toks))


def s10(md, book=""):
    n_t = n_b = n_r = 0
    # 0) 整行重写
    for pat, new in REWRITE.get(book, []):
        md, k = pat.subn(new, md)
        if k != 1:
            print("    [S10 警告] %s 整行重写命中 %d 次: %r" % (book, k, pat.pattern[:60]))
        n_r += k
    # 1) 逐册精确串（先精确匹配，失败则退化为空白/~ 容忍正则）
    for old, new in TARGETED.get(book, []):
        cnt = md.count(old)
        if cnt == 1:
            md = md.replace(old, new, 1)
            n_t += 1
            continue
        pat = _tolerant(old)
        md, k = pat.subn(lambda m: new, md)
        if k != 1:
            print("    [S10 警告] %s 精确命中 %d 次 / 容忍命中 %d 次: %r"
                  % (book, cnt, k, old[:60]))
        n_t += k
    # 2) 批量模式
    for desc, pat, rep, only in BATCH:
        if only and book != only:
            continue
        md, k = pat.subn(rep, md)
        n_b += k
    return md, n_t + n_b + n_r


def s8(md):
    lines = [l for l in md.split("\n") if not l.strip().startswith("<!-- alt:")]
    return add_formula_alt("\n".join(lines))


# ===================== S12：内容级修复（截图报告第二轮） =====================
# 覆盖上一轮"引用完整性"检查的盲区——图存在但图里没有内容：
#   1) 水印带/碎片图（人教社水印被误检为图片块，无任何教学内容）→ 移除引用
#   2) 小节类别图标（复习巩固/综合运用/拓广探索）→ 补 alt 文字
#   3) HTML 表格泄漏 → 转 Markdown 表格（支持 rowspan/colspan/img）
#   4) HTML 标签泄漏（small/span/div、行内 img）→ 清理
#   5) 数学区内 HTML 实体转义（&gt; 等）→ 还原为 > < &
# 判定依据：灰度墨量 < 1% 且饱和度 < 2% 且（宽高比 > 3 或面积 < 6 万像素），
# 并逐张人工目检（排除淡蓝细线的知识结构图等误报）。

WATERMARK = {
    "必修第一册": ["page_101_image_9.jpg", "page_180_image_7.jpg", "page_18_image_16.jpg",
            "page_190_image_5.jpg", "page_194_image_7.jpg", "page_253_image_8.jpg",
            "page_261_image_2.jpg", "page_338_image_4.jpg", "page_493_image_13.jpg",
            "page_509_image_1.jpg", "page_511_image_1.jpg"],
    "必修第二册": ["page_108_image_2.jpg", "page_114_image_7.jpg", "page_118_image_4.jpg",
            "page_126_image_9.jpg", "page_197_image_34.jpg", "page_197_image_37.jpg",
            "page_205_image_2.jpg", "page_21_image_17.jpg", "page_255_image_6.jpg",
            "page_364_image_9.jpg", "page_431_image_3.jpg", "page_433_image_14.jpg",
            "page_438_image_5.jpg", "page_500_image_4.jpg", "page_520_image_9.jpg"],
    "选择性必修第一册": ["page_189_image_12.jpg", "page_193_image_13.jpg", "page_271_image_8.jpg"],
    "选择性必修第二册": ["page_195_image_2.jpg", "page_36_image_6.jpg"],
    "选择性必修第三册": ["page_266_image_6.jpg"],
}


class _TableParser(HTMLParser):
    """极简 HTML 表格解析：行/单元格文本、rowspan/colspan、img"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.cur_row, self.cur_cell = [], None, None
        self.in_table = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = True
        elif not self.in_table:
            return
        elif tag == "tr":
            self.cur_row = []
        elif tag in ("td", "th"):
            d = dict(attrs)
            self.cur_cell = {"t": "", "rs": int(d.get("rowspan", 1) or 1),
                             "cs": int(d.get("colspan", 1) or 1), "img": ""}
        elif tag == "img" and self.cur_cell is not None:
            self.cur_cell["img"] = dict(attrs).get("src", "")
        elif tag == "br" and self.cur_cell is not None:
            self.cur_cell["t"] += " "

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = False
        elif tag == "tr" and self.cur_row is not None:
            self.rows.append(self.cur_row)
            self.cur_row = None
        elif tag in ("td", "th") and self.cur_cell is not None and self.cur_row is not None:
            self.cur_row.append(self.cur_cell)
            self.cur_cell = None

    def handle_data(self, data):
        if self.cur_cell is not None:
            self.cur_cell["t"] += data


def _html_table_to_md(html):
    p = _TableParser()
    p.feed(html)
    if not p.rows:
        return ""
    expanded, occupied = [], set()
    for r, row in enumerate(p.rows):
        line, c = [], 0
        for cell in row:
            while (r, c) in occupied:
                line.append("")
                c += 1
            txt = cell["t"].strip()
            if cell["img"]:
                img = "![](%s)" % cell["img"]
                txt = (txt + " " + img).strip() if txt else img
            line.append(txt)
            line.extend([""] * (cell["cs"] - 1))
            for k in range(1, cell["rs"]):
                for j in range(cell["cs"]):
                    occupied.add((r + k, c + j))
            c += cell["cs"]
        expanded.append(line)
    ncol = max(len(l) for l in expanded)
    for l in expanded:
        l.extend([""] * (ncol - len(l)))
    out = []
    for i, l in enumerate(expanded):
        out.append("| " + " | ".join(x.replace("\n", " ").replace("|", "\\|") for x in l) + " |")
        if i == 0:
            out.append("| " + " | ".join(["---"] * ncol) + " |")
    return "\n".join(out)


def s12(md, book="", imgdir=None, qroot=None):
    n = 0
    # 1) 水印带/碎片图：无教学内容，移除引用（整行 ![] 或表内 <img>）
    for f in WATERMARK.get(book, []):
        md, k = re.subn(r"(?m)^!\[\]\(images/%s\)[ \t]*\n" % re.escape(f), "", md)
        n += k
        md, k = re.subn(r'<img\s+src="images/%s"\s*/>' % re.escape(f), "", md)
        n += k
    # 2) HTML 表格 → Markdown 表格
    md, k = re.subn(r"<table[^>]*>.*?</table>",
                    lambda m: "\n" + _html_table_to_md(m.group(0)) + "\n", md, flags=re.S)
    n += k
    # 4) HTML 标签泄漏清理（small/span/div、行内 img、行首星号转义）
    md, k = re.subn(r"</?(?:small|span|div)[^>]*>", "", md)
    n += k
    md, k = re.subn(r'<img\s+src="([^"]+)"\s*/>', r"![](\1)", md)
    n += k
    md, k = re.subn(r"(?m)^\*(?=\s*标有)", "\\\\*", md)
    n += k
    # 5) HTML 实体转义还原（数学区内必改——KaTeX 不解码实体；正文/表格一并还原消除源码噪声）
    md = re.sub(r"\$[^$\n]+\$",
                lambda m: (m.group(0).replace("&gt;", ">").replace("&lt;", "<")
                           .replace("&amp;", "&").replace("&quot;", '"')), md)
    md = md.replace("&lt;a，b&gt;", "⟨a，b⟩")
    md = (md.replace("&gt;", ">").replace("&lt;", "<")
             .replace("&quot;", '"').replace("&amp;", "&"))
    # 6) 表内 img 路径错位修复：重跑提取后页码改名，普通引用已改写、表内引用漏改。
    #    按 table_image_序号_单元格 后缀在同册 images 目录中找唯一现存文件重映射
    if imgdir is None:
        raise ValueError("s12/s15 需要 imgdir 参数（由 run() 注入 <output_dir>/<book>/images）")
    if os.path.isdir(imgdir):
        existing = set(os.listdir(imgdir))

        def _remap(m):
            fn = m.group(1)
            if fn in existing:
                return m.group(0)
            k = re.search(r"table_image_(\d+_\d+)\.jpg$", fn)
            if not k:
                return m.group(0)
            cands = [f for f in existing if f.endswith("table_image_" + k.group(1) + ".jpg")]
            if len(cands) == 1:
                return "images/" + cands[0]
            print("    [S12 警告] %s 表内图 %s 候选 %d 个，未重映射" % (book, fn, len(cands)))
            return m.group(0)

        md, k = re.subn(r"images/(page_\d+_table_image_\d+_\d+\.jpg)", _remap, md)
        n += k
        # 7) 水印图文件本体清理（引用已移除，文件即垃圾）
        for f in WATERMARK.get(book, []):
            fp = os.path.join(imgdir, f)
            if os.path.exists(fp) and ("images/" + f) not in md:
                _quarantine_image(fp, imgdir, qroot)
                n += 1
    return md, n


# ===================== S13：排版层修复（L3 探测器） =====================
# 1) 思考框图标被 OCR 成问号混入标题：`## ？思考`/`## ?思考`/`## ? 思考`/`## ?` → `## 思考`
# 2) 标题前 emoji 图标（🎯探究与发现、🌍文献阅读与数学写作）→ 去除 emoji
# 判定依据：人教 A 版教材边栏图标是固定的几种（思考=问号、探究与发现=靶形、
# 文献阅读=地球），OCR 把图标识别成字符混进标题；教材原文标题不含图标字符。

def s13(md, book=""):
    n = 0
    md, k = re.subn(r"(?m)^(#{1,6}\s*)[？?]\s*(?:思考)?\s*$", r"\1思考", md)
    n += k
    md, k = re.subn("(?m)^(#{1,6}\\s*)[\U0001F300-\U0001FAFF\u2600-\u27BF]+\\s*", r"\1", md)
    n += k
    return md, n


# ===================== S15：页边图标清理 =====================
# 教材页边距的装饰图标：习题类别图标（复习巩固/综合运用/拓广探索）、思考问号、
# 探究/阅读与思考图标，共 270 张（47-72px 彩色小图，全 5 册）。
# 印在纸上时是小节标签旁的小装饰，线性渲染下浮为独立图片（用户截图报告）。
# 信息完全由紧随的标题/正文承载，移除引用并删除文件。
# 判据：image 类裁片且宽或高 < 100px。真插图最小约 150px，与图标（<=72px）
# 之间有明确间隔；equation_/table_/chart_ 类裁片不在此列（公式已转 LaTeX）。

def _jpeg_size(fp):
    """无依赖读取 JPEG 宽高（解析 SOFn 标记）；失败返回 None"""
    try:
        with open(fp, "rb") as f:
            if f.read(2) != b"\xff\xd8":
                return None
            while True:
                b = f.read(1)
                while b and b != b"\xff":
                    b = f.read(1)
                if not b:
                    return None
                marker = f.read(1)
                if not marker:
                    return None
                if marker in (b"\xc0", b"\xc1", b"\xc2", b"\xc3",
                              b"\xc5", b"\xc6", b"\xc7", b"\xc9", b"\xca", b"\xcb",
                              b"\xcd", b"\xce", b"\xcf"):
                    f.read(3)
                    h = int.from_bytes(f.read(2), "big")
                    w = int.from_bytes(f.read(2), "big")
                    return w, h
                if marker in (b"\xd8", b"\xd9") or b"\xd0" <= marker <= b"\xd7":
                    continue
                ln = int.from_bytes(f.read(2), "big")
                if ln < 2:
                    return None
                f.seek(ln - 2, 1)
    except Exception:
        return None


def s15(md, book="", imgdir=None, qroot=None):
    """页边图标清理（幂等）。

    image 类裁片中宽或高 <100px 的是页边装饰图标（习题类别/思考问号/探究图标），
    信息由紧随的标题/正文承载，移除引用并隔离文件（qroot 给定时移入隔离区而非删除）。
    幂等关键：流水线每轮从备份重建 md，但文件删除不可重做——若只按"现存文件"
    驱动，二轮重跑会因文件已删而漏清引用，留下悬空引用。故对 md 中引用了但
    文件已不存在（且非水印名单）的 image 类文件，同样清引用。

    ⚠️ 跨学科风险：<100px 阈值按人教 A 版数学书调优（页边装饰图标 47-72px）。
    化学/生物等册的装置示意图、元素符号小图可能同尺寸，须按科目校准
    （rules_pack 未接线前，用隔离区人工抽检实际清掉了什么）。"""
    n = 0
    if imgdir is None:
        raise ValueError("s12/s15 需要 imgdir 参数（由 run() 注入 <output_dir>/<book>/images）")
    icons = set()
    if os.path.isdir(imgdir):
        for f in os.listdir(imgdir):
            if re.match(r"page_\d+_image_\d+\.jpg$", f):
                sz = _jpeg_size(os.path.join(imgdir, f))
                if sz and max(sz) < 100:
                    icons.add(f)
    leftover = set()
    for f in set(re.findall(r"!\[[^\]]*\]\(images/(page_\d+_image_\d+\.jpg)\)", md)):
        if f not in icons and not os.path.exists(os.path.join(imgdir, f)) \
                and f not in WATERMARK.get(book, []):
            icons.add(f)
            leftover.add(f)
    if leftover:
        print("    [S15] %s 清理上轮已删图标的悬空引用 %d 处" % (book, len(leftover)))
    for f in sorted(icons):
        md, k = re.subn(r"(?m)^!\[[^\]]*\]\(images/%s\)[ \t]*\n" % re.escape(f), "", md)
        if k:
            fp = os.path.join(imgdir, f)
            if os.path.exists(fp):
                _quarantine_image(fp, imgdir, qroot)
            n += 1
    return md, n


# ============== S16：结构性损坏公式降级（跨学科必需，化学书实测引入） ==============
# 背景（2026-10-26 B4 化学书实战）：MinerU 对"双线桥电子转移标注""嵌套圈号/下标圈"
# 产出不可渲染的垃圾——嵌套 13 层 \textcircled、命令截断 \textc }、空 array 无限嵌套。
# KaTeX 必然报错 → html 门（要求 0 错误）永久失败，整册无法交付。
# 处置原则（守"PDF 是唯一事实源、不臆造内容"纪律）：
#   1) 整条公式降级为显式占位，原串写报告文件，供人工按 PDF 补录——引擎不猜内容；
#   2) 可安全判定的拆散形态（数字被 \; 拆开、裸 ^ 无基底）就地修复，如
#      1 \; 5 3 8 \; ^ { \circ } \mathrm { C } → 1538\,^{\circ}\mathrm{C}。
_BROKEN_FORMULA = re.compile(
    r"\\textcircled\s*\{\s*\\textcircled"     # 圈号嵌套 ≥2 层
    r"|\\textc\s*[}\s]"                       # 命令被截断（\textc }）
    r"|\\textcircled\s*\{\s*\\textc\s*\}"     # 退化为空圈号
)
_NESTED_EMPTY_ARRAY = re.compile(
    r"(?:\\begin\{array\}\s*\{\s*[lcr]\s*\}\s*){3,}"   # 连续 3 个以上 array 开头（{ l } 的带空格写法）
)
FORMULA_PLACEHOLDER_BLOCK = "> ⚠️ 〔此处公式 OCR 损坏、无法自动还原，已记入待补录清单〕"
FORMULA_PLACEHOLDER_INLINE = "〔公式损坏〕"


def s16(md, book="", report_path=None):
    """结构性损坏公式降级 + 可安全修复的拆散形态（幂等）。

    幂等性：占位文本不含 $ 与 \\textcircled，二次执行不再命中。
    返回 (md, (降级条数, 安全修复条数))。
    """
    n_broken, n_fixed = 0, 0
    records = []

    def _ctx(text, start, end):
        return text[max(0, start - 60):end + 60].replace("\n", " ")

    # ① 块公式 $$...$$
    def _fix_block(m):
        nonlocal n_broken
        body = m.group(0)
        if not (_BROKEN_FORMULA.search(body) or _NESTED_EMPTY_ARRAY.search(body)):
            return body
        n_broken += 1
        records.append(("block", body[:200], _ctx(md, m.start(), m.end())))
        return FORMULA_PLACEHOLDER_BLOCK

    md = re.sub(r"\$\$[\s\S]{0,4000}?\$\$", _fix_block, md)

    # ② 行内公式 $...$（跳过已降级的占位与 $$）
    def _fix_inline(m):
        nonlocal n_broken
        body = m.group(0)
        if not _BROKEN_FORMULA.search(body):
            return body
        n_broken += 1
        records.append(("inline", body[:200], _ctx(md, m.start(), m.end())))
        return FORMULA_PLACEHOLDER_INLINE

    md = re.sub(r"\$(?!\$)[^$\n]{0,600}?\$", _fix_inline, md)

    # ③ 安全修复：数字被 \; 拆散 → 合并；裸 ^ 无基底 → 删掉前面的 \; 让 ^ 贴住数字
    #    （注意不能补 \, 作基底：\, 是间距命令，不构成上标基底，KaTeX 仍报
    #     "Expected group after '^'"——首版曾误补 \, ，实测 4 处错误只降到 2 处）
    md, k1 = re.subn(r"(?<=[0-9])\s*\\;\s*(?=[0-9])", "", md)
    md, k2 = re.subn(r"\\;\s*\^", "^", md)
    n_fixed = k1 + k2

    if records and report_path:
        try:
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            with open(report_path, "w", encoding="utf-8") as fh:
                fh.write("# %s 结构性损坏公式（待按 PDF 补录）\n" % book)
                fh.write("# 格式：序号\t类型\t原串\t上下文\n")
                for i, (kind, src, ctx) in enumerate(records, 1):
                    fh.write("%d\t%s\t%s\t%s\n" % (i, kind, src.replace("\t", " "), ctx))
        except OSError as e:
            print("    [S16 警告] 报告写入失败 %s: %s" % (report_path, e))
    return md, (n_broken, n_fixed)


def run(books=None, source_dir=None, output_dir=None, quarantine_dir=None):
    """行为保持版入口（自 main() 参数化）。
    source_dir: 抽取基线目录（原 final_backup_20261022/），内含 <book>.markdown.md；
                单册缺失时回退读 output_dir 现有产物（幂等重跑，语义同原 main）。
    output_dir: 输出根，写 <output_dir>/<book>/markdown.md；
                s12/s15 的图片目录取 <output_dir>/<book>/images（与原 FINAL 布局一致）。
    quarantine_dir: 可选。给定则 s12/s15 清掉的裁片移入 <quarantine_dir>/<book>/
                （rename，可回溯），不给定则沿用删除。受保护环境必须给定：
                批量 unlink 会被安全策略拦截并中断流水线。
    返回 {book: {step: count}}；进度走 stderr（stdout 留给 CLI 的 JSON 信封）。
    """
    books = books or BOOKS
    if not source_dir or not output_dir:
        raise ValueError("run() 需要 source_dir 与 output_dir（参数化注入）")
    grand = {}
    for book in books:
        path = os.path.join(output_dir, book, "markdown.md")
        backup = os.path.join(source_dir, book + ".markdown.md")
        if os.path.exists(backup):
            md = open(backup, encoding="utf-8").read()  # 从备份干净重跑
        else:
            md = open(path, encoding="utf-8").read()    # 幂等：无备份则对现有产物重跑
        orig_len = len(md)
        imgdir = os.path.join(output_dir, book, "images")
        qroot = os.path.join(quarantine_dir, book) if quarantine_dir else None
        steps = {}
        for name, fn in [("S1正文标点", s1), ("S2符号误识", s2), ("S2b数学符号解包", s2b),
                         ("S3纯中文解包", s3), ("S4连接词拆分", s4), ("S4b二轮解包", s3),
                         ("S5单位修复", s5), ("S9伪块公式解包", s9), ("S6尾标点移出", s6)]:
            md, n = fn(md)
            steps[name] = n
        md, n10 = s10(md, book)
        steps["S10定点修复"] = n10
        md, n12 = s12(md, book, imgdir, qroot)
        steps["S12内容级修复"] = n12
        md, n13 = s13(md, book)
        steps["S13排版层修复"] = n13
        md, n15 = s15(md, book, imgdir, qroot)
        steps["S15页边图标清理"] = n15
        md, (n16b, n16f) = s16(md, book, os.path.join(output_dir, book, "broken_formulas.tsv"))
        steps["S16损坏公式降级"] = n16b
        steps["S16拆散形态修复"] = n16f
        md, removed = s7(md)
        steps["S7残留alt清理"] = removed
        md = s8(md)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w", encoding="utf-8").write(md)
        grand[book] = steps
        print("[%s] %d -> %d 字符 | %s" % (book, orig_len, len(md),
              " ".join("%s=%d" % (k, v) for k, v in steps.items() if v)), file=sys.stderr)
    print("=== A 档修复完成 ===", file=sys.stderr)
    return grand


if __name__ == "__main__":
    import argparse
    _p = argparse.ArgumentParser(description="行为保持版修复流水线（b2m run 的内核）")
    _p.add_argument("--source", required=True, help="抽取基线目录（含 <book>.markdown.md）")
    _p.add_argument("--output", required=True, help="输出根目录")
    _p.add_argument("books", nargs="*", help="册名列表，缺省为默认五册")
    _a = _p.parse_args()
    run(books=_a.books or None, source_dir=_a.source, output_dir=_a.output)
