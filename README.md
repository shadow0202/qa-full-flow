# QA-Full-Flow: AI测试用例与知识库系统

> 基于向量知识库的智能测试用例生成与检索系统，面向测试开发工程师的工程化解决方案

## 🎯 项目简介

QA-Full-Flow 是一个**生产级** AI 测试知识库与用例生成系统，提供：

- 📚 **统一知识管理** - 对接 JIRA/Confluence/本地文件，构建向量知识库
- 🔍 **智能语义检索** - 三路召回（向量+BM25+元数据）+ RRF 融合 + Cross-Encoder 重排序
- 🤖 **AI 用例生成** - 四阶段工作流（需求分析→用例设计→自审→交付），防幻觉机制保障
- 🔌 **工程化架构** - 模块化设计、依赖注入、Prompt 可配置化、完整类型注解
- 🚀 **生产就绪** - Docker 部署、健康检查、日志轮转、热重载

---

## 🏗️ 系统架构

### 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         客户端层                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Web UI     │  │   API Client │  │  CLI Tools   │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
└─────────┼─────────────────┼─────────────────┼──────────────────┘
          │                 │                 │
          ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API 层 (FastAPI)                            │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────┐  │
│  │  Health    │  │ Knowledge  │  │ TestCases  │  │ Prompts  │  │
│  │  Router    │  │  Router    │  │  Router    │  │ Manager  │  │
│  └────────────┘  └────────────┘  └────────────┘  └──────────┘  │
│                         依赖注入层                                │
└────────────────────────────┬────────────────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   Agent 层       │ │  Retrieval 层   │ │ Data Pipeline   │
│                 │ │                 │ │                 │
│ • Phase1 分析   │ │ • 向量检索      │ │ • 数据加载器    │
│ • Phase2 生成   │ │ • BM25 检索     │ │ • 文档切分      │
│ • Phase3 自审   │ │ • 混合检索      │ │ • 向量化        │
│ • Phase4 交付   │ │ • Reranker      │ │ • 增量更新      │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      基础设施层                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Embedding   │  │ Vector Store │  │  LLM Service │          │
│  │  (BGE-M3)    │  │  (ChromaDB)  │  │  (OpenAI)    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### 核心设计原则

1. **分层架构** - API → Agent/Retrieval/Pipeline → Infrastructure，职责清晰
2. **依赖注入** - 服务实例按需创建，无全局变量，便于测试
3. **Prompt 可配置化** - YAML 模板管理，在线调整无需重启
4. **防幻觉机制** - 结构化提取、Token 预算、可追溯验证
5. **类型安全** - Pydantic Settings + 完整类型注解

---

## 📁 项目结构

