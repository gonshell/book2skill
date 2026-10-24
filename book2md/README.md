# textbook-pipe

教材 PDF → md + 图片 + 公式 → 双版本单体 HTML（阅读版 / 知识库版）的独立转换工具。

源自人教A版高中数学 5 册转换项目（gzsx-md）沉淀的 ~3800 行引擎，产品化重构。
设计文档见工作区 `教材转换工具化方案.md`（本仓库外）。

## 结构（一核一壳）

```
textbook_pipe/           核心包（必选）：引擎 + 配置 + CLI（命令 tbp，别名 tbpipe）
├── engine/              修复/渲染/探测器/质量门流水线（自 gzsx-md 参数化搬迁）
├── extractors/          抽取适配器（RemoteMinerU / LocalMinerU / 未来其他 OCR）
├── configs/             backends 网关契约 + 科目配置
├── packs/               L1 学科规则包（math 已有，chem/physics 预研）
└── assets/katex/        KaTeX 预渲染资产（随包分发）
skill-textbook-pipe/     WorkBuddy 技能壳（可选）：SKILL.md + scripts + references
docs/                    install / onboarding / backend 三手册
baselines/               基准样本初始集 + 基线指标
```

## 纪律

- 行为保持型搬迁：每步以五册字符数逐字节一致为过关线
- 引擎逻辑零平台绑定；技能壳逻辑零嵌入
- 教材 PDF / 整册图片 / 产物永不入库（见 .gitignore）
