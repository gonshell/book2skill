# conventions.md — 命名与编码规范（搬迁与后续开发的强制标准）

> 状态：2026-10-24 v1.0。依据：用户要求"开始下一步之前做好文件名命名规则、规范开发"。
> 本文件对**所有在本仓库工作的 AI 与人**生效（AGENT.md §1.4 缰绳的本体）；
> 违反 = 评审打回。与 AGENT.md 冲突时以本文件为准。

## 1. 总原则

1. **行为保持优先**：搬迁期任何"顺手改进"（改名、重构、优化）都算违约——
   本文件规范的是**新写的代码**（CLI、适配器、配置层）；搬迁的引擎代码除
   参数化所必需的最小改动外保持原样。
2. 纯 Python 标准库；Python 3.13；Node 仅经 subprocess 调用且必须显式超时。
3. 术语纪律：口语比喻词（体检/黄金/钉死/兜底/跑通等）禁止进入代码、注释、文档。

## 2. 文件与目录命名

| 对象 | 规则 | 示例 |
|---|---|---|
| 包/目录 | 小写 snake_case，职责名词 | `engine/` `extractors/` `packs/math/` |
| Python 模块 | snake_case，一个模块一个职责 | `fix_rules.py` `render.py` `reporting.py` `cli.py` `config.py` |
| 探测器模块 | `inspectors/d<编号>_<语义>.py` | `inspectors/d2_set_notation.py` |
| 测试 | `tests/test_<被测模块名>.py` | `tests/test_fix_rules.py` |
| 科目配置 | `configs/<学科>-<出版社/版本>.json`，kebab-case | `configs/math-renjiao-a.json` `configs/chem-renjiao.json` |
| 后端配置 | `configs/backends/<backend-id>.json` | `configs/backends/mineru-remote.json` |
| 文档 | `docs/` 下 kebab-case 英文文件名 | `spec-cli.md` `install.md` `backend.md` |
| 书 id（工作区数据） | = PDF 文件名去扩展名，**允许中文** | `化学必修第一册` |
| 工作区产物 | 程序生成，沿用现引擎物理页命名规则，搬迁不改 | `out/<book>/images/…` |

禁止：拼音缩写（`jiaocai/` `xzbx2/`）、大写混排（`FixMd.py`）、空格与中文文件名
进**仓库代码区**（工作区数据区不受此限）。

## 3. 代码命名

| 对象 | 规则 | 示例 |
|---|---|---|
| 函数/变量 | snake_case 英文，动词开头 | `run_quality_gates()` `parse_page_range()` |
| 类 | PascalCase | `RemoteMinerUAdapter` `BaselineRunner` |
| 常量 | UPPER_SNAKE | `DEFAULT_TIER` `GATE_ORDER` |
| 私有成员 | 前置下划线 | `_load_ledger()` |
| 退出码 | 常量枚举，禁止裸数字 | `EXIT_GATE_FAIL`（=10） |
| 规则四元组 | 数据结构，**名称字段可用中文**（数据≠标识符，沿用 fix_md 现状） | `("花体字母→正解", …)` |

禁止：单字母名（数学循环变量 i/j/k 除外）、`temp/data/foo` 类无义名、裸魔数。

## 4. 语言策略

- **标识符**：英文。
- **docstring / 注释 / commit message**：中文（面向中文团队）；LaTeX、API 参数名等
  原文保留。
- **文档**：中文；文件名英文 kebab-case。

## 5. 代码风格（硬性）

1. 公开函数必须有类型注解 + docstring（中文，含 Args/Returns/ Raises）。
2. 路径一律 `pathlib.Path`；`open()` 读写**一律显式** `encoding="utf-8"`。
3. 日志/进度 → **stderr**；stdout 只准写 JSON 信封（docs/spec-cli.md §5）——
   禁止 `print()` 调试输出入库。
4. 标准库 only：`os/re/sys/json/pathlib/argparse/subprocess/hashlib/logging/…`；
   引入任何第三方依赖 = 需用户批准的架构变更。
5. subprocess 调 Node 必须 `timeout=`；网络调用必须超时 + 退避（继承 run_blocks 策略）。
6. 所有命令实现为纯函数式的"解析参数 → 执行 → 返回信封 dict"结构，便于测试。

## 6. 测试约定（为将来验收预留，欠账见 AGENT.md）

- 测试框架：标准库 `unittest`（不引第三方）。
- 每条新增正则规则必须带**覆盖备份真实形态**的用例（S20 吞括号教训）；
- 行为保持对账脚本 `tests/test_behavior_parity.py`：五册字符数基线比对——
  搬迁每步的施工准绳。

## 7. Git 约定

- commit message：`type(scope): 中文摘要`，type ∈ `feat|fix|docs|refactor|test|chore`；
  搬迁类注明源文件（如 `feat(engine): 搬迁 fix_md.py → fix_rules.py（自 gzsx-md，行为保持）`）。
- **一模块一 commit**（搬迁期铁律），可单独回滚与二分。
- 分支：单人开发 main 直提交；有回归疑虑开 `fix/…` 修完合回。

## 8. 版本

- SemVer；唯一来源 = `pyproject.toml` 的 `version`；
- `v0.1.0` = P1 验收（五册对账全绿，验收方式届时由用户解冻欠账决定）。
