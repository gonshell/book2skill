import ast, shutil, subprocess, sys
P = "/usr/local/lib/python3.12/dist-packages/mineru/model/ocr/image.py"
src = open(P, encoding="utf-8").read()
if "int(max(1.0, round(" in src:
    print("ALREADY-PATCHED, nothing to do"); sys.exit(0)
try:
    ast.parse(src)
except SyntaxError as e:
    print("DISK-FILE-BROKEN at line", e.lineno, ":", e.msg)
    import importlib.metadata
    v = importlib.metadata.version("mineru")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--force-reinstall",
                        "--no-deps", "mineru==" + v,
                        "-i", "https://mirrors.aliyun.com/pypi/simple"],
                       capture_output=True, text=True, timeout=900)
    print("PIP-RESTORE rc:", r.returncode, (r.stderr or "")[-300:])
    print("restore attempted -> please RE-RUN this same patch command")
    sys.exit(2)
pairs = [
 ("img_crop_width = int(max(np.linalg.norm(points[0] - points[1]), np.linalg.norm(points[2] - points[3])))",
  "img_crop_width = int(max(1.0, round(max(np.linalg.norm(points[0] - points[1]), np.linalg.norm(points[2] - points[3])))))"),
 ("img_crop_height = int(max(np.linalg.norm(points[1] - points[2]), np.linalg.norm(points[3] - points[0])))",
  "img_crop_height = int(max(1.0, round(max(np.linalg.norm(points[1] - points[2]), np.linalg.norm(points[3] - points[0])))))"),
]
n = 0
for old, new in pairs:
    if old in src:
        src = src.replace(old, new); n += 1
    else:
        print("MISS (whitespace/layout differs):", old[:70])
if n != 2:
    print("EXPECTED 2 LINES, GOT", n, "- stop without writing"); sys.exit(3)
ast.parse(src)
shutil.copy2(P, P + ".bak-prepatch")
open(P, "w", encoding="utf-8").write(src)
chk = open(P, encoding="utf-8").read()
ast.parse(chk)
print("PATCHED-LINES:", n, "| backup:", P + ".bak-prepatch")
r = subprocess.run([sys.executable, "-c", "import mineru.model.ocr.image"],
                   capture_output=True, text=True, timeout=600)
print("IMPORT-SMOKE:", "OK" if r.returncode == 0 else (r.stderr or "")[-300:])
if r.returncode != 0:
    shutil.copy2(P + ".bak-prepatch", P)
    print("ROLLED-BACK"); sys.exit(4)
print("PATCH-DONE")
