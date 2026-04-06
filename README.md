# QA-Full-Flow: AI测试用例与知识库系统

> 基于向量知识库的智能测试用例生成与检索系统

## 🎯 项目简介

面向测试开发工程师的AI知识库与测试用例生成系统：
- 📚 **管理测试知识**：统一存储测试用例、Bug报告、业务规则
- 🔍 **智能语义检索**：基于语义相似度快速定位相关知识
- 🤖 **AI生成测试用例**：分阶段工作流，PRD/技术文档充分理解后生成
- 🔌 **可扩展架构**：支持对接JIRA、Confluence等数据源
- 🏗️ **工程化规范**：模块化设计、pre-commit、Docker支持

---

## 🏗️ 知识库架构详解

### 整体数据流程图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          数据源层（外部系统）                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │   JIRA       │  │  Confluence  │  │  本地JSONL   │                  │
│  │  (Bug/任务)  │  │  (PRD/文档)  │  │  (自定义数据) │                  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                  │
│         │                 │                 │                           │
│         ▼                 ▼                 ▼                           │
├─────────────────────────────────────────────────────────────────────────┤
│                          数据接入层（Loaders）                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │  JiraLoader  │  │ConfluenceLoader│ │ JSONLLoader │                  │
│  │              │  │              │  │              │                  │
│  │ • JQL查询    │  │ • v1/v2 API  │  │ • 本地文件    │                  │
│  │ • 字段提取   │  │ • HTML转文本  │  │ • 格式校验    │                  │
│  │ • 状态映射   │  │ • 页面分类    │  │              │                  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                  │
│         │                 │                 │                           │
│         └─────────────────┼─────────────────┘                           │
│                           ▼                                             │
├─────────────────────────────────────────────────────────────────────────┤
│                          数据处理层（Pipeline）                          │
│                                                                         │
│  1. 加载数据 ──→ 2. 去重/增量检查 ──→ 3. 文档切分 ──→ 4. 向量化         │
│                           │                    │                        │
│                           ▼                    ▼                        │
│                    ┌──────────────┐  ┌──────────────────┐              │
│                    │ 增量更新逻辑  │  │ RecursiveCharacter│              │
│                    │              │  │    Splitter        │              │
│                    │ • doc_id去重 │  │                    │              │
│                    │ • 时间戳对比  │  │ • Markdown标题    │              │
│                    │ • 有则更新    │  │ • 段落/句子/字符  │              │
│                    │ • 无则跳过    │  │ • overlap=50      │              │
│                    └──────────────┘  └──────────────────┘              │
│                           │                                             │
│                           ▼                                             │
├─────────────────────────────────────────────────────────────────────────┤
│                          向量存储层（ChromaDB）                          │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │                    文档 Schema                            │          │
│  │                                                          │          │
│  │  doc_id: "JIRA_PROJ-123"     ← 唯一标识（数据源ID+前缀） │          │
│  │  content: "标题：登录页崩溃..." ← 切分后的文本块          │          │
│  │  embedding: [0.1, 0.2, ...]  ← 向量（BGE-M3, 1024维）   │          │
│  │  metadata: {                  ← 元数据（用于过滤/更新）   │          │
│  │    source_type: "bug_report",                            │          │
│  │    module: "登录",                                       │          │
│  │    last_updated: "2026-04-08T10:00:00Z",  ← 数据源更新时间│          │
│  │    synced_at: "2026-04-08T12:00:00Z",     ← 我们同步时间 │          │
│  │    priority: "P0",                                       │          │
│  │    ...                                                   │          │
│  │  }                                                       │          │
│  └──────────────────────────────────────────────────────────┘          │
│                                                                         │
│  存储方式: PersistentClient（本地持久化，data/vector_db/）              │
└─────────────────────────────────────────────────────────────────────────┘
```

### 统一同步接口

所有知识库更新都通过 **统一 API 接口** 处理：

```
POST /api/v1/knowledge/sync

