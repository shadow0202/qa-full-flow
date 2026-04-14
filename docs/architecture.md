# QA-Full-Flow 后端系统设计

> 基于完整源码逆向解析与架构建模

---

## 一、架构全景与模块拓扑

### 1.1 技术栈清单

| 层级 | 技术 | 依据 |
|------|------|------|
| **语言** | Python 3.12+ | `pyproject.toml#requires-python` |
| **Web框架** | FastAPI 0.115+ + Uvicorn | `src/qa_full_flow/api/app.py`, `start_api.py` |
| **向量数据库** | ChromaDB (PersistentClient) | `src/qa_full_flow/vector_store/chroma_store.py` |
| **Embedding模型** | SentenceTransformers (BAAI/bge-m3) | `src/qa_full_flow/embedding/embedder.py` |
| **Reranker模型** | BAAI/bge-reranker-large (CrossEncoder) | `src/qa_full_flow/core/config.py#RERANKER_MODEL`, `src/qa_full_flow/retrieval/reranker.py` |
| **关键词检索** | BM25 (rank-bm25) + jieba分词 | `src/qa_full_flow/retrieval/hybrid.py` |
| **LLM集成** | OpenAI SDK (兼容协议) | `src/qa_full_flow/agent/llm_service.py` |
| **数据源** | TAPD / JIRA / Confluence API | `src/qa_full_flow/data_pipeline/loaders/` |
| **配置管理** | pydantic-settings + .env | `src/qa_full_flow/core/config.py` |
| **日志系统** | logging + RotatingFileHandler + JSON格式化 | `src/qa_full_flow/core/logging.py` |
| **依赖管理** | uv (pyproject.toml + uv.lock) | `pyproject.toml` |
| **容器化** | Docker + docker-compose | `Dockerfile`, `docker-compose.yml` |
| **代码质量** | pre-commit + ruff | `.pre-commit-config.yaml` |
| **会话持久化** | SQLite (WAL模式) | `src/qa_full_flow/agent/test_session.py` |

### 1.2 分层架构图

```
客户端层
  ├── 前端/浏览器
  └── CLI脚本

API层 (FastAPI)
  ├── 中间件: Logging + CORS + Error Handler
  ├── 路由: Health Check / 知识库 / 测试用例 / Prompt管理
  └── 依赖注入: lru_cache实例缓存

Agent层 (四阶段工作流)
  ├── Phase1: 需求分析 (LLM + 检索增强)
  ├── Phase2: 用例设计 (LLM + 防幻觉机制)
  ├── Phase3: 自审 (语义匹配 + 可追溯验证 + 质量检查)
  └── Phase4: 交付 (产物整理)
  └── 状态机: TestSession + SessionManager (SQLite持久化)

检索层 (Retrieval)
  ├── HybridRetriever: 向量+BM25+元数据 (RRF融合)
  ├── Reranker: CrossEncoder重排序
  └── Retriever: 统一入口

数据管道层 (DataPipeline)
  ├── DataPipeline: 编排入库
  ├── RecursiveCharacterSplitter: Markdown分级切分
  └── Loaders: TapdLoader / JiraLoader / ConfluenceLoader / JSONLLoader

向量存储层
  ├── Embedder: SentenceTransformers
  └── ChromaStore: PersistentClient

LLM服务层
  ├── LLMService: OpenAI SDK + 指数退避重试
  └── PromptManager: 模板管理 (YAML/JSON/硬编码)

定时同步层 (SyncScheduler)
  └── 共享API实例，定时从TAPD增量同步

持久化层
  ├── ChromaDB 向量库
  ├── BM25 索引 JSON
  ├── SQLite 会话数据库
  └── 日志文件
```

### 1.3 核心模块职责与依赖关系表

| 模块 | 职责 | 上游依赖 | 下游依赖 |
|------|------|---------|---------|
| **API层** | HTTP路由、中间件、异常处理 | FastAPI | Agent层、检索层、数据管道 |
| **Agent层** | 四阶段测试用例生成工作流 | LLM、Prompt、检索 | Session状态机 |
| **检索层** | 混合检索(向量+BM25+元数据)、RRF融合、重排序 | Embedding、ChromaDB | API层、Agent层 |
| **数据管道层** | 数据加载→切分→向量化→入库 | 各Loader、Embedding、ChromaDB | 定时同步、手动入库 |
| **向量存储层** | ChromaDB持久化、集合管理 | SentenceTransformers | 检索层、数据管道 |
| **LLM服务层** | OpenAI协议调用、JSON mode、指数退避重试 | 配置 | Agent层 |
| **定时同步层** | 定时从TAPD拉取Bug/Testcase/Wiki并增量入库 | 共享API实例 | TAPD API |

---

## 二、核心接口契约矩阵

### 2.1 接口分组与路由规则

