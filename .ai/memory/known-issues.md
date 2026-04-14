# 已知问题与历史坑

## 2026-04-14 Reranker 依赖注入缺失
**场景**: `dependencies.py` 中 `get_retriever()` 未传入 Reranker 实例
**问题**: Reranker 永远不会被调用，重排序功能失效
**解决**: 新增 `get_reranker()` 依赖函数，在 `get_retriever()` 中注入
**约束**: 新增依赖时必须同步更新所有引用方，审查调用链确保参数传递

## 2026-04-14 SessionManager 无持久化
**场景**: 会话数据纯内存存储（`Dict[str, TestSession]`）
**问题**: 服务重启后丢失所有会话，无法水平扩展
**解决**: 实现 SQLite 后端持久化，支持 memory/sqlite 双模式
**约束**: 涉及状态管理的组件必须考虑持久化方案

## 2026-04-14 SyncScheduler 重复初始化服务
**场景**: SyncScheduler 独立初始化 Embedder/ChromaStore/Pipeline
**问题**: Embedder 模型加载两次（双倍内存约 500MB），BM25 索引可能竞态
**解决**: 改为通过 `api.dependencies` 获取共享实例
**约束**: 新增后台任务时必须复用 API 层服务实例

## 2026-04-14 BaseLoader 签名不一致
**场景**: 基类定义 `load(self, source: str)` 但子类有额外参数
**问题**: 破坏类型安全（LSP），IDE 无法补全，运行时才能发现错误
**解决**: 改为 `load(self, source: str = "", **kwargs)` 模式
**约束**: 抽象基类与子类签名必须一致，kwargs 用途在 docstring 明确