请求体:
{
    "type": "bug | doc | jsonl",      ← 数据源类型
    "config": { ... },                 ← 不同类型配置不同
    "update_mode": "incremental"       ← 更新模式
}
```

| type | config 关键字段 | 说明 |
|------|----------------|------|
| `bug` | `jira_url`, `jira_email`, `jira_api_token`, `project_key` | 从 JIRA 同步 Bug |
| `doc` | `confluence_url`, `confluence_email`, `confluence_api_token`, `space_key` | 从 Confluence 同步文档 |
| `jsonl` | `file_path`, `chunk_size`, `chunk_overlap` | 上传本地 JSONL 文件 |

### 增量更新机制

**核心问题**：如何避免重复插入？如何检测数据源变更？

**解决方案**：

```
同步流程:
┌─────────────────────────────────────────────────────────────┐
│  1. 从 JIRA/Confluence 拉取数据                               │
│     每条数据带 last_updated 时间戳                             │
│     例: {"doc_id": "JIRA_PROJ-123", "last_updated": "2026-04-08T15:00:00Z"} │
│                              │                                │
│                              ▼                                │
│  2. 查询向量库中是否已存在该 doc_id                             │
│     ├── 不存在 → 新文档，直接插入 ✅                            │
│     └── 存在 → 对比 last_updated                               │
│          ├── 源.last_updated > 库.last_updated                │
│          │      → 数据源有变更，执行 upsert 覆盖 ✅              │
│          └── 源.last_updated <= 库.last_updated               │
│                 → 数据无变更，跳过 ✅                            │
└─────────────────────────────────────────────────────────────┘
```

**定时任务**：只同步 `bug` 和 `doc` 类型，使用 `incremental` 模式，定期自动执行。

---

## 🔍 检索系统详解

### 混合检索架构

```
用户查询: "登录功能测试用例"
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                     多路召回层                                    │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │  向量语义路  │  │ BM25关键词路│  │ 元数据匹配路  │            │
│  │             │  │             │  │             │            │
│  │ • BGE-M3    │  │ • jieba分词 │  │ • 标题匹配   │            │
│  │ • ChromaDB  │  │ • BM25算法  │  │ • 标签匹配   │            │
│  │ • 余弦相似度│  │ • 关键词得分│  │ • 模块匹配   │            │
│  │             │  │             │  │             │            │
│  │ 召回: [A,B,C]│  │ 召回: [A,D,E]│  │ 召回: [A,F] │            │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘            │
│         │                │                │                    │
│         └────────────────┼────────────────┘                    │
│                          ▼                                     │
│              RRF (Reciprocal Rank Fusion) 融合                 │
│              RRF(d) = Σ 1/(k + rank(d))                       │
│              k=60, 平衡各路权重                                 │
│                          │                                     │
│                          ▼                                     │
│              融合结果: [A(最高), B, C, D, E, F]                 │
└──────────────────────────┬─────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     重排序层（Reranker）                          │
│                                                                 │
│  ┌──────────────────────────────────────────────────┐          │
│  │  Cross-Encoder 模型 (BAAI/bge-reranker-large)    │          │
│  │                                                  │          │
│  │  • 输入: (query, document) 对                    │          │
│  │  • 输出: 精确相关性分数                           │          │
│  │  • 相比 Bi-Encoder 的优势:                        │          │
│  │    - 捕捉 query-document 细粒度交互               │          │
│  │    - 比余弦相似度更准确                           │          │
│  └──────────────────────────────────────────────────┘          │
│                          │                                     │
│                          ▼                                     │
│              最终排序: [A, D, B, ...] (按相关性降序)             │
│              返回 Top-N 结果                                    │
└─────────────────────────────────────────────────────────────────┘
```

### 各技术组件效果对比

| 检索路 | 技术 | 优势 | 局限 | 适用场景 |
|--------|------|------|------|---------|
| 向量语义 | BGE-M3 + ChromaDB | 理解语义相似度，不依赖关键词匹配 | 可能遗漏关键词精确匹配的文档 | 语义相近但用词不同的查询 |
| BM25关键词 | jieba + rank-bm25 | 精确关键词匹配，可解释性强 | 无法理解语义，同义词失效 | 包含专有名词/接口名的查询 |
| 元数据匹配 | 标题/标签/模块精确匹配 | 权重高，直接命中 | 依赖元数据质量 | 已知模块/标签的精确查询 |
| RRF 融合 | 倒数排名融合 | 无需调参，鲁棒性强 | 各路质量差异大时效果下降 | 多路结果互补 |
| Cross-Encoder 重排 | bge-reranker-large | 精确相关性打分 | 计算开销大，只重排候选集 | 对准确率要求高的场景 |

---

## 🤖 AI 生成测试用例（防幻觉机制）

### 来源标注 + 置信度评分

```json
{
  "title": "用户输入正确手机号和验证码登录",
  "priority": "P0",
  "steps": ["打开登录页", "输入手机号", "输入验证码", "点击登录"],
  "expected": "登录成功，跳转首页",
  "source": {
    "document_type": "PRD文档",
    "section": "3.2 用户登录功能",
    "quote": "用户输入已注册的手机号和短信验证码，验证通过后跳转至首页"
  },
  "confidence": 0.95
}
```

| 字段 | 说明 | 作用 |
|------|------|------|
| `source.document_type` | 来源文档类型 | 可追溯到 PRD/技术文档/补充文档 |
| `source.section` | 对应章节 | 快速定位原始需求位置 |
| `source.quote` | 原文引用（20-50字） | **防幻觉**：必须引用原文，无法编造 |
| `confidence` | 置信度 0.0-1.0 | 确定性评分，辅助人工审核 |

### 置信度分级

| 分数范围 | 含义 | 前端展示 | 处理建议 |
|---------|------|---------|---------|
| 0.9-1.0 | 文档明确描述，细节完整 | 🟢 绿色 | 可直接通过 |
| 0.7-0.89 | 文档有提及但细节不完整 | 🟡 黄色 | 需要人工确认 |
| 0.5-0.69 | 文档暗示但未明确说明 | 🟡 黄色 | 重点审查 |
| <0.5 | AI 自行补充的通用场景 | 🔴 红色 + ⚠️ | 可能是幻觉，必须审核 |

### 防幻觉 Prompt 约束

在 System Prompt 中明确要求 LLM：
1. **严格基于文档**：禁止编造文档中不存在的需求
2. **可追溯性**：每个用例必须能对应到文档中的具体功能
3. **不确定时保守处理**：标注"待确认"而非自行假设

---

## 🚀 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，配置 Confluence/JIRA/LLM 连接信息
```