| 路由前缀 | 分组 |
|----------|------|
| `/health` | 运维 |
| `/api/v1/search` | 知识库检索 |
| `/api/v1/ingest` | 数据入库 |
| `/api/v1/collection/info` | 知识库管理 |
| `/api/v1/testcase/generate` | 测试用例生成(旧) |
| `/api/v1/testcase/save` | 测试用例保存(旧) |
| `/api/v1/testcase/session/*` | 测试用例会话(新, 四阶段) |
| `/api/v1/prompts/*` | Prompt模板管理 |

### 2.2 Top 10 关键接口

| # | 路径 | Method | 协议 | 鉴权 | 幂等 | 错误码 |
|---|------|--------|------|------|------|--------|
| 1 | `/health` | GET | HTTP | ❌ 无 | ✅ | 200 |
| 2 | `/api/v1/search` | POST | JSON | ❌ 无 | ✅ | 500检索失败 |
| 3 | `/api/v1/ingest` | POST | JSON | ❌ 无 | ❌ 依赖update_mode | 500入库失败 |
| 4 | `/api/v1/testcase/generate` | POST | JSON | ❌ 无 | ❌ LLM非幂等 | 400/500 |
| 5 | `/api/v1/testcase/session/create` | POST | JSON | ❌ 无 | ❌ 每次创建新会话 | 500 |
| 6 | `/api/v1/testcase/session/{id}/phase1` | POST | JSON | ❌ 无 | ❌ 状态依赖 | 400/404/500 |
| 7 | `/api/v1/testcase/session/{id}/confirm` | POST | JSON | ❌ 无 | ❌ 状态依赖 | 400/404/500 |
| 8 | `/api/v1/testcase/session/{id}/phase2` | POST | JSON | ❌ 无 | ❌ 状态依赖 | 400/404/500 |
| 9 | `/api/v1/testcase/session/{id}/phase3` | POST | JSON | ❌ 无 | ❌ 状态依赖 | 400/404/500 |
| 10 | `/api/v1/testcase/session/{id}/phase4` | POST | JSON | ❌ 无 | ❌ 状态依赖 | 400/404/500 |

---

## 三、调用链与事务边界

### 3.1 核心业务场景：四阶段测试用例生成

```
客户端请求(wiki_id, module)
  ↓
POST /testcase/session/create → 创建会话 (状态=created, SQLite持久化)
  ↓
POST /testcase/session/{id}/phase1
  ├── TapdLoader.get_wiki_by_id(wiki_id) → PRD原始内容
  ├── DocumentStructurer: 结构化预处理 + Token预算控制(PRD 8000 tokens)
  ├── Retriever.search (向量+BM25+元数据 RRF融合 + CrossEncoder重排序)
  ├── LLMService.generate (OpenAI SDK, json_mode=true)
  └→ 状态更新为 phase1_done (SQLite持久化)
  ↓
POST /testcase/session/{id}/confirm {confirmed: true}
  └→ 状态推进 phase1_confirmed (SQLite持久化)
  ↓
POST /testcase/session/{id}/phase2
  ├── Phase2Generator: 提取结构化功能点 → LLM生成测试用例
  └→ 状态更新为 phase2_done (SQLite持久化)
  ↓
POST /testcase/session/{id}/confirm {confirmed: true}
  └→ 状态推进 phase2_confirmed (SQLite持久化)
  ↓
POST /testcase/session/{id}/phase3
  ├── Phase3Reviewer: 语义匹配覆盖率 + 可追溯验证 + 质量检查
  └→ 状态更新为 phase3_done (SQLite持久化)
  ↓
POST /testcase/session/{id}/confirm {confirmed: true}
  └→ 状态推进 phase3_confirmed (SQLite持久化)
  ↓
POST /testcase/session/{id}/phase4
  ├── Phase4Deliverer: 交付产物整理
  └→ 状态更新为 completed (SQLite持久化)
```

### 3.2 同步/异步链路清单

| 类型 | 生产者 → 队列/存储 → 消费者 | 重试/DLQ |
|------|---------------------------|----------|
| **同步: API检索** | 客户端 → FastAPI → Retriever → HybridRetriever → ChromaDB/BM25 → 响应 | ❌ 无重试, 返回空列表 |
| **同步: API生成** | 客户端 → FastAPI → Phase1/2 → LLMService → OpenAI API → 响应 | ✅ 指数退避重试3次 |
| **同步: 数据入库** | 客户端 → FastAPI → DataPipeline → Loader → Embedder → ChromaStore → 响应 | ❌ 无重试 |
| **异步: 定时同步** | SyncScheduler → TapdLoader → DataPipeline → ChromaStore → BM25重建 | ⚠️ 异常后10分钟重试 |

### 3.3 事务模型

