# -*- coding: utf-8 -*-
"""网关端点解析（docs/backend.md 契约：端点禁止硬编码）。

解析顺序：环境变量 TBP_BACKEND_API > ~/.tbp/config.json 的 backend_endpoint。
返回 None 表示未配置（调用方映射退出码 20）。
"""
import json
import os


def resolve_api():
    api = os.environ.get("TBP_BACKEND_API")
    if api:
        return api.rstrip("/")
    cfg = os.path.join(os.path.expanduser("~"), ".tbp", "config.json")
    if os.path.exists(cfg):
        try:
            val = json.load(open(cfg, encoding="utf-8")).get("backend_endpoint")
            if val:
                return str(val).rstrip("/")
        except Exception:
            pass
    return None
