# -*- coding: utf-8 -*-
"""退出码常量（arch.md §8；语义沿用 book2md）。禁止在代码中使用裸数字退出码。"""
EXIT_OK = 0            # 成功（含非致命情况，用 warnings / issues 表达）
EXIT_GATE_FAIL = 10    # 质量闸未通过（graph 段：必填缺失 / id 重复）
EXIT_USAGE = 20        # 用法/配置错误（含未实现的 stage）
EXIT_CONTRACT = 40     # 契约违约（candidates 被手工改坏，字段类型不符）
EXIT_MISSING = 50      # 输入文件不存在（markdown.md / page_map.md 缺失）
