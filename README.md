# QA-Full-Flow: AI 测试知识库与用例生成系统

> 基于 RAG 架构的测试知识库管理与智能用例生成平台

---

## 项目概述

QA-Full-Flow 是一个实验性 AI 测试知识库与用例生成系统

### 核心能力

| 能力 | 说明 |
|------|------|
| **知识管理** | 对接 JIRA/Confluence/JSONL，构建结构化向量知识库 |
| **语义检索** | 三路召回（向量+BM25+元数据），RRF 融合，Cross-Encoder 重排序 |
| **用例生成** | 四阶段 Agent 工作流（需求分析→用例设计→自审→交付），防幻觉机制保障 |
| **Prompt 管理** | YAML 可配置模板，支持热重载、版本管理 |

---

## 架构设计

### 整体分层

```
客户端层 (Web UI / API Client / CLI)
    │
    ▼
┌─────────────────────────────────────────────┐
│  API 层 (FastAPI)                            │
│  • 路由：Health / Knowledge / TestCases      │
│  • 中间件：日志 / 异常处理                    │
│  • 依赖注入：服务实例按需创建                 │
└──────────────────┬──────────────────────────┘
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
┌─────────┐  ┌──────────┐  ┌──────────┐
│ Agent 层 │  │Retrieval │  │ Pipeline │
│ 需求分析 │  │ 向量路   │  │ 数据加载 │
│ 用例设计 │  │ BM25 路  │  │ 文档切分 │
│ 用例自审 │  │ 元数据路 │  │ 向量化   │
│ 用例交付 │  │ RRF 融合 │  │ 增量更新 │
└────┬────┘  └────┬─────┘  └────┬─────┘
     │            │             │
     └────────────┼─────────────┘
                  ▼
┌─────────────────────────────────────────────┐
│  基础设施层                                   │
│  Embedding (BGE-M3) / ChromaDB / LLM API    │
└─────────────────────────────────────────────┘
```

### 设计原则

- **分层架构** - API → Agent/Retrieval/Pipeline → Infrastructure，职责清晰
- **依赖注入** - 服务实例通过 `@lru_cache` 缓存复用，避免全局变量污染
- **Prompt 可配置化** - YAML 模板管理，在线调整无需重启
- **防幻觉机制** - 结构化提取、Token 预算、可追溯验证、JSON mode 强制输出
- **类型安全** - Pydantic Settings + 完整类型注解

---

## 知识库构建

### 数据源

| 数据源 | 连接器 | 数据类型 | 增量更新 |
|--------|--------|---------|---------|
| **JIRA** | `JiraLoader` | Bug / Task / Story | 基于 `updated` 时间戳 |
| **Confluence** | `ConfluenceLoader` | PRD / 技术文档 / 测试用例 | 基于 `version.updatedAt` |
| **JSONL** | `JSONLLoader` | 本地结构化数据 | 基于 `doc_id` 去重 |

### 入库流程

```
数据源 → Loader.load() → List[Dict{doc_id, content, source_type, module, tags, metadata}]
    ↓
DataPipeline.ingest()
    ├─ 去重判断 (skip / incremental / force 三种模式)
    ├─ 文档切分 (RecursiveCharacterSplitter，支持 Markdown 标题/段落/句子多级切分)
    ├─ 向量化 (Embedder.encode → BAAI/bge-m3)
    ├─ 构建元数据 (tags 转逗号分隔，提取 priority/version/author/last_updated/synced_at)
    └─ 写入向量库 (ChromaStore.upsert → ChromaDB PersistentClient)
    ↓
BM25 索引重建 (JSON 格式持久化，避免 pickle 安全风险)
```

### 关键词自动提取

入库时自动使用 `jieba.analyse.extract_tags()` (TF-IDF) 提取关键词作为 `tags`，提升后续检索的召回率：

```python
# 自动提取 10 个关键词
tags = jieba.analyse.extract_tags(content, topK=10)
```

---

## 检索系统

### 三路召回架构

