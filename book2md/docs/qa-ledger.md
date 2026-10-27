# 待确定事项台账（统一记录，2026-10-25 建档）

> 本台账汇总待确定项与销项记录：`AGENT.md` 欠账台账、【MinerU 侧面】
> （现见 [mineru-selfhost.md](mineru-selfhost.md) §8）、工作记忆暂停点。
> 销一项划一项（改为 ✅ 并注明日期）。2026-10-27 归档入库本仓库 `docs/`。
>
> **提醒义务（2026-10-27 口径）**：AI 在任何阶段性交付时必须主动提醒——
> "内容保真关口只在渲染与结构层；与原书一致性靠人工抽检，E 队列未清零前
> 产物不得定稿发布"，即使用户没有问。（原"系统级通测/联调/网关侧未实测"
> 口径因实测已完成而废止，见 AGENT.md。）

---

## A. 立即待办（纯本地可做，**停在等用户裁定**）

| # | 事项 | 状态 | 待确定内容 |
|---|---|---|---|
| A1 | 系统级 run 通测（路线图阶段 A-5） | ✅ **已完成（2026-10-26）** | 用户裁定"全删只留结论"。五册纯本地通测：extract 契约（final_backup_20261022 基线 + final images 直通）→ `tbp run` 六门全绿 → 与 final 逐字节比对 **markdown/images/阅读版HTML/知识库版HTML 全部 SAME**；质检报告数值与 final 完全一致；TOC 逐节一致。发现并修复缺口：run 补生 page_map.md（commit 13986c1，内容与 final 逐字一致，legacy 该文件 LF 为历史异常口径，tbp 统一 CRLF）。临时产物已全部删除（`_tmp_tbp_run_e2e/` 归零）。**阶段 A 全部完成**。 |
| A2 | 引擎演进后的基线漂移登记（B4 副作用处置） | ✅ **2026-10-26 完成** | B4 修的两个跨学科缺口会改变数学书产物，实测漂移量 **9 行**且与规则命中数一一对应（`rules` 段 5 行 = S16③ 修 OCR 拆散数字 7 处，如 `1.414\;3→1.4143`、`0.062\;5→0.0625`；`merge` 段 4 行 = 表格 `src=` 引用同步改写，历史值经核实为悬空：真实文件 `page_261_…` vs 历史引用 `page_135_…`）。其余三册仍逐字节一致，**修读版/知识库版 HTML 对账仍全绿**（白名单只涉及 md 层）。处置：`tests/parity_util.py` + `tests/fixtures/parity_delta_allowlist.json` 逐行登记，除登记项外任何差异仍判失败（已用三类反例验证判据有效）。新增 `tests/test_s16_and_inline_tags.py` 13 例锁死规则行为。**下次整册重跑刷新 final 基线时清空该文件即可**。 |

> 强制提醒：A1 结论中的"逐字节 SAME"成立于 B4 之前；B4 之后口径为「除 9 行已声明改动外逐字节一致」，见 A2。

## B. 网关恢复后销账（<网关地址>，路线图阶段 B）

