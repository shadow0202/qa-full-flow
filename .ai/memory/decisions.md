# 架构决策记录

## 2026-04-14 选择 SQLite 作为会话持久化方案
**场景**: SessionManager 需要从内存存储改为持久化
**备选方案**: 
- SQLite（轻量、零依赖、支持并发 WAL 模式）
- Redis（需外部依赖、适合分布式场景）
- PostgreSQL（重量级、过度设计）

**决策**: 选择 SQLite
**原因**: 
- 项目当前为单实例部署，无需分布式会话
- SQLite 零配置，无需额外服务
- WAL 模式支持多进程并发读写
- 可通过配置切换回内存模式（`SESSION_BACKEND=memory`）

**约束**: 如果未来需要水平扩展，可平滑迁移到 Redis

---

## 2026-04-14 BM25 索引使用 JSON 格式而非 Pickle
**场景**: BM25 索引需要持久化到文件
**备选方案**:
- Pickle（直接序列化 BM25Okapi 对象）
- JSON（保存重建所需数据，加载时重构）

**决策**: 选择 JSON 格式
**原因**:
- Pickle 存在安全风险（可执行任意代码）
- JSON 跨语言、可读性强、便于调试
- BM25Okapi 重建成本低（分词+构建索引约几秒）

**约束**: 默认禁用 Pickle 加载（`ALLOW_PICKLE_LOADING=false`）

---

## 2026-04-14 检索器使用依赖注入而非全局变量
**场景**: API 层需要共享 Embedder/ChromaStore/Retriever 实例
**备选方案**:
- 全局变量（简单但难以测试）
- 依赖注入 + lru_cache（实例缓存、便于单元测试）

**决策**: 选择依赖注入 + lru_cache
**原因**:
- FastAPI 原生支持 `Depends()` 模式
- lru_cache 实现实例缓存，避免重复加载模型
- 测试时可轻松 Mock 依赖

**约束**: 后台任务（SyncScheduler）也必须复用依赖注入实例

---

## 2026-04-14 Phase2 Prompt 使用 V3 防幻觉版本
**场景**: 测试用例生成需要控制 LLM 幻觉
**备选方案**:
- V1: 投喂完整 PRD 文档（token 消耗大，易幻觉）
- V2: 投喂多文档（PRD+技术+补充）（信息过载）
- V3: 只投喂 Phase1 提取的结构化功能点（精准控制）

**决策**: 选择 V3 版本
**原因**:
- 避免将原文全文投喂给 Phase2，减少 token 消耗
- 结构化功能点已包含所有必要信息
- 明确约束"禁止编造功能点中未提及的内容"

**约束**: V1/V2 代码保留但不使用，可在未来清理

---

## 2026-04-14 Loader 签名统一使用 **kwargs
**场景**: 各 Loader 有不同参数（resource_type/issue_type/space_key 等）
**备选方案**:
- 各自定义签名（灵活但破坏 LSP）
- 统一使用 **kwargs（类型安全弱但接口一致）
- 使用 dataclass 配置对象（类型安全但复杂）

**决策**: 选择 **kwargs 模式
**原因**:
- 保持基类与子类签名一致（符合 LSP）
- 调用方通过 `**loader_kwargs` 传递参数，模式统一
- 各 Loader 在 docstring 明确 kwargs 用途

**约束**: 未来可考虑引入 dataclass 配置对象以增强类型安全