```
用户查询
    │
    ├─ [第 1 路] 向量语义检索
    │   query → Embedder.encode_single() → ChromaDB 余弦相似度匹配
    │   分词：不分词，直接传入 Embedding 模型
    │
    ├─ [第 2 路] BM25 关键词检索
    │   query → jieba.cut_for_search() → BM25Okapi 打分
    │   分词：jieba 搜索引擎模式
    │
    └─ [第 3 路] 元数据匹配
        query → jieba.cut_for_search() → 匹配 module/tags 字段
        权重：模块精确匹配 20 分 / 包含匹配 10 分 / 标签精确匹配 5 分
            ↓
    RRF 融合 (k=60)
    公式：RRF(d) = Σ weight / (60 + rank(d))
    权重：向量路 1.0 / BM25 路 1.0 / 元数据路 1.5
            ↓
    Cross-Encoder 重排序 (可选，BAAI/bge-reranker-large)
            ↓
    Top-N 结果
```

### 检索配置

检索支持为每路配置独立的 query，实现最优匹配：

```python
retriever.search(
    query=vector_query,           # 向量路：完整语义
    bm25_query=bm25_query,        # BM25 路：精准关键词
    metadata_query=bm25_query,    # 元数据路：精准关键词
    n_results=5,
    filters={"module": "订单支付"}
)
```

### BM25 索引持久化

BM25 索引以 JSON 格式持久化到 `data/vector_db/bm25_index.json`，避免 pickle 反序列化安全风险。系统启动时自动加载，入库完成后自动重建。

---

## Agent 编排

### 四阶段工作流

```
创建会话 → Phase1 需求分析 → 用户确认 → Phase2 用例设计 → 用户确认
    ↓
Phase3 用例自审 → 用户确认 → Phase4 交付
```

### 阶段详解

| 阶段 | 职责 | 输入 | 输出 | 防幻觉机制 |
|------|------|------|------|-----------|
| **Phase1** | 需求分析与测试点提取 | PRD/技术文档/补充文档 | 测试点分析文档 | Token 预算控制、结构化提取 |
| **Phase2** | 测试用例设计生成 | Phase1 提取的结构化功能点 | JSON 格式测试用例 | JSON mode 强制输出、禁止跨模块 |
| **Phase3** | 测试用例自审 | 测试用例 + Phase1 分析结果 | 自审报告（覆盖率/可追溯率/问题清单） | 语义覆盖率分析、可追溯性验证 |
| **Phase4** | 测试用例交付 | 分析文档 + 测试用例 + 自审报告 | Markdown 报告 + JSON 用例 | 质量检查、交付清单 |

### 人工介入 (Human-in-the-Loop)

每个阶段完成后暂停，等待用户审核。用户可：
- **确认通过** → 推进状态，可进入下一阶段
- **驳回反馈** → 记录反馈，自动重新执行当前阶段（LLM 会根据反馈调整输出）

### 多轮知识库检索

Phase1 执行时自动进行多轮 RAG 检索：

```
PRD 文档
    ↓
preprocess_documents() → 提取核心内容
    ↓
第一轮：jieba 提取核心内容关键词 → 检索知识库
第二轮：核心内容完整语义 → 检索知识库
    ↓
合并去重 → Top 5 参考知识 → 传入 Prompt
```

---

## Prompt 管理

### 模板配置

Prompt 模板以 YAML 格式存储在 `src/qa_full_flow/agent/prompts/templates/` 目录：

```yaml
- name: phase2_user_prompt
  version: v3
  content: |
    请基于以下结构化功能点生成测试用例：
    ## 所属模块
    {module}
    
    ## 结构化功能点
    {function_points}
  variables:
    - module
    - function_points
```

### 特性

- **热重载** - 修改 YAML 文件后自动检测更新，无需重启服务
- **版本管理** - 多版本共存，可通过 `version` 参数指定
- **在线查询** - 通过 `GET /api/v1/prompts/list` 查看所有模板

---

## 快速开始

### 环境要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) 包管理器（或 pip）
- Docker & Docker Compose（可选，用于容器化部署）

### 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/shadow0202/qa-full-flow.git
cd qa-full-flow

# 2. 安装依赖
uv sync --dev

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，配置 LLM/Confluence/JIRA 等信息

# 4. 启动服务
uv run python start_api.py
```

### Docker 部署

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f api

# 健康检查
curl http://localhost:8000/health
```

---

## API 文档