| # | 事项 | 状态 | 备注 |
|---|---|---|---|
| B1 | extract 实抽联测（真实抽取全链路） | ✅ **2026-10-26 完成** | trial_选择性必修第一册_p51-57.pdf 走真实网关 22s 抽取成功；对修复前基线相似度 98.75%（差异为个别标点 OCR 漂移）；zip 契约 md↔图片 0 缺失；孤儿图片为网关固有行为（历史块 87/164 同现象）；册名防呆（--book 与 PDF 文件名不一致以文件名为准）实测生效 |
| B2 | `tbp baseline run` 基准回归重抽比对 | ✅ **2026-10-26 完成**（试验册全链路） | init→run→RC 40 三态正确触发。**关键发现：MinerU 同版本重抽图片裁片数有 run 间波动（D10 18↔21），字符指标稳定（±0.5% 内）**——图片数量类指标天然有噪声，字符才是稳定锚点；本条的"整册基线需原始整书 PDF"已由 B5 用化学书整册销账（不需另供 PDF）。指纹全 null（/version 404） |
| B3 | MinerU 精确版本确定 | ✅ **2026-10-26 完成（远程核实）** | 网关 `/v1/health` 返回 `version: 4.0.12`，`/v1/tiers`、`/v1/models` 三处一致；wrapper 为 FastAPI（API 1.0.0，19 端点，无 `/version`，版本在 `/v1/health`）；已回填手册 §2.4/§6.3/§7.1 与 backend.md §3 |
| B4 | 化学书实战（第一本化学教材端到端） | ✅ **2026-10-26 完成** | onboard 网关真实抽取 139 页 → `tbp run` 七门全绿（deps/fix/html/selfcontain/render/preview/scan3/toc），产物齐全（阅读版+知识库版各 11.5 MB 单体 HTML、315 图、TOC 268 条、page_map 121 页、provenance 保留）。视觉抽检 5 处（顶部/氧化还原/实验室制气/侯氏制碱/元素周期表）公式与表格渲染正常。实战暴露并修复 **3 个引擎缺口**：① merge 二次偏移漏改 HTML 表格 `src=` 引用（补同步改写，32 引用 0 缺失）；② 抽取层结构性损坏公式（嵌套 textcircled/空 array 无限嵌套/度数拆散）新增 S16 降级通道 + broken_formulas.tsv 待补录清单；③ md2html 转义打露原生 `<sup>/<sub>/<u>` 标签（转义白名单放行，74 处恢复真上下标）。遗留：TOC 8 条标题 OCR 噪音（3%）+ 2 条损坏公式待按 PDF 人工补录 |
| B5 | 整册 baseline 实测（139 页整册，非切片） | ✅ **2026-10-26 完成** | **不需另供 PDF**：直接用 B4 化学书整册（139 页 / 20 MB，账本 `total_pdf_pages=139`）作素材。init 抽样按科目配置覆盖 4 个抽取块（7-46 / 47-86 / 87-126 / 127-139；默认首中尾抽样只命中 3 块、漏掉表内图最密集的 87-126）→ 重抽 4 块（6m46s）→ **`status 一致` RC=0**，4 块字符 / 探测器 / KaTeX 全部命中基线，指纹未漂移。**实测暴露并修复两个测量口径缺陷**：① `_measure` 临时目录不带图片 → 所有引用误判 D10 悬空（22 处）+ 缺图 144，改为只复制 text 实际引用的图；② init 基线取自 out/ 的**修复后**产物，run 比的却是**未过 S 规则**的重抽原始产物 → 假漂移（7-46 +7.4% / 87-126 +13.0% / 127-139 +67.0%，D7 标签泄漏 0→23，KaTeX 0→3），改为 run 侧同样过 S1–S20 再测。附证：重抽 raw 字符数与历史 raw **精确相同**（34334 / 38538 / 17362），即抽取内容确定性到字符级。新增 `tests/test_baseline_smoke.py::BaselineMeasureParity` 2 例锁死口径。注：`/v1/file_parse` 在沙箱内被网络层拦成 403（响应体为空、三次重试同）——须在沙箱外跑。 |

## C. MinerU 手册 §8 待核实（2026-10-26 **六项全部销账**）

