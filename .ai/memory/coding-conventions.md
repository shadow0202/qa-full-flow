# 编码规范

## FastAPI
- 依赖注入使用 `lru_cache` 实例缓存，避免全局变量
- 路由文件按功能拆分（health/knowledge/testcases/prompts）
- 异常处理统一在 `middleware/error_handler.py`
- 响应模型使用 Pydantic BaseModel，字段必须有描述
- CORS 配置允许 `localhost:3000` 和 `127.0.0.1:3000`

## Agent 层
- 四阶段工作流必须保持独立（Phase1/2/3/4）
- Prompt 模板优先使用 `PromptManager.render()` 管理
- LLM 调用必须启用 `json_mode=True`
- 使用 `extract_json_object/array` 容错解析 LLM 输出
- 会话状态变更必须调用 `session_manager.update_session()` 持久化

## 检索层
- 混合检索默认开启（向量+BM25+元数据），RRF 融合常数 `rrf_k=60`
- BM25 索引使用 JSON 格式（禁止 pickle，安全风险）
- CrossEncoder 重排序器加载失败时优雅降级（返回 None）
- 检索失败返回空列表，不抛异常

## 数据管道
- Loader 必须继承 `BaseLoader`，签名统一为 `load(source="", **kwargs)`
- kwargs 用途必须在 docstring 明确列出
- 文档切分使用 `RecursiveCharacterSplitter`（chunk_size=800, overlap=100）
- 向量化使用 `Embedder.encode(normalize=True)`

## 配置管理
- 所有配置使用 pydantic-settings（`Settings` 类）
- 敏感信息放入 `.env`（不在代码中硬编码）
- 配置项必须有验证器（validator）
- 新增配置项必须加到 `.env.example`

## 日志
- 使用 `logging.getLogger(__name__)` 获取 logger
- 禁止使用 `print()` 输出日志
- 敏感信息（API Key/密码）禁止记录到日志
- 请求日志由 `LoggingMiddleware` 自动处理

## 测试
- 测试文件放在 `tests/` 目录
- 使用 pytest fixtures 提供 Mock 对象
- 测试命名格式：`test_功能_场景.py`
