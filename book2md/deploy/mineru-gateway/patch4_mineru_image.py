import ast, re, shutil, subprocess, sys
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

def patch_name(src, name):
    rx = re.compile(
        r"^(?P<indent>[ \t]*)" + name + r"[ \t]*=[ \t]*int\(max\((?P<inner>.+)\)\)[ \t]*(?:#.*)?$",
        re.M)
    def _sub(m):
        new = m.group("indent") + name + " = int(max(1.0, round(max(" + m.group("inner") + "))))"
        print("OLD:", m.group(0).strip())
        print("NEW:", new.strip())
        return new
    out, n = rx.subn(_sub, src)
    return out, n

total = {}
for name in ("img_crop_width", "img_crop_height"):
    src, n = patch_name(src, name)
    total[name] = n
    print(name, "patched:", n)
if total["img_crop_width"] < 1 or total["img_crop_height"] < 1:
    print("MISS SOMETHING:", total, "- dump lines 88-106 and stop")
    for i, ln in enumerate(src.split("\n")[87:106], start=88):
        print(f"{i:4d}| {ln}")
    sys.exit(3)
ast.parse(src)
shutil.copy2(P, P + ".bak-prepatch")
open(P, "w", encoding="utf-8").write(src)
chk = open(P, encoding="utf-8").read()
ast.parse(chk)
print("WRITTEN | backup:", P + ".bak-prepatch")
r = subprocess.run([sys.executable, "-c", "import mineru.model.ocr.image"],
                   capture_output=True, text=True, timeout=600)
print("IMPORT-SMOKE:", "OK" if r.returncode == 0 else (r.stderr or "")[-300:])
if r.returncode != 0:
    shutil.copy2(P + ".bak-prepatch", P)
    print("ROLLED-BACK"); sys.exit(4)
print("PATCH-DONE")
