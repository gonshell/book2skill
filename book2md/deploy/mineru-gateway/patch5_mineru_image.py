import ast, shutil, subprocess, sys
P = "/usr/local/lib/python3.12/dist-packages/mineru/model/ocr/image.py"
src = open(P, encoding="utf-8").read()
if "int(max(1.0, round(" in src:
    print("ALREADY-PATCHED, nothing to do"); sys.exit(0)
try:
    tree = ast.parse(src)
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

WANT = ("img_crop_width", "img_crop_height")
hits = []
for node in ast.walk(tree):
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        continue
    tgt = node.targets[0]
    if not isinstance(tgt, ast.Name) or tgt.id not in WANT:
        continue
    val = node.value
    ok_shape = (isinstance(val, ast.Call) and isinstance(val.func, ast.Name)
                and val.func.id == "int" and len(val.args) == 1
                and isinstance(val.args[0], ast.Call) and isinstance(val.args[0].func, ast.Name)
                and val.args[0].func.id == "max" and len(val.args[0].args) == 2)
    if not ok_shape:
        print("UNEXPECTED-SHAPE:", tgt.id, "- not int(max(a, b))")
        continue
    inner = ast.get_source_segment(src, val.args[0])
    if inner is None:
        print("CANNOT-EXTRACT-SOURCE:", tgt.id)
        continue
    hits.append((tgt.id, node.lineno, node.end_lineno, inner))

print("FOUND:", [(n, a, b) for n, a, b, _ in hits])
names = [h[0] for h in hits]
if "img_crop_width" not in names or "img_crop_height" not in names:
    print("MISS-WIDTH-OR-HEIGHT -> dump lines 88-106 and stop")
    for i, ln in enumerate(src.split("\n")[87:106], start=88):
        print(f"{i:4d}| {ln}")
    sys.exit(3)

lines = src.split("\n")
for name, a, b, inner in sorted(hits, key=lambda h: h[1], reverse=True):
    first = lines[a - 1]
    indent = first[:len(first) - len(first.lstrip())]
    new_stmt = indent + name + " = int(max(1.0, round(" + inner + ")))"
    print("REPLACE lines %d-%d:" % (a, b))
    print("  OLD:", " ".join(x.strip() for x in lines[a - 1:b])[:130])
    print("  NEW:", new_stmt.strip()[:130])
    lines[a - 1:b] = [new_stmt]
new_src = "\n".join(lines)
ast.parse(new_src)
shutil.copy2(P, P + ".bak-prepatch")
open(P, "w", encoding="utf-8").write(new_src)
chk = open(P, encoding="utf-8").read()
ast.parse(chk)
cnt = chk.count("int(max(1.0, round(")
print("WRITTEN | clamp-count:", cnt, "| backup:", P + ".bak-prepatch")
if cnt < 2:
    print("COUNT-TOO-LOW - rollback")
    shutil.copy2(P + ".bak-prepatch", P)
    sys.exit(4)
r = subprocess.run([sys.executable, "-c", "import mineru.model.ocr.image"],
                   capture_output=True, text=True, timeout=600)
print("IMPORT-SMOKE:", "OK" if r.returncode == 0 else (r.stderr or "")[-300:])
if r.returncode != 0:
    shutil.copy2(P + ".bak-prepatch", P)
    print("ROLLED-BACK"); sys.exit(5)
print("PATCH-DONE")
