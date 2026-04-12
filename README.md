# QA-Full-Flow: AI 测试知识库与用例生成系统

> 基于 RAG 架构的测试知识库管理与智能用例生成平台

---

## 项目概述

QA-Full-Flow 是一个完整的 AI 测试知识库管理系统，实现了从 **数据获取 → 知识库构建 → 智能检索 → 测试用例生成** 的全链路流程。

### 核心能力

| 能力 | 说明 |
|------|------|
| **知识管理** | 对接 TAPD，自动同步 Bug、Wiki、Testcase 构建向量知识库 |
| **分块存储** | Wiki 长文档智能切分，Bug/Testcase 保持完整，兼顾检索精度与上下文完整性 |
| **三路检索** | 向量语义 + BM25 关键词 + 元数据匹配，RRF 融合，Cross-Encoder 重排序 |
| **分块检索** | PRD 切块后逐块检索全量知识（Wiki/Bug/用例），避免长文档信息稀释 |
| **用例生成** | 四阶段 Agent 工作流（需求分析→用例设计→自审→交付），防幻觉机制保障 |

---

## 核心流程详解

### 一、数据获取与入库

#### 1. 数据源连接

系统通过 `TapdLoader` 从 TAPD 开放平台获取数据，使用 **HTTP Basic Authentication** 认证：

```env
TAPD_WORKSPACE_ID=你的项目ID
TAPD_API_USER=你的API用户名
TAPD_API_PASSWORD=你的API口令
```

#### 2. 数据类型

| 数据类型 | API 路径 | 返回键名 | 内容特点 |
|---------|---------|---------|---------|
| **Bug** | `/bugs` | `"Bug"` | 缺陷描述含 HTML，需清洗 |
| **Wiki** | `/tapd_wikis` | `"Wiki"` | 知识库文档，含 Markdown 内容 |
| **Testcase** | `/tcases` | `"Tcase"` | 测试用例，含步骤和预期结果 |

> **注意**：TAPD 的 Wiki 批量 API 不返回完整内容，系统会自动逐条调用 `get_wiki_by_id` 获取完整 `markdown_description`。

#### 3. 数据清洗

Bug 和 Testcase 的描述字段可能包含 HTML 标签，通过 `_clean_html()` 方法清洗：

```python
@staticmethod
def _clean_html(raw_text: str) -> str:
    # 1. 移除 script/style 标签及其内容
    # 2. 将 <br>, <p> 等换行标签转为 \n
    # 3. 移除剩余 HTML 标签
    # 4. 处理 HTML 实体（如 &gt; → >）
    # 5. 将 &nbsp; 转为普通空格
    # 6. 压缩多余空行（3个以上换行 → 2个）
```

**Wiki 文档不经过 HTML 清洗**，保留完整的 Markdown 格式（含 `#`, `##` 标题），用于后续按标题切分。

#### 4. 智能分块策略

系统使用 `RecursiveCharacterSplitter` 进行**差异化分块**：

```python
# 切分规则
if source_type == "wiki" and content_len > chunk_size (800字符):
    # Wiki 长文档 → 按 Markdown 标题层级切分
    # 优先级：# → ## → ### → 段落 → 句子
    # 重叠：100 字符（防止关键信息被切断）
else:
    # Bug / Testcase / 短 Wiki → 保持完整，不切分
```

#### 5. 向量化与入库

```
TapdLoader.load()
    ↓ (返回 List[Dict])
    • doc_id: "TAPD_WIKI_123" / "TAPD_BUG_456" / "TAPD_TC_789"
    • content: 清洗后的文本
    • source_type: "wiki" / "bug" / "testcase"
    • module: "Wiki知识库" / "默认模块" / "测试用例库"
    • tags: ["关键词1", "关键词2"]  # jieba 自动提取
    • metadata: {priority, author, create_date, last_updated, ...}
    ↓
DataPipeline.ingest(update_mode="incremental")
    ↓
┌─ 增量检查（对比 last_updated 时间戳）
├─ 文档切分（仅 Wiki 长文档）
├─ 向量化（BAAI/bge-m3，归一化）
├─ 构建元数据（tags 转逗号分隔字符串）
└─ 写入 ChromaDB (upsert)
    ↓
BM25 索引重建（JSON 格式持久化）
```

#### 6. 定时同步

```bash
# 启动定时同步（默认每 6 小时）
python sync_scheduler.py --interval 6

# 仅执行一次
python sync_scheduler.py --once
```

同步内容：
1. **Bug**：增量同步，基于 `modified` 时间戳
2. **Testcase**：增量同步，基于 `modified` 时间戳
3. **Wiki**：增量同步，逐条获取完整内容

---

### 二、检索流程

#### 1. 分块检索（生成测试用例时）

当用户传入 PRD Wiki ID 生成测试用例时，系统执行**分块全量检索**：

```
用户传入 PRD Wiki ID
    ↓
获取完整 PRD 内容（可能 3000+ 字）
    ↓
RecursiveCharacterSplitter 切分（800字/块，重叠100字）
    → 假设切分为 5 块：[背景与目标, 发品模块, 导购模块, 交易模块, 履约模块]
    ↓
逐块全量检索（每块执行一次）
    ↓
┌─ 关键词提取：jieba.analyse.extract_tags(chunk, topK=10)
│     → 如："购买, Redis, 库存, 预占, 异常"
│
├─ 向量检索路：完整 chunk 文本 → Embedding → 语义匹配
│
├─ BM25 检索路：关键词 → 文本匹配（精准命中功能词）
│
├─ 元数据匹配路：关键词 → 碰撞 module/tags 字段
│     • 模块精确匹配 +20 分
│     • 模块包含匹配 +10 分
│     • 标签精确匹配 +5 分
│
├─ RRF 融合（k=60）
│     向量路权重 1.0 / BM25 路 1.0 / 元数据路 1.5
│
└─ Cross-Encoder 重排序（可选）
    ↓
去重合并（按 doc_id 去重）
    ↓
分类归档
    • wikis: 相关技术文档
    • bugs: 历史缺陷记录
    • testcases: 已有测试用例
    ↓
传入 Agent 生成新用例
```