```
qa-full-flow/
├── src/qa_full_flow/           # 主源码包
│   ├── agent/                  # AI Agent 层
│   │   ├── prompts/            # Prompt 模板
│   │   │   └── templates/      # YAML 可配置模板
│   │   ├── llm_service.py      # LLM 服务（重试+JSON mode）
│   │   ├── json_parser.py      # JSON 容错解析器
│   │   ├── prompt_manager.py   # Prompt 管理器（热重载）
│   │   ├── document_structurer.py  # 文档结构化+Token预算
│   │   ├── semantic_matcher.py     # 语义匹配（覆盖率分析）
│   │   ├── traceability_verifier.py # 可追溯性验证
│   │   ├── test_phase1_analyzer.py  # 阶段1：需求分析
│   │   ├── test_phase2_generator.py # 阶段2：用例生成
│   │   ├── test_phase3_reviewer.py  # 阶段3：自审
│   │   └── test_session.py     # 会话管理器（状态机）
│   │
│   ├── api/                    # FastAPI 应用层
│   │   ├── routes/             # 路由模块
│   │   │   ├── health.py       # 健康检查
│   │   │   ├── knowledge.py    # 知识库管理
│   │   │   ├── testcases.py    # 测试用例
│   │   │   └── prompt_management.py  # Prompt 管理
│   │   ├── middleware/         # 中间件
│   │   ├── dependencies.py     # 依赖注入
│   │   ├── schemas.py          # Pydantic 数据模型
│   │   └── app.py              # 应用工厂
│   │
│   ├── core/                   # 核心模块
│   │   ├── config.py           # 配置管理（pydantic-settings）
│   │   ├── logging.py          # 日志系统（轮转+JSON）
│   │   └── exceptions.py       # 异常定义
│   │
│   ├── data_pipeline/          # 数据处理层
│   │   ├── loaders/            # 数据加载器
│   │   │   ├── jira_loader.py
│   │   │   ├── confluence_loader.py
│   │   │   └── jsonl_loader.py
│   │   ├── chunker.py          # 文档切分器
│   │   └── pipeline.py         # 数据管道
│   │
│   ├── retrieval/              # 检索层
│   │   ├── retriever.py        # 统一检索入口
│   │   ├── hybrid.py           # 混合检索（三路召回）
│   │   ├── bm25.py             # BM25 关键词检索
│   │   └── reranker.py         # Cross-Encoder 重排序
│   │
│   ├── embedding/              # 向量嵌入层
│   │   └── embedder.py         # SentenceTransformer
│   │
│   └── vector_store/           # 向量存储层
│       └── chroma_store.py     # ChromaDB 封装
│
├── configs/                    # 配置文件
├── data/                       # 数据目录（运行时生成）
│   ├── vector_db/              # 向量数据库
│   └── logs/                   # 日志文件
│
├── tests/                      # 测试代码
├── docs/                       # 文档
│   └── prompt_management.md    # Prompt 管理使用指南
│
├── Dockerfile                  # Docker 镜像
├── docker-compose.yml          # Docker Compose
├── pyproject.toml              # 项目配置（uv）
├── .env.example                # 环境变量模板
└── .gitignore                  # Git 忽略规则
```

---

## 🚀 快速开始

### 前置要求

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

## 📡 API 文档

服务启动后访问：
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 核心接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/v1/knowledge/search` | 知识库检索 |
| POST | `/api/v1/knowledge/ingest` | 数据入库 |
| POST | `/api/v1/knowledge/sync` | 知识库同步 |
| POST | `/api/v1/testcase/generate` | AI 生成用例（旧版） |
| POST | `/api/v1/testcase/session/create` | 创建用例会话 |
| POST | `/api/v1/testcase/session/{id}/phase1` | 阶段1：需求分析 |
| POST | `/api/v1/testcase/session/{id}/phase2` | 阶段2：用例设计 |
| POST | `/api/v1/testcase/session/{id}/phase3` | 阶段3：自审 |
| POST | `/api/v1/testcase/session/{id}/phase4` | 阶段4：交付 |
| GET | `/api/v1/prompts/list` | 列出 Prompt 模板 |
| POST | `/api/v1/prompts/reload` | 重载 Prompt 模板 |

---

## ⚙️ 配置说明

### 环境变量

所有配置通过 `.env` 文件管理，参考 `.env.example`：

```env
# LLM 配置
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-3.5-turbo

# 向量数据库
EMBEDDING_MODEL=BAAI/bge-m3
CHROMA_PATH=./data/vector_db/chroma_kb

# Confluence（可选）
CONFLUENCE_URL=https://your-company.atlassian.net/wiki
CONFLUENCE_EMAIL=your-email@company.com
CONFLUENCE_API_TOKEN=your-token