### 3. 启动API服务

```bash
python start_api.py
```

访问API文档：http://localhost:8000/docs

### 4. Docker启动（可选）

```bash
docker-compose up -d
```

## 📦 项目结构

```
qa-full-flow/
├── src/
│   ├── agent/                     # AI Agent层
│   │   ├── llm_service.py
│   │   ├── test_agent.py          # 测试用例生成Agent
│   │   ├── test_session.py        # 会话管理（状态机）
│   │   ├── test_phase1_analyzer.py   # 阶段1：需求分析
│   │   ├── test_phase2_generator.py  # 阶段2：用例生成
│   │   ├── test_phase3_reviewer.py   # 阶段3：自审
│   │   ├── test_phase4_deliver.py    # 阶段4：交付
│   │   └── prompts/               # Prompt模板
│   ├── api/                       # API层
│   │   ├── app.py                 # 应用工厂
│   │   ├── schemas.py             # Pydantic模型
│   │   └── routes/                # 模块化路由
│   ├── config/                    # 配置管理
│   │   └── settings.py
│   ├── data_pipeline/             # 数据管道
│   │   ├── pipeline.py            # 数据处理管道（含增量更新）
│   │   ├── chunker.py             # 递归字符切分器
│   │   └── loaders/               # 数据加载器
│   │       ├── base.py
│   │       ├── jira_loader.py
│   │       ├── confluence_loader.py
│   │       └── jsonl_loader.py
│   ├── embedding/                 # 向量嵌入
│   │   └── embedder.py            # BGE-M3 模型封装
│   ├── retrieval/                 # 检索层
│   │   ├── retriever.py           # 统一检索入口
│   │   ├── hybrid.py              # 混合检索（多路召回+RRF）
│   │   ├── bm25.py                # BM25 关键词检索
│   │   └── reranker.py            # Cross-Encoder 重排序
│   └── vector_store/              # 向量存储
│       └── chroma_store.py        # ChromaDB 封装
├── tests/                         # 测试
├── data/                          # 数据目录（gitignore）
│   └── vector_db/                 # 向量库持久化目录
├── .env.example
├── pyproject.toml
├── sync_scheduler.py              # 定时同步任务
└── start_api.py                   # API启动脚本
```

## 🏗️ 架构设计

### 分阶段测试用例生成工作流

采用**状态机模式**和**Human-in-the-loop**机制：

```
创建会话 → 阶段1(需求分析) → 人工确认 →
阶段2(用例设计) → 人工确认 →
阶段3(用例自审) → 人工确认 →
阶段4(交付) → 完成
```

**核心优势**：
- ✅ 每个阶段生成可审查的中间产物
- ✅ 人工确认机制，避免黑盒
- ✅ 状态机控制，防止非法跳转
- ✅ 完整的会话管理和产物保存

## 🔧 开发工具链

### 代码格式化

```bash
ruff format src/
```

### 代码检查

```bash
ruff check src/
```

### 安装pre-commit hooks

```bash
pre-commit install
pre-commit run --all-files
```

### 运行测试

```bash
pytest tests/ -v
```

## 🔌 API使用示例

### 1. 统一知识库同步

#### 同步 JIRA Bug

```bash
curl -X POST http://localhost:8000/api/v1/knowledge/sync \
  -H "Content-Type: application/json" \
  -d '{
    "type": "bug",
    "config": {
      "jira_url": "https://your-company.atlassian.net",
      "jira_email": "user@company.com",
      "jira_api_token": "your-token",
      "project_key": "PROJ",
      "max_results": 100
    },
    "update_mode": "incremental"
  }'
```

#### 同步 Confluence 文档

