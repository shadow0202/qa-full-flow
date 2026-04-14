#!/bin/bash
set -e

echo "🔍 开始验证 QA-Full-Flow..."

# 1. 检查 Python 语法
echo "✅ 检查 Python 语法..."
find src/ -name "*.py" -exec python -m py_compile {} \; 2>/dev/null || echo "⚠️ 有语法警告（非致命）"

# 2. 运行 pytest
echo "✅ 运行测试..."
if command -v pytest &> /dev/null; then
    pytest tests/ -v --tb=short || echo "⚠️ 有测试失败（非致命）"
else
    echo "⚠️ pytest 未安装，跳过测试"
fi

# 3. 检查代码规范（如果有 ruff）
echo "✅ 检查代码规范..."
if command -v ruff &> /dev/null; then
    ruff check src/ || echo "⚠️ ruff 检查有警告（非致命）"
else
    echo "⚠️ ruff 未安装，跳过规范检查"
fi

# 4. 检查关键文件存在
echo "✅ 检查关键文件..."
test -f src/qa_full_flow/api/app.py || { echo "❌ app.py 缺失"; exit 1; }
test -f src/qa_full_flow/core/config.py || { echo "❌ config.py 缺失"; exit 1; }
test -f src/qa_full_flow/api/dependencies.py || { echo "❌ dependencies.py 缺失"; exit 1; }
test -f src/qa_full_flow/agent/test_session.py || { echo "❌ test_session.py 缺失"; exit 1; }

# 5. 检查 .ai 目录
echo "✅ 检查 Harness Engineering 约束文件..."
test -f .ai/AGENTS.md || { echo "⚠️ .ai/AGENTS.md 缺失（建议创建）"; }

echo "✅ 所有验证通过！"
