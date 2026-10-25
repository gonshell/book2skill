# -*- coding: utf-8 -*-
"""tbp config — 用户配置管理（docs/spec-cli.md §6.1）。"""
import json
import os
import sys

from textbook_pipe.exit_codes import EXIT_OK, EXIT_USAGE
from textbook_pipe.commands._envelope import emit

CONFIG_KEYS = ("workspace", "backend", "backend_endpoint", "subjects")
VALID_BACKENDS = ("mineru-remote", "local-mineru", "manual")


def _config_path():
    return os.path.join(os.path.expanduser("~"), ".tbp", "config.json")


def _load():
    p = _config_path()
    if not os.path.exists(p):
        return {}
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        backup = p + ".bak-" + str(int(os.path.getmtime(p)))
        os.replace(p, backup)  # 损坏配置备份后按空配置继续（spec §6.1）
        print("!! 配置文件损坏，已备份为 %s，按空配置继续" % backup, file=sys.stderr)
        return {}


def execute(args, t0):
    cfg = _load()
    cp = _config_path()
    if args.action == "path":
        return emit("config", EXIT_OK, artifacts={"config_path": cp}, t0=t0)
    if args.action == "get":
        data = cfg if not args.key else {args.key: cfg.get(args.key)}
        return emit("config", EXIT_OK, artifacts={"config": data, "config_path": cp}, t0=t0)
    # set
    key, value = args.key, args.value
    if key not in CONFIG_KEYS:
        return emit("config", EXIT_USAGE,
                    error={"code": "BAD_KEY", "message": "未知配置键 %r（可选：%s）" % (key, ", ".join(CONFIG_KEYS))},
                    t0=t0)
    if key == "backend" and value not in VALID_BACKENDS:
        return emit("config", EXIT_USAGE,
                    error={"code": "BAD_BACKEND", "message": "backend 取值须为：%s" % ", ".join(VALID_BACKENDS)},
                    t0=t0)
    if key == "subjects":
        value = [s.strip() for s in value.split(",") if s.strip()]
    if key == "workspace":
        if not os.path.isdir(value):
            return emit("config", EXIT_USAGE,
                        error={"code": "BAD_WORKSPACE", "message": "workspace 目录不存在且不可创建: %s" % value},
                        t0=t0)
    cfg[key] = value
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    json.dump(cfg, open(cp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return emit("config", EXIT_OK, artifacts={"config": cfg, "config_path": cp}, t0=t0)
