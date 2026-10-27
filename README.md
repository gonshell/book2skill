# book2skill

教材 → 教学能力的工具集合。每个子目录是一个自包含模块（独立 Python 包、独立 CLI、
独立测试与技能壳），彼此不共享运行时代码。

## 模块

| 目录 | 名称 | 职责 | 版本 |
|---|---|---|---|
| [`book2md/`](book2md/) | **book2md** | 教材 PDF → Markdown + 图片 + 公式 → 双版本单体 HTML（阅读版 / 知识库版） | v0.3.2 |

`book2md` 的前身是 `textbook-pipe`（2026-10-27 更名并迁入本仓库）。它的历史记录
（CHANGELOG 0.1.0/0.2.0、QA 台账销项过程）保留原名，见
[book2md/CHANGELOG.md](book2md/CHANGELOG.md) 与 [book2md/docs/qa-ledger.md](book2md/docs/qa-ledger.md)。

## 快速开始

```bash
git clone <本仓库>
cd book2md
pip install -e .          # 需要 Python ≥ 3.13
b2m --version             # → b2m (book2md) 0.3.2
b2m config set workspace /path/to/workspace
b2m config set backend_endpoint http://<网关地址>:8000   # 教材抽取网关（MinerU）
```

渲染需要系统安装 Node.js ≥ 22；KaTeX 资产随包分发，无需另装。
完整命令说明见 [book2md/docs/spec-cli.md](book2md/docs/spec-cli.md)，
网关部署见 [book2md/docs/mineru-selfhost.md](book2md/docs/mineru-selfhost.md)。

> ⚠️ 在**本仓库根目录**执行 `python -m book2md.cli` 会失败——根下的 `book2md/`
> 目录名与包名相同，Python 会先把它当 namespace package。用 `b2m` 命令即可（不受
> 工作目录影响），或先 `cd book2md` 再用 `python -m book2md.cli`。

## 测试

```bash
cd book2md
bash run_tests.sh                                      # 69 例，纯本地，约 1 分钟
B2M_PARITY_SOURCE=/path/to/history bash run_tests.sh   # 追加 5 套行为保持对账，约 20 分钟
```

两点说明：

- **对账测试**需要一份历史产物目录（`markdown.md` + 双版 HTML + 图片）作裁判，
  它不在本仓库里（内含教材原文）。没有就自动跳过，不影响其他测试。
- **抽取契约测试**的一个样例是网关真实返回的 zip，同样因含教材原文而不入库；
  缺失时该套测试跳过。可自行对任意 PDF 跑一次抽取后放回
  `tests/fixtures/blocks/<册名>/`（格式见 [tests/fixtures/README.md](book2md/tests/fixtures/README.md)）。

## 约定

1. **命名**：`book2<产物形态>`——`book2md`（转 Markdown/HTML），未来的 `book2quiz`
   （出题）、`book2slides`（课件）等。名字直接说明输入与输出。
2. **模块边界**：一个模块 = 一个 Python 包 + 一套 CLI + 一份 `AGENT.md` + 一套测试。
   模块之间不直接 `import`；跨模块协作走文件产物或显式接口。
3. **不入库的东西**：教材原件、抽取产物（`out/` `blocks/` `baselines/`）、含教材原文的
   测试样例。数据一律留在本地 workspace。
4. **新增模块**前先在本文档的模块表登记一行，写明职责与状态。

## 环境基准

Python 3.13 / Node.js 22。各模块依赖锁定见其 `docs/install.md`。

## 许可证

[MIT](LICENSE)。仅授权代码本身；教材原文版权归原出版方，使用本工具处理教材
不改变教材的版权归属。