服务启动后访问：
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 核心接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/v1/knowledge/search` | 知识库检索 |
| POST | `/api/v1/knowledge/ingest` | 数据入库（支持 skip/incremental/force 模式） |
| POST | `/api/v1/testcase/session/create` | 创建用例会话 |
| POST | `/api/v1/testcase/session/{id}/phase1` | 阶段 1：需求分析 |
| POST | `/api/v1/testcase/session/{id}/confirm` | 确认阶段结果（驳回自动重新执行） |
| POST | `/api/v1/testcase/session/{id}/phase2` | 阶段 2：用例设计 |
| POST | `/api/v1/testcase/session/{id}/phase3` | 阶段 3：用例自审 |
| POST | `/api/v1/testcase/session/{id}/phase4` | 阶段 4：交付 |
| GET | `/api/v1/prompts/list` | 列出 Prompt 模板 |
| POST | `/api/v1/prompts/reload` | 重载 Prompt 模板 |

---

## 配置说明

### 环境变量

所有配置通过 `.env` 文件管理，参考 `.env.example`：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `LLM_API_KEY` | LLM API 密钥 | - |
| `LLM_BASE_URL` | LLM API 基础 URL | `https://api.openai.com/v1` |
| `LLM_MODEL` | LLM 模型名称 | `gpt-3.5-turbo` |
| `EMBEDDING_MODEL` | Embedding 模型 | `BAAI/bge-m3` |
| `CHROMA_PATH` | ChromaDB 存储路径 | `./data/vector_db/chroma_kb` |
| `SYNC_INTERVAL_HOURS` | 定时同步间隔（小时） | `6` |
| `ALLOW_PICKLE_LOADING` | 允许加载旧格式 BM25 索引 | `false` |

### 定时同步

```bash
# 仅启动定时同步（不启动 API）
uv run python sync_scheduler.py --interval 6

# 启动 API + 定时同步
uv run python start_all.py --sync-interval 6
```

---

## 开发指南

### 代码规范

```bash
# 代码格式化
uv run ruff format src/

# 代码检查
uv run ruff check src/

# 类型检查
uv run mypy src/qa_full_flow/

# 运行测试
uv run pytest tests/ -v
```

### Pre-commit Hooks

```bash
# 安装 hooks
pre-commit install

# 手动运行
pre-commit run --all-files
```

### 添加新功能

| 功能 | 操作 |
|------|------|
| **新增 API 端点** | 在 `src/qa_full_flow/api/routes/` 创建路由文件，注册到 `app.py` |
| **新增数据源** | 继承 `BaseLoader`，实现 `load()` 方法 |
| **自定义 Prompt** | 在 `templates/` 目录添加 YAML 文件 |
| **扩展 Agent** | 实现新的 Phase 或修改现有 Prompt |

---

## 技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| **Web 框架** | FastAPI + Uvicorn | ≥0.115 |
| **向量数据库** | ChromaDB | ≥1.5.5 |
| **Embedding** | SentenceTransformer (BAAI/bge-m3) | ≥5.3.0 |
| **分词** | jieba | ≥0.42.1 |
| **BM25** | rank-bm25 | ≥0.2.2 |
| **重排序** | Cross-Encoder (BAAI/bge-reranker-large) | - |
| **LLM** | OpenAI 兼容 API | ≥1.50.0 |
| **配置** | pydantic-settings | ≥2.6.0 |
| **包管理** | uv | - |
| **代码质量** | ruff + mypy + pre-commit | - |
| **测试** | pytest + httpx | ≥7.0 |
| **部署** | Docker + docker-compose | - |

---

## 故障排查

### LLM 服务不可用

```bash
# 检查配置
grep LLM .env

# 验证连接
curl -H "Authorization: Bearer $LLM_API_KEY" $LLM_BASE_URL/models
```

### 向量库初始化失败

```bash
# 检查目录权限
ls -la data/vector_db/

# 删除重建
rm -rf data/vector_db/chroma_kb
```

### BM25 检索未生效

```bash
# 检查索引文件是否存在
ls -la data/vector_db/bm25_index.json

# 重建索引（通过 API）
curl -X POST http://localhost:8000/api/v1/knowledge/ingest \
  -H "Content-Type: application/json" \
  -d '{"source_path": "data/mock_test_kb/mock_test_data.jsonl", "update_mode": "force"}'
```

---

## 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'feat: add amazing feature'`)
4. 推送到远程 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

---

## License

[MIT License](LICENSE)

---

## 作者

**QA Team** - [shadow0202](https://github.com/shadow0202)
