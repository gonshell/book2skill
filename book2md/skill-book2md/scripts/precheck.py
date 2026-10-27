#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""技能壳脚本：环境预检（SKILL.md §0）。

检查项：b2m 可用性 / Node.js / KaTeX 资产随包 / 工作区可写；端点可达性可选。
只做检查与汇报，不做任何转换动作。输出 JSON 信封（与核心包同纪律）。

用法：
    python precheck.py [--workspace <路径>] [--check-endpoint]

退出码：0 全部通过 · 20 必要项缺失 · 30 端点不可达（仅 --check-endpoint 时）。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

EXIT_OK = 0
EXIT_CONFIG = 20
EXIT_BACKEND = 30


def _emit(payload, exit_code, t0):
    payload.update({"cmd": "precheck", "ok": exit_code == 0, "exit_code": exit_code,
                    "elapsed_sec": round(time.time() - t0, 2)})
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return exit_code


def _sh(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                           encoding="utf-8", errors="replace")
        return r.returncode, (r.stdout or r.stderr or "").strip().splitlines()
    except (OSError, subprocess.TimeoutExpired) as ex:
        return None, [str(ex)]


def _probe_endpoint(endpoint):
    """探活网关：/v1/health（官方 mineru-kit）优先，回退 /version（自研 wrapper）。

    返回 (ok, detail)。detail 带版本号，便于与 extract 账本指纹对照。
    """
    import urllib.error
    import urllib.request

    last = ""
    for path in ("/v1/health", "/version"):
        url = endpoint.rstrip("/") + path
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                body = resp.read(400).decode("utf-8", "replace")
            try:
                payload = json.loads(body)
                ver = payload.get("version") or payload.get("data", {}).get("version")
            except ValueError:
                ver = None
            return True, "%s%s -> 200%s" % (endpoint, path, (" version=%s" % ver) if ver else "")
        except (urllib.error.URLError, OSError, ValueError) as ex:
            last = "%s%s -> %s" % (endpoint, path, ex)
    return False, last


def main():
    t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace")
    ap.add_argument("--check-endpoint", action="store_true")
    args = ap.parse_args()

    checks = []

    def add(name, ok, detail, hint=None, fatal=True):
        checks.append({"name": name, "ok": bool(ok), "detail": detail,
                       **({"hint": hint} if hint else {}), "fatal": fatal})

    # ① b2m 命令可用（import 路径与入口双重验证）
    rc, out = _sh([sys.executable, "-c",
                   "import book2md, sys; print(book2md.__file__)"])
    add("b2m_import", rc == 0, out[0] if out else "",
        hint="pip install book2md（见 docs/install.md）" if rc != 0 else None)
    b2m_exe = shutil.which("b2m") or shutil.which("b2m.exe")
    if not b2m_exe:
        # 兜底：venv 里 pip install -e 生成的入口与解释器同目录，但该目录可能不在 PATH
        cand = os.path.join(os.path.dirname(sys.executable), "b2m.exe")
        if not os.path.exists(cand):
            cand = os.path.join(os.path.dirname(sys.executable), "b2m")
        b2m_exe = cand if os.path.exists(cand) else None
    # 入口缺失不致命：import 成功时 python -m book2md.cli 等价可用
    add("b2m_entry", b2m_exe is not None, b2m_exe or "未找到（可用 python -m book2md.cli 等价调用）",
        hint="pip install book2md 后 b2m 入口进 PATH" if not b2m_exe else None, fatal=False)

    # ② Node.js ≥ 22（KaTeX 预渲染依赖）
    rc, out = _sh(["node", "--version"])
    ver = out[0] if rc == 0 and out else ""
    try:
        ok = rc == 0 and tuple(int(x) for x in ver.lstrip("v").split(".")) >= (22,)
    except ValueError:
        ok = False
    add("node", ok, ver or "未找到",
        hint="安装 Node.js ≥22（版本锁定见 docs/install.md）" if not ok else None)

    # ③ KaTeX 资产随包（css + 字体 + 渲染脚本）
    rc, out = _sh([sys.executable, "-c",
                   "import os, book2md.engine.render as r;"
                   "print(os.path.exists(os.path.join(r.KATEX_DIR, 'katex.min.css')));"
                   "print(len(os.listdir(os.path.join(r.KATEX_DIR, 'fonts'))));"
                   "print(os.path.exists(r.RENDER_JS))"])
    if rc == 0 and len(out) >= 3:
        add("katex_assets", out[0] == "True" and int(out[1]) >= 20 and out[2] == "True",
            "css=%s fonts=%s js=%s" % (out[0], out[1], out[2]),
            hint="重装包（package-data 应随 wheel 分发）" if out[0] != "True" else None)
    else:
        add("katex_assets", False, "探测失败", hint="检查 book2md.engine.render 可导入")

    # ④ 工作区解析与可写
    ws = args.workspace or os.environ.get("B2M_WORKSPACE") or os.getcwd()
    try:
        probe = os.path.join(ws, ".b2m_probe")
        os.makedirs(ws, exist_ok=True)
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("ok")
        os.remove(probe)
        add("workspace_writable", True, ws)
    except OSError as ex:
        add("workspace_writable", False, "%s: %s" % (ws, ex),
            hint="b2m config set workspace <可写路径>")

    # ⑤ 端点可达（可选，失败仅警告不致命）
    # 解析走核心包 resolve_api()（无参：环境变量 > ~/.book2md/config.json），
    # 探活走 /v1/health（版本端点；/version 在官方 mineru-kit 上不存在），
    # 回退 /version 兼容自研 wrapper。
    endpoint_rc = None
    if args.check_endpoint:
        rc, out = _sh([sys.executable, "-c",
                       "from book2md.commands._endpoints import resolve_api;"
                       "print(resolve_api() or '')"])
        endpoint = out[0] if rc == 0 and out else ""
        if not endpoint:
            add("endpoint", False, "未配置",
                hint="设 B2M_BACKEND_API 或 b2m config set backend_endpoint",
                fatal=False)
        else:
            ok, detail = _probe_endpoint(endpoint)
            endpoint_rc = 0 if ok else 30
            add("endpoint", ok, detail,
                hint="网关不可达：离线命令（run/scan/report）仍可用，抽取/基准重抽不可用",
                fatal=False)

    fatal_bad = [c for c in checks if not c["ok"] and c["fatal"]]
    exit_code = EXIT_OK if not fatal_bad else EXIT_CONFIG
    if args.check_endpoint and exit_code == EXIT_OK and endpoint_rc not in (0, None):
        exit_code = EXIT_BACKEND
    return _emit({"checks": checks, "workspace": ws}, exit_code, t0)


if __name__ == "__main__":
    sys.exit(main())
