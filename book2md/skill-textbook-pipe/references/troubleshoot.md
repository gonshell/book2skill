# 质量门失败处置手册（references/troubleshoot.md）

按退出码与失败门定位。处理原则：**如实汇报，失败即停，不粉饰**。

## 退出码速查

| 码 | 含义 | 处置 |
|---|---|---|
| 0 | 成功 | 走 SKILL.md §2 交付流程 |
| 10 | 质量门未过 | 见下表按 error.gate 定位 |
| 20 | 配置缺失 | 按 error.code：NO_SUBJECT_CONFIG（编辑模板重跑）/ NO_BASELINE（先 baseline init）/ USAGE（改命令行） |
| 30 | 网关失败 | BACKEND_FAILED（看失败块，重跑断点续跑）/ NO_ENDPOINT / GATEWAY_UNREACHABLE（设 TBP_BACKEND_API；离线命令不受影响） |
| 40 | 契约违约 | baseline 漂移（逐指标差异在信封 drifts；先查后端版本是否变更再谈规则） |
| 50 | 资源缺失 | NO_BOOK / NO_CONTRACT / NO_DELIVERY：按 message 补前置步骤 |

## 质量门定位（error.gate）

| 门 | 常见原因 | 处置 |
|---|---|---|
| deps | 缺 Node / PIL / KaTeX 资产 | 跑 precheck.py 对号补装（版本见 docs/install.md） |
| fix | 规则包异常 | 看 stderr 首个异常栈；规则问题修核心包并对账，不临场绕过 |
| html / render | KaTeX 渲染错误 | 看 stderr 的公式错误列表；典型错识对照 ocr-patterns.md |
| selfcontain | 外部引用/字体缺失 | 通常资产问题；确认 KaTeX 快照完整 |
| preview | texmath 语义异常 | 记录到复核表；不影响产物，按需人工抽检 |
| scan3 | D1–D10 未归零 | 报告哪项未归零 → 对照 PDF 判定 → 规则缺陷修核心包，C 档进复核表 |
| toc | 报告/目录重生失败 | 看 stderr 栈；多为产物目录不完整 |

## staging 语义（重要）

`tbp run` 失败时产物留在 `out/<book>.staging/`，**上一版成功产物原样保留**
（晋升成功才轮换 `.prev-`）。排查时可检视 staging 中间产物定位失败门，
但不要手工修改 staging 内容后"凑合交付"——修复必须回到命令链路。