| # | 待确认项 | 状态 | 核实方式与结论 |
|---|---|---|---|
| C1 | MinerU 精确版本号 | ✅ **4.0.12** | 远程 `curl /v1/health`（`/v1/tiers`、`/v1/models` 三处一致） |
| C2 | 8 个模型权重 sha256 | ✅ **8/8** | ModelScope API `repo/files`，全量回填手册 §3.2 |
| C3 | GPU 型号 / 显存 / 驱动 | ✅ **核实** | `nvidia-smi`：**2 × TITAN X (Pascal) 12 GB**，驱动 **535.309.01**，CC 6.1；basic 档实测仅占 **≈784 MiB（单卡）**，GPU1 闲置——backend.md"6–8 GB/算力 ≥7.0"经验值作废 |
| C4 | docker run 完整参数 | ✅ **核实** | `docker inspect`：镜像 **`mineru:pascal`**、容器 `mineru-api`、`--gpus all`、`-p 8000:8000`、**零挂载**（模型烘焙在镜像内）、`restart unless-stopped`、CMD=`mineru-kit api-server --host 0.0.0.0 --port 8000 --tier basic --disable-image-analysis` |
| C5 | wrapper 实现与版本端点 | ✅ **核实** | 非自研：**MinerU 官方 `mineru-kit api-server`**（FastAPI，19 端点，版本在 `/v1/health`）；进程 = 1 主 + 3 multiprocessing worker |
| C6 | 模型实际存放路径 | ✅ **核实 2026-10-26** | 容器内 **`/root/.mineru/models/MinerU-4_models_torch/{Layout,MFR,OCR,Table}/`**（`MINERU_MODEL_SOURCE=local` 默认根 `~/.mineru/models`，**非** `~/.cache/modelscope`）；烘焙在镜像层，宿主不可见，只能 `docker exec` 访问 |

**回填结果**：手册升 **v1.3**（§1.2 GPU 定版、§2.4 镜像 tag 更正、§3.2 sha256 全量、§3.3 校验命令落地路径、§3.4 零挂载+落地路径+宿主/容器辨析、§4.1 实测启动参数、§4.2 LD_LIBRARY_PATH 出入与 CUDA 版本关系、§6 引言、§7.1 四行销账、§8 全销、附录 A 坑 4 更正）+ backend.md §3（GPU/部署形态/模型路径三行）。

## D. 阶段 C 联调（**用户裁定：实测全部完成后才做**）

| # | 事项 | 状态 |
|---|---|---|
| D1 | WorkBuddy 技能壳端到端联调（对话指令 → 技能壳 → tbp → 产物回显） | ✅ **2026-10-26 完成** |
| D2 | 全链路验收收尾、销账，视情况打 v0.2.0 | ✅ **2026-10-27 完成** |

**D2 销项记录（2026-10-27）**：
1. ✅ 全量回归：`run_tests.sh` 67 例 + 5 套对账全绿（exit=0，render 对账 827s，KaTeX 0 错误）。
2. ✅ 五步交付复验（tbp-ws-c，各步 stdout JSON 信封 + 退出码见 AGENT.md 欠账表 D2 行）：
   precheck 0（探活 200 version=4.0.12）→ verify_delivery 0（gaps=[]，C=2）→
   adjudicate_sheet 0（2 items）→ overlay_scaffold 骨架在案（不重复追加）→
   convert（D1 已逐字节验证，不重跑）。
3. ✅ 打版：`v0.2.0`（tag e5833ef），CHANGELOG / README / AGENT.md 状态同步，
   pyproject 版本号补齐（v0.1.0 时漏改 0.0.1）。
4. ✅ 本台账 D2 划勾；A/B/C/D 全部销清，**仅剩 E 人工复核队列**。
5. ✅ 低优先两项顺手完成（commit bf91526）：指纹实测填充 `/v1/health`→4.0.12
   （未配置/探活失败仍 None）；`baseline.blocks:"all"` 按块自动覆盖替代手填 pages
   （4 块覆盖结果与手填逐一相同）；化学书基线已按新口径重建。

**D1 联调结论（全新工作区 `tbp-ws-c`，化学书整册；该工作区已于 2026-10-27 归档删除，见 F 节）**：
1. `tbp convert --subject chemistry --pdf …` 抽取 4 块（368 图）→ `tbp run` 七门全 PASS；
   产物与此前 `tbp-ws-chem`（onboard+run 路径）**逐字节相同**（markdown / 阅读版 / 知识库版
   三件 cmp 全等，images 均 315）→ convert ≡ onboard+run，链路确定性成立。