```bash
curl -X POST http://localhost:8000/api/v1/knowledge/sync \
  -H "Content-Type: application/json" \
  -d '{
    "type": "doc",
    "config": {
      "confluence_url": "https://your-company.atlassian.net/wiki",
      "confluence_email": "user@company.com",
      "confluence_api_token": "your-token",
      "space_key": "TEST",
      "max_results": 50
    },
    "update_mode": "incremental"
  }'
```

#### 上传 JSONL 文件

```bash
curl -X POST http://localhost:8000/api/v1/knowledge/sync \
  -H "Content-Type: application/json" \
  -d '{
    "type": "jsonl",
    "config": {
      "file_path": "data/raw/test_cases.jsonl"
    },
    "update_mode": "incremental"
  }'
```

### 2. 混合检索知识库

```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "登录功能测试",
    "n_results": 5,
    "filters": {"module": "登录", "source_type": "test_case"}
  }'
```

### 3. 创建测试用例会话

```bash
curl -X POST http://localhost:8000/api/v1/testcase/session/create \
  -H "Content-Type: application/json" \
  -d '{
    "prd_url": "https://your-confluence.atlassian.net/wiki/spaces/XXX/pages/123",
    "tech_doc_urls": ["https://your-confluence.atlassian.net/wiki/spaces/DEV/pages/456"],
    "module": "订单支付",
    "n_examples": 5,
    "use_knowledge_base": true
  }'
```

### 4. 执行阶段1：需求分析

```bash
curl -X POST http://localhost:8000/api/v1/testcase/session/{session_id}/phase1
```

返回测试点分析文档，前端展示给用户确认。

### 5. 确认后继续阶段2

```bash
curl -X POST http://localhost:8000/api/v1/testcase/session/{session_id}/confirm \
  -H "Content-Type: application/json" \
  -d '{"confirmed": true}'

curl -X POST http://localhost:8000/api/v1/testcase/session/{session_id}/phase2
```

返回生成的测试用例（含来源标注和置信度）。

完整API文档请参考：http://localhost:8000/docs

## ⚙️ 配置说明

### 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `JIRA_URL` | JIRA服务器地址 | `https://xxx.atlassian.net` |
| `JIRA_EMAIL` | JIRA邮箱 | `user@company.com` |
| `JIRA_API_TOKEN` | JIRA API Token | `ATATT3...` |
| `JIRA_PROJECT_KEY` | JIRA项目Key | `PROJ` |
| `CONFLUENCE_URL` | Confluence服务器地址 | `https://xxx.atlassian.net/wiki` |
| `CONFLUENCE_EMAIL` | Confluence邮箱 | `user@company.com` |
| `CONFLUENCE_API_TOKEN` | Confluence API Token | `ATATT3...` |
| `EMBEDDING_MODEL` | Embedding模型 | `BAAI/bge-m3` |
| `RERANKER_MODEL` | 重排序模型 | `BAAI/bge-reranker-large` |
| `LLM_API_KEY` | LLM API密钥（可选） | `sk-xxx` |
| `LLM_BASE_URL` | LLM API地址 | `https://api.openai.com/v1` |
| `LLM_MODEL` | LLM模型 | `gpt-3.5-turbo` |
| `API_PORT` | API服务端口 | `8000` |

## 🎯 典型使用场景

### 场景1：基于PRD生成测试用例

1. 提供PRD Confluence链接
2. 系统自动获取文档内容
3. 分阶段分析需求、生成用例、自审、交付
4. 每个阶段人工确认，确保质量

### 场景2：混合检索历史知识

```python
# 语义检索（自动混合向量+BM25+元数据）
search("并发导致库存超卖", filters={"source_type": "bug_report"})

# 结果按相关性排序，每个用例带来源标注和置信度
```

### 场景3：定时同步JIRA/Confluence

系统后台定期从数据源拉取增量数据，自动对比时间戳增量入库。

## 📊 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 向量数据库 | ChromaDB | 本地持久化，支持元数据过滤 |
| Embedding | BAAI/bge-m3 | 支持中文，1024维向量 |
| 分词 | jieba | 中文分词，用于BM25 |
| BM25检索 | rank-bm25 | 关键词精确匹配 |
| 重排序 | BAAI/bge-reranker-large | Cross-Encoder，精确相关性打分 |
| 文档切分 | RecursiveCharacterSplitter | 多级切分策略，overlap=50 |
| Web框架 | FastAPI | 异步高性能 |
| LLM | OpenAI兼容接口 | 可对接任意模型 |
| 依赖管理 | uv | 快速可靠 |
| 代码质量 | ruff + pre-commit | 自动化规范 |
| 部署 | Docker | 容器化 |

## 🤝 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 提交 Pull Request

## 📄 License

MIT
