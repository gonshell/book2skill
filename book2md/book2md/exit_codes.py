# -*- coding: utf-8 -*-
"""退出码常量（docs/spec-cli.md §3）。禁止在代码中使用裸数字退出码。"""
EXIT_OK = 0            # 成功（含非致命情况，用 warnings 表达）
EXIT_GATE_FAIL = 10    # 质量门未通过（失败不落盘）
EXIT_USAGE = 20        # 用法/配置错误（含依赖缺失、能力未接线）
EXIT_BACKEND = 30      # 抽取后端错误（网关不可达 / HTTP 错误 / 超时）
EXIT_CONTRACT = 40     # 契约违约（布局/schema/版本指纹/补丁缺失）
EXIT_MISSING = 50      # 输入文件不存在