# JIRA（可选）
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=your-email@company.com
JIRA_API_TOKEN=your-token
```

### Prompt 模板

Prompt 模板位于 `src/qa_full_flow/agent/prompts/templates/`，支持：
- YAML/JSON 格式
- 版本管理（多版本共存）
- 热重载（修改后自动生效）
- 通过 API 在线查询

详见 [Prompt 管理文档](docs/prompt_management.md)。

---

## 🔧 开发指南

### 代码规范

项目使用以下工具保证代码质量：

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

1. **新增 API 端点** - 在 `src/qa_full_flow/api/routes/` 创建路由文件，注册到 `app.py`
2. **新增数据源** - 继承 `BaseLoader`，实现 `load()` 方法
3. **自定义 Prompt** - 在 `templates/` 目录添加 YAML 文件
4. **扩展 Agent** - 实现新的 Phase 或修改现有 Prompt

---

## 🏛️ 核心特性详解

### 1. 三路召回检索系统

```
用户查询
   ↓
┌─────────────────────────────────┐
│        混合检索 (Hybrid)         │
├─────────┬──────────┬────────────┤
│ 向量路  │ BM25 路  │ 元数据路   │
│ 语义匹配│ 关键词    │ 精确匹配   │
└─────────┴──────────┴────────────┘
           ↓
    RRF 融合 (k=60)
           ↓
   Cross-Encoder 重排序
           ↓
       Top-N 结果
```

### 2. 四阶段用例生成

```
Phase1: 需求分析 ──→ Phase2: 用例设计 ──→ Phase3: 自审 ──→ Phase4: 交付
   ↓                   ↓                   ↓                  ↓
• 结构化提取        • 基于功能点          • 语义覆盖率        • Markdown 报告
• Token 预算        • 防跨模块            • 可追溯验证        • JSON 用例
• 显式约束          • JSON mode           • 质量检查          • 交付清单
```

### 3. 防幻觉机制

| 层级 | 机制 | 说明 |
|------|------|------|
| **输入层** | Token 预算控制 | 防止上下文溢出，每类文档有限额 |
| **处理层** | 结构化提取 | 只传 Phase1 提取的功能点，不传原文 |
| **生成层** | JSON mode + 显式约束 | 强制输出 JSON，标注未提及内容 |
| **验证层** | 可追溯性验证 | 逐字段验证是否能在原文找到依据 |

### 4. Prompt 可配置化

```yaml
# src/qa_full_flow/agent/prompts/templates/phase2_design.yaml
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

修改 YAML 文件后，调用 `POST /api/v1/prompts/reload` 即可生效，**无需重启服务**。

---

## 📊 技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| **Web 框架** | FastAPI + Uvicorn | ≥0.115 |
| **向量数据库** | ChromaDB | ≥1.5.5 |
| **Embedding** | SentenceTransformer (BGE-M3) | ≥5.3.0 |
| **分词** | jieba | ≥0.42.1 |
| **BM25** | rank-bm25 | ≥0.2.2 |
| **重排序** | Cross-Encoder (BGE-Reranker) | - |
| **LLM** | OpenAI 兼容 API | ≥1.50.0 |
| **配置** | pydantic-settings | ≥2.6.0 |
| **包管理** | uv | - |
| **代码质量** | ruff + mypy + pre-commit | - |
| **测试** | pytest + httpx | ≥7.0 |
| **部署** | Docker + docker-compose | - |

---

## 🐛 故障排查

### 常见问题

**Q: LLM 服务不可用？**
```bash
# 检查配置
grep LLM .env

# 验证连接
curl -H "Authorization: Bearer $LLM_API_KEY" $LLM_BASE_URL/models
```

**Q: 向量库初始化失败？**
```bash
# 检查目录权限
ls -la data/vector_db/

# 删除重建
rm -rf data/vector_db/chroma_kb
```

**Q: Prompt 模板未生效？**
```bash
# 手动重载
curl -X POST http://localhost:8000/api/v1/prompts/reload

# 检查 YAML 格式
python -c "import yaml; yaml.safe_load(open('path/to/template.yaml'))"
```

---

## 🤝 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'feat: add amazing feature'`)
4. 推送到远程 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

---

## 📄 License

[MIT License](LICENSE)

---

## 👥 作者

**QA Team** - [shadow0202](https://github.com/shadow0202)

---

## ⭐ Star History

如果这个项目对你有帮助，请给个 Star！
