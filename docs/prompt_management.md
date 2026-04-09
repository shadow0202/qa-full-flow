# Prompt 模板管理系统

## 概述

Prompt 模板管理系统实现了 Prompt 的**可配置化**，支持：
- ✅ 从 YAML/JSON 文件加载 Prompt 模板
- ✅ 在线调整 Prompt 而无需修改代码
- ✅ 版本管理（支持多版本共存）
- ✅ 热重载（检测文件变化自动重新加载）
- ✅ 向后兼容（仍可硬编码在 Python 文件中）

## 目录结构

```
src/qa_full_flow/agent/prompts/
├── templates/                    # YAML/JSON 模板目录
│   ├── phase1_analysis.yaml     # Phase1 分析 Prompt
│   └── phase2_design.yaml       # Phase2 设计 Prompt
├── test_analysis.py             # 硬编码 Prompt（向后兼容）
└── test_design.py               # 硬编码 Prompt（向后兼容）
```

## 使用方式

### 方式 1：从文件加载（推荐）

1. **创建/编辑 YAML 模板**

```yaml
# src/qa_full_flow/agent/prompts/templates/phase1_analysis.yaml
- name: phase1_system_prompt
  version: v1
  description: "阶段1：需求分析与测试点提取 - 系统提示词"
  content: |
    你是一位资深测试专家，擅长从需求文档中提取功能点并设计测试策略。
    
    你的任务：
    1. 仔细阅读PRD文档、技术文档和补充文档
    2. 提取所有功能点，不遗浣、不编造
    ...
  variables:
    - module
    - prd_content
    - tech_doc_content
  metadata:
    author: QA Team
    created: "2026-04-09"
```

2. **在代码中使用**

```python
from src.qa_full_flow.agent.prompt_manager import get_prompt_manager

# 获取管理器
prompt_manager = get_prompt_manager(
    prompt_dir="src/qa_full_flow/agent/prompts/templates",
    enable_hot_reload=True  # 启用热重载
)

# 渲染模板
system_prompt = prompt_manager.render(
    "phase1_system_prompt",
    version="v1"
)

user_prompt = prompt_manager.render(
    "phase1_user_prompt",
    version="v1",
    module="登录",
    prd_content="...",
    tech_doc_content="..."
)
```

### 方式 2：硬编码（向后兼容）

原有的 Python 常量方式仍然可用：

```python
from src.qa_full_flow.agent.prompts.test_analysis import PHASE1_SYSTEM_PROMPT

# 直接使用硬编码常量
system_prompt = PHASE1_SYSTEM_PROMPT
```

`PromptManager` 会自动加载这些硬编码常量作为 fallback。

### 方式 3：通过 API 管理

启动服务后，可以使用 REST API 管理 Prompt：

```bash
# 查看所有 Prompt
curl http://localhost:8000/api/v1/prompts/list

# 查看指定 Prompt 详情
curl http://localhost:8000/api/v1/prompts/phase1_system_prompt/v1

# 查看最新版本
curl http://localhost:8000/api/v1/prompts/phase1_system_prompt/latest

# 重新加载所有 Prompt（修改文件后）
curl -X POST http://localhost:8000/api/v1/prompts/reload
```

## Prompt 模板格式

### YAML 格式

```yaml
- name: prompt_name              # 必填：Prompt 名称
  version: v1                    # 必填：版本号
  content: |                     # 必填：模板内容
    这是一个 {variable} 示例。
  description: "描述"            # 可选：描述
  variables:                     # 可选：变量列表（自动检测）
    - variable
  metadata:                      # 可选：元数据
    author: QA Team
    created: "2026-04-09"
    tags:
      - phase1
      - analysis
```

### JSON 格式

```json
{
  "name": "prompt_name",
  "version": "v1",
  "content": "这是一个 {variable} 示例。",
  "description": "描述",
  "variables": ["variable"],
  "metadata": {
    "author": "QA Team",
    "created": "2026-04-09"
  }
}
```

## 变量替换

模板中使用 `{variable}` 格式的占位符：

```yaml
content: |
  请分析 {module} 模块的 PRD 文档：
  
  {prd_content}
  
  技术文档：
  {tech_doc_content}
```

渲染时传入变量：

```python
prompt = prompt_manager.render(
    "phase1_user_prompt",
    version="v1",
    module="登录",
    prd_content="PRD 内容...",
    tech_doc_content="技术文档..."
)
```

## 版本管理

