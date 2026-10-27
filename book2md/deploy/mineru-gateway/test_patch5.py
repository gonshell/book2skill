# -*- coding: utf-8 -*-
"""本地验证 patch5（AST 级补丁）在各种 height 行写法下的行为。
做法：把 patch5 源码中的路径 P 替换为临时 mock 文件，fake 掉 subprocess，
exec 真实脚本代码路径，捕获 SystemExit 检查退出码与落盘结果。"""
import ast, os, sys, types, math, tempfile

SCRIPT = open("patch5_mineru_image.py", encoding="utf-8").read()

class FakeCompleted:
    returncode = 0
    stdout = "import OK\n"
    stderr = ""

class FakeSubprocess(types.ModuleType):
    def run(self, *a, **k):
        return FakeCompleted()

CONFIRMED_WIDTH = (
    "def get_rotate_crop_image(img, points):\n"
    "    img_crop_width = int(max(np.linalg.norm(points[0] - points[1]), np.linalg.norm(points[2] - points[3])))\n"
)
TAIL = (
    "    pts_std = np.float32([[0, 0], [w, 0], [w, h], [0, h]])\n"
    "    M = cv2.getPerspectiveTransform(points, pts_std)\n"
    "    return cv2.warpPerspective(img, M, (w, h))\n"
)
HEIGHT_VARIANTS = {
    "A-原猜测": "    img_crop_height = int(max(np.linalg.norm(points[1] - points[2]), np.linalg.norm(points[3] - points[0])))\n",
    "B-顺序交换": "    img_crop_height = int(max(np.linalg.norm(points[3] - points[0]), np.linalg.norm(points[1] - points[2])))\n",
    "C-无空格": "    img_crop_height = int(max(np.linalg.norm(points[1]-points[2]),np.linalg.norm(points[3]-points[0])))\n",
    "D-尾注释": "    img_crop_height = int(max(np.linalg.norm(points[1] - points[2]), np.linalg.norm(points[3] - points[0])))  # noqa\n",
    "E-多行换行": "    img_crop_height = int(\n        max(np.linalg.norm(points[1] - points[2]), np.linalg.norm(points[3] - points[0])))\n",
    "F-逗号索引": "    img_crop_height = int(max(np.linalg.norm(points[1, :] - points[2, :]), np.linalg.norm(points[3, :] - points[0, :])))\n",
    "G-变量名错(应失败)": "    crop_height = int(max(np.linalg.norm(points[1] - points[2]), np.linalg.norm(points[3] - points[0])))\n",
}

def run_case(label, height_line):
    tmpdir = tempfile.mkdtemp()
    mock = os.path.join(tmpdir, "image.py")
    open(mock, "w", encoding="utf-8").write(CONFIRMED_WIDTH + height_line + TAIL)
    code = SCRIPT.replace('P = "/usr/local/lib/python3.12/dist-packages/mineru/model/ocr/image.py"',
                          'P = %r' % mock)
    g = {"__name__": "__main__"}
    real_sub = sys.modules.get("subprocess")
    sys.modules["subprocess"] = FakeSubprocess("subprocess")
    try:
        exec(compile(code, "patch5", "exec"), g)
        rc = 0
    except SystemExit as e:
        rc = e.code
    finally:
        if real_sub is not None:
            sys.modules["subprocess"] = real_sub
    patched = open(mock, encoding="utf-8").read()
    try:
        ast.parse(patched)
        parse = "OK"
    except SyntaxError as e:
        parse = f"FAIL@{e.lineno}"
    n = patched.count("int(max(1.0, round(")
    # clamp 数学验证：从落盘结果提取两个赋值并求值
    class V:
        def __init__(s, x, y): s.x, s.y = x, y
        def __sub__(s, o): return V(s.x - o.x, s.y - o.y)
    NP = types.SimpleNamespace(linalg=types.SimpleNamespace(norm=staticmethod(lambda v: math.hypot(v.x, v.y))))
    def ev(expr, pts):
        return eval(expr, {"__builtins__": {}}, {"int": int, "max": max, "round": round, "np": NP, "points": pts})
    deg  = [V(10, 10)] * 4
    norm = [V(0, 0), V(30, 0), V(30, 10), V(0, 10)]
    math_ok = "-"
    if n == 2 and parse == "OK":
        w_line = [l for l in patched.split("\n") if l.strip().startswith("img_crop_width")][0]
        h_line = [l for l in patched.split("\n") if l.strip().startswith("img_crop_height")][0]
        try:
            vw0, vw1 = ev(w_line.split("=", 1)[1], deg), ev(w_line.split("=", 1)[1], norm)
            vh0, vh1 = ev(h_line.split("=", 1)[1], deg), ev(h_line.split("=", 1)[1], norm)
            math_ok = f"deg=({vw0},{vh0}) norm=({vw1},{vh1})" + (" ✔" if (vw0, vh0) == (1, 1) and (vw1, vh1) == (30, 10) else " �’")
        except Exception as ex:
            math_ok = f"EVAL-FAIL {ex}"
    print(f"[{label:14s}] exit={rc} clamps={n} parse={parse} math={math_ok}")

for label, line in HEIGHT_VARIANTS.items():
    run_case(label, line)
