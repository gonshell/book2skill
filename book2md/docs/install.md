# install.md — 安装手册与客户端依赖锁定

> 状态：2026-10-24 建档。客户端版本以"实测通过"为准；升级客户端依赖须重跑五册
> 行为保持对账（五册字符数逐字节一致 + 六道质量门）。

## 1. 客户端依赖锁定表

| 依赖 | 锁定值 | 核实方式 | 说明 |
|---|---|---|---|
| Python | **3.13.14**（要求 ≥3.13） | 实测（本项目钉死解释器） | 纯标准库实现，无 pip 依赖 |
| Node.js | **v22.22.2**（实测通过；最低版本未验证，暂按 v22 记录） | `node --version` | 仅用于 KaTeX 预渲染子进程 |
| KaTeX | **0.16.11**（资产快照**随包分发**） | `katex/katex.min.js` 内嵌版本串 | 含 auto-render + 20 字体；禁用 npm 运行时安装——版本漂移=渲染结果漂移 |
| MinerU（客户端） | **不安装** | — | 抽取走远程网关（docs/backend.md）；仅 `local-mineru` 回退适配器才需本机安装 |
| OS | Windows（实测）；其他平台未验证 | — | 路径处理已按 pathlib/UTF-8 设计 |

## 2. 安装步骤（三步）

```bash
# ① 环境：Python ≥3.13 + Node.js（见上表锁定值）
# ② 安装核心包
pip install -e textbook-pipe/           # 或发布后: pip install textbook-pipe
# ③ 验证 + 配置
tbp --version                           # 别名 tbpipe 等效
tbp config set workspace "D:/教材工作区"
tbp config set backend mineru-remote
```

技能壳安装（可选）：将 `skill-textbook-pipe/` 目录拷贝至
`~/.workbuddy/skills/textbook-pipe/`（前缀 `skill-` 仅仓库内区分用）。

## 3. 命名含义表（所有自造词）

| 名称 | 含义 |
|---|---|
| `textbook-pipe` | 包名；"pipe"=抽取→修复→渲染→质检全流水线 |
| `tbp` | CLI 命令（`tbpipe` 为过渡别名，行为一致） |
| `baselines/` | 基准样本集（golden master 惯用名的规范化用词） |
| `workspace` | 运行工作区：out/ 产物、overlays/ 裁定规则、blocks/ 缓存、ledger 账本 |
| Canonical Extraction | 抽取归一化契约（方案 §4.4.2），阶段 B 唯一输入格式 |

## 4. 工作区初始化

```bash
# 首本书接入（建目录树 + 科目配置模板 + 抽取 + 基线扫描）
tbp onboard --subject chem-renjiao --pdf "D:/教材/化学必修第一册.pdf"
# 科目配置不存在时会生成模板并以退出码 20 结束——编辑 configs 后重跑
```

## 5. 升级纪律

- 任何客户端依赖（Node/KaTeX 快照）变更 → 必须先 `tbp baseline run` → 再全量五册对账
- KaTeX 资产升级 = 渲染结果可能变化，视同后端升级对待（同走基准回归）