支持多个版本共存：

```yaml
# phase1_analysis.yaml
- name: phase1_system_prompt
  version: v1
  content: "旧版 Prompt..."

- name: phase1_system_prompt
  version: v2
  content: "新版 Prompt..."
```

获取时指定版本：

```python
# 获取指定版本
v1_prompt = prompt_manager.get("phase1_system_prompt", version="v1")

# 获取最新版（自动）
latest = prompt_manager.get("phase1_system_prompt")
```

## 热重载

启用热重载后，修改文件会自动重新加载：

```python
prompt_manager = get_prompt_manager(
    prompt_dir="path/to/templates",
    enable_hot_reload=True  # 启用热重载
)
```

或者手动触发重新加载：

```python
prompt_manager.reload()

# 或通过 API
curl -X POST http://localhost:8000/api/v1/prompts/reload
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/prompts/list` | 列出所有 Prompt |
| GET | `/api/v1/prompts/{name}/versions` | 列出指定 Prompt 的所有版本 |
| GET | `/api/v1/prompts/{name}/{version}` | 获取指定版本详情 |
| GET | `/api/v1/prompts/{name}/latest` | 获取最新版本 |
| POST | `/api/v1/prompts/reload` | 重新加载所有 Prompt |

## 配置

在 `.env` 中可以配置 Prompt 目录：

```env
# Prompt 模板目录路径
PROMPT_DIR=./src/qa_full_flow/agent/prompts/templates

# 是否启用热重载
PROMPT_HOT_RELOAD=false
```

## 最佳实践

1. **优先使用 YAML 文件**：便于管理和调整
2. **版本控制**：每次修改 Prompt 时增加版本号
3. **测试新 Prompt**：上线前充分测试
4. **保留旧版本**：不要删除旧版，便于回滚
5. **文档化**：在 `description` 中说明 Prompt 用途和变更历史

## 迁移指南

从硬编码迁移到文件加载：

### 步骤 1：创建 YAML 文件

将 Python 常量复制到 YAML 文件：

```python
# 原代码（硬编码）
PHASE1_SYSTEM_PROMPT = """你是一位专家..."""
```

```yaml
# 新文件（YAML）
- name: phase1_system_prompt
  version: v1
  content: |
    你是一位专家...
```

### 步骤 2：更新代码

```python
# 旧代码
from src.qa_full_flow.agent.prompts.test_analysis import PHASE1_SYSTEM_PROMPT

system_prompt = PHASE1_SYSTEM_PROMPT
```

```python
# 新代码
from src.qa_full_flow.agent.prompt_manager import get_prompt_manager

prompt_manager = get_prompt_manager()
system_prompt = prompt_manager.render("phase1_system_prompt", version="v1")
```

### 步骤 3：测试

确保渲染结果与原来一致。

## 故障排查

### 问题 1：找不到 Prompt 模板

**错误**：`KeyError: Prompt 模板不存在: xxx`

**原因**：
- 文件路径不正确
- YAML 格式错误
- 未指定版本号

**解决**：
1. 检查 `prompt_dir` 路径
2. 验证 YAML 格式（使用 yaml 验证工具）
3. 确保指定了正确的版本号

### 问题 2：变量替换失败

**错误**：`ValueError: Prompt 模板 'xxx' 缺少变量: yyy`

**原因**：
- 调用 `render()` 时缺少必需变量

**解决**：
```python
# 检查模板需要的变量
template = prompt_manager.get("phase1_user_prompt")
print(template.variables)  # 查看所有变量

# 确保传入所有必需变量
prompt_manager.render(
    "phase1_user_prompt",
    module="...",  # 所有必需变量
    prd_content="..."
)
```

### 问题 3：热重载不生效

**原因**：
- 未启用 `enable_hot_reload`
- 文件权限问题

**解决**：
```python
# 确认启用热重载
prompt_manager = get_prompt_manager(
    enable_hot_reload=True
)

# 或手动触发
prompt_manager.reload()
```

## 总结

Prompt 模板管理系统提供了灵活的可配置化方案：
- ✅ **在线调整**：修改 YAML 文件即可调整 Prompt
- ✅ **版本管理**：支持多版本共存和回滚
- ✅ **热重载**：检测文件变化自动重新加载
- ✅ **向后兼容**：保留原有硬编码方式
- ✅ **API 支持**：通过 REST API 管理 Prompt

**现在可以在线调整 Prompt，无需修改代码和重启服务！**