**分块检索优势**
- 直接用整篇 PRD 检索会导致语义平均化，后半部分功能点被忽略
- 分块后每块聚焦一个功能点，召回更精准
- 全量检索（Wiki+Bug+用例）确保获取全方位上下文

#### 2. 三路召回详解

| 检索路 | 入参 | 匹配原理 | 优势 |
|--------|------|---------|------|
| **向量语义** | 完整 chunk 文本 | 深度学习理解语义 | 不受字面差异影响（如"库存不足"匹配"缺货"） |
| **BM25** | 提取的关键词 | 词频/逆文档频率打分 | 精准匹配专业术语 |
| **元数据** | 提取的关键词 | 模块名/标签精确匹配 | 确保同模块文档优先召回 |

#### 3. BM25 索引管理

- **构建时机**：数据入库后自动重建
- **存储格式**：JSON（避免 pickle 安全风险）
- **加载时机**：系统启动时自动加载
- **一致性保障**：启动时对比向量库文档数，不一致则自动重建

---

### 三、测试用例生成

```
POST /api/v1/testcase/generate
{
  "wiki_id": "123456",           # 必填：PRD Wiki ID
  "additional_wiki_ids": ["789"], # 可选：技术文档 Wiki ID
  "module": "用户管理",
  "n_examples": 5,
  "use_knowledge_base": true
}
    ↓
1. 获取 PRD Wiki 完整内容
2. 分块全量检索（获取相关 Wiki/Bug/用例）
3. 构建 Prompt（PRD + 检索到的全量上下文）
4. 调用 LLM Agent 生成测试用例
5. 返回生成的用例 + 参考来源
```

---

## 架构设计

### 整体分层

```
┌─────────────────────────────────────────────────┐
│  API 层 (FastAPI)                                │
│  • 用例生成 / 知识库检索 / 数据入库              │
│  • 依赖注入：TapdLoader / Retriever / Pipeline   │
└──────────────────┬──────────────────────────────┘
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
┌─────────┐  ┌──────────┐  ┌──────────┐
│ Agent 层 │  │Retrieval │  │ Pipeline │
│ 四阶段   │  │ 三路召回  │  │ 数据加载 │
│ 工作流   │  │ RRF+重排 │  │ 清洗切分 │
└────┬────┘  └────┬─────┘  └────┬─────┘
     │            │             │
     └────────────┼─────────────┘
                  ▼
┌─────────────────────────────────────────────────┐
│  基础设施层                                      │
│  Embedding (BGE-M3) / ChromaDB / LLM API        │
└─────────────────────────────────────────────────┘
```

### 设计原则

- **分层架构** - API → Agent/Retrieval/Pipeline → Infrastructure，职责清晰
- **依赖注入** - 服务实例通过 `@lru_cache` 缓存复用，避免全局变量污染
- **智能分块** - Wiki 长文档切分，Bug/Testcase 保持完整
- **分块检索** - PRD 切块后逐块检索，避免信息稀释
- **防幻觉机制** - 结构化提取、Token 预算、可追溯验证

---

## 快速开始

### 环境要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) 包管理器

### 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/shadow0202/qa-full-flow.git
cd qa-full-flow

# 2. 安装依赖
uv sync --dev

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，配置 TAPD 和 LLM 信息

# 4. 启动服务
uv run python start_api.py
```

### 定时同步

```bash
# 启动定时同步（每 6 小时同步一次 TAPD 数据）
uv run python sync_scheduler.py --interval 6

# 同时启动 API + 定时同步
uv run python start_all.py --sync-interval 6
```

---

## API 文档

服务启动后访问：
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 核心接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/testcase/generate` | 基于 Wiki 文档生成测试用例（分块检索增强） |
| POST | `/api/v1/knowledge/search` | 知识库检索 |
| POST | `/api/v1/knowledge/ingest` | 数据入库 |
| GET | `/health` | 健康检查 |

---

## 配置说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `TAPD_WORKSPACE_ID` | TAPD 项目 ID | - |
| `TAPD_API_USER` | TAPD API 用户名 | - |
| `TAPD_API_PASSWORD` | TAPD API 口令 | - |
| `LLM_API_KEY` | LLM API 密钥 | - |
| `LLM_BASE_URL` | LLM API 基础 URL | `https://api.openai.com/v1` |
| `LLM_MODEL` | LLM 模型名称 | `gpt-3.5-turbo` |
| `EMBEDDING_MODEL` | Embedding 模型 | `BAAI/bge-m3` |
| `CHROMA_PATH` | ChromaDB 存储路径 | `./data/vector_db/chroma_kb` |
| `SYNC_INTERVAL_HOURS` | 定时同步间隔（小时） | `6` |

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

---

## 故障排查

### BM25 检索未生效

```bash
# 检查索引文件是否存在
ls -la data/vector_db/bm25_index.json

# 如不存在，触发一次全量同步重建
uv run python sync_scheduler.py --once
```

### 向量库初始化失败

```bash
# 检查目录权限
ls -la data/vector_db/

# 删除重建
rm -rf data/vector_db/chroma_kb
uv run python sync_scheduler.py --once
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