2. 技能壳脚本实测暴露并修复 **4 处断点**（均为壳侧，未改转换语义）：
   ① `precheck --check-endpoint` 调 `resolve_api(os.getcwd())` 而核心包是无参 `resolve_api()`
   → 端点恒判"未配置"；② 探活用 `/version`，官方 mineru-kit 只有 `/v1/health`（404）→
   改为 health 优先、`/version` 回退，detail 带 `version=4.0.12`；③ `verify_delivery` 只找
   `ws/html/` 与 `out/<book>/<book>.html`，而 run 实际落在 `out/<book>/html|kb_html/`
   → 完整交付被误判 2 处缺口（EXIT 10）；④ `adjudicate_sheet` 的 C 档数据源是 issues.json，
   而 issues 只有探测器计数、无定位信息、且不含 S16 降级项 → 复核表恒为空表。
3. 引擎侧配套（C 档闭环打通）：`detectors.run` 增返 `details`（命中串含行号）；
   `_issues.collect` 据此填 items 的 line/excerpt，并读 `broken_formulas.tsv` 生成 C 档
   items（跨行原串按「行首 序号+tab」切分，摘录折叠单行）。化学书实测 `counts C=2`，
   复核表两条可裁定行，`overlay_scaffold` 成功登记 `overlays/<book>/overlay.jsonl`。
4. 环境侧记录：`extract` 收尾清空重建 `extract/<book>/images`（368 文件）触发宿主批量删除
   保护闸，进程在合并前退出；处置已写入 `skill-textbook-pipe/references/troubleshoot.md`
   （改名 images → 重跑 extract，blocks 命中缓存不重新请求网关）。
5. 交付实测：`tbp report` 重生 TOC/质检报告正常；verify_delivery 0 缺口、双版 HTML
   selfcontain 外部引用 0；C 档 2 条为 S16 降级公式（须按 PDF 补录）。

## E. 长期人工复核队列（QA 报告遗留，故意不自动改写，非关口项）

- 顶点 bar 误识、花括号错位、overrightarrow→widehat 等已知模式频次统计 —— 留人工定位，避免自动改写误伤。

## F. 工作区归档（2026-10-27，用户裁定"仅保留第四类"）

**已删除（不可恢复）**：`tbp-ws` / `tbp-ws-c` / `tbp-ws-chem` 三个工作区 ——
含化学书唯一成品（161 MB：双版 HTML + 315 图 + TOC）、v0.2.0 实测基线（7.8 MB）、
网关切块缓存与抽取中间件（124 MB）、运行日志、staging 残件、旧版备份（37 MB），
以及 `/tmp` 下 154 个测试临时目录。工作区 807 MB → **532 MB**。

**保留**：`gzsx-md/`（526 MB，只读原件 + final 对账裁判）、
`textbook-pipe/`（源码 + .git + v0.1.0/v0.2.0 两个 tag；三份文档与网关部署资产
已于同日归档入库为 `docs/design.md`、`docs/mineru-selfhost.md`、`docs/qa-ledger.md`
与 `deploy/mineru-gateway/`，工作区根只剩 `gzsx-md/` 与 `textbook-pipe/` 两项）、
`.workbuddy/` 记忆。

**复现成本（若日后重启本项目）**：化学书需网关重抽约 7 分钟 + run 约 20 分钟；
数学五册对账可直接用 `gzsx-md/final/` 作 `TBP_PARITY_SOURCE` 跑 `run_tests.sh`。
本台账 B4/D1 记录的产品规格是历史结论，非现存文件。

---

*建台账：2026-10-25。2026-10-27 全部销项（A/B/C/D）并归档（F）；仅 E 人工复核队列
挂账。提醒义务口径见 [AGENT.md](../AGENT.md)：内容保真靠人工抽检，E 队列未清零前
产物不得定稿发布。*