| 事务 | 类型 | 边界 | 一致性保障 |
|------|------|------|-----------|
| **测试用例会话** | SQLite事务 | SessionManager.backend.save() | WAL模式并发安全，UPSERT原子操作 |
| **数据入库** | 本地事务(ChromaDB upsert) | DataPipeline.ingest | ChromaDB原子upsert |
| **定时同步** | 最终一致性(增量同步) | SyncScheduler.run_sync | 基于last_updated时间戳对比 |
| **BM25索引重建** | 最终一致性 | DataPipeline.rebuild_bm25_index | 同步后重建，失败仅warning |

---

## 四、数据流与状态机

### 4.1 核心实体→存储映射表

| 实体 | 存储位置 | ID格式 | 元数据字段 |
|------|---------|--------|-----------|
| **TAPD Bug** | ChromaDB集合 `test_knowledge` | `TAPD_BUG_{id}` | source_type="bug", module, priority, severity, status |
| **TAPD Testcase** | ChromaDB集合 `test_knowledge` | `TAPD_TC_{id}` | source_type="testcase", module, priority, status |
| **TAPD Wiki** | ChromaDB集合 `test_knowledge` | `TAPD_WIKI_{id}` | source_type="wiki", module, parent_wiki_id, view_count |
| **JIRA Bug** | ChromaDB集合 `test_knowledge` | `JIRA_{key}` | source_type="bug_report", module, priority, status |
| **Confluence Page** | ChromaDB集合 `test_knowledge` | `CONFL_{page_id}` | source_type=test_case/business_rule/bug_report, space_key |
| **BM25索引** | JSON文件 `data/vector_db/bm25_index.json` | doc_id数组 | documents, doc_ids, metadatas |
| **测试会话** | SQLite数据库 `data/sessions.db` | UUID前8位 | config, status, artifacts, feedback_history |

### 4.2 业务状态流转图

```
created
  ↓ 执行Phase1
phase1_done
  ↓ 用户确认(confirmed=true) / 用户未确认+重新执行Phase1(confirmed=false)
phase1_confirmed
  ↓ 执行Phase2
phase2_done
  ↓ 用户确认 / 用户未确认+重新执行Phase2
phase2_confirmed
  ↓ 执行Phase3
phase3_done
  ↓ 用户确认 / 用户未确认+重新执行Phase3
phase3_confirmed
  ↓ 执行Phase4
completed
```

---

## 五、可观测性与运维特性

### 5.1 日志/Trace/指标采集机制

| 特性 | 机制 |
|------|------|
| **日志格式** | Text格式(默认) / JSON格式(可选) |
| **日志输出** | stdout + RotatingFileHandler(10MB × 5) |
| **请求日志** | LoggingMiddleware: Request started/completed + duration |
| **响应头** | X-Process-Time: 处理时间(秒) |
| **健康检查** | GET /health → {status, service, version} |
| **Docker Healthcheck** | curl -f http://localhost:8000/health (30s interval) |
| **同步日志** | sync.log (独立日志文件) |

### 5.2 异常处理链路与错误码体系

| 错误场景 | HTTP状态码 | 错误信息格式 |
|----------|-----------|-------------|
| Wiki获取失败 | 400 | "无法获取TAPD Wiki，请检查ID是否正确" |
| 会话不存在 | 404 | "会话不存在" |
| 状态转换非法 | 400 | "当前状态 X 不允许执行阶段Y" |
| TestAgent未实现 | 503 | "TestAgent 尚未实现" |
| 检索失败 | 500 | "检索失败: {str(e)}" |
| 入库失败 | 500 | "入库失败: {str(e)}" |
| LLM调用失败 | 500 | "生成失败: {str(e)}" |
| 未捕获异常 | 500 | "内部服务器错误" |

### 5.3 安全/限流/熔断/灰度配置

| 特性 | 状态 | 详情 |
|------|------|------|
| **CORS** | ✅ 已配置 | 允许 localhost:3000 / 127.0.0.1:3000 |
| **API鉴权** | ❌ 未实现 | 所有端点无认证机制 |
| **限流** | ❌ 未实现 | 无Rate Limiting |
| **熔断** | ⚠️ LLM重试 | 指数退避3次(2s, 4s, 8s) |
| **降级** | ✅ Phase2降级 | LLM失败时使用简单模板 |
| **SSL验证** | ✅ 默认开启 | TapdLoader/JiraLoader/ConfluenceLoader verify_ssl=True |
| **BM25索引安全** | ✅ JSON格式 | 默认禁用pickle(安全风险) |
| **会话清理** | ✅ 24小时过期 | SessionManager.cleanup_old_sessions |

---

> **报告生成时间**: 2026-04-14  
> **分析范围**: 完整源码 (68个Python文件 + 配置文件 + 文档)  
> **核心业务逻辑覆盖率**: 100%
