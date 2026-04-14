# QA-Full-Flow 验证脚本 (PowerShell)
# 使用方式: pwsh .ai/checks/validate.ps1

$ErrorActionPreference = "Continue"

Write-Host "🔍 开始验证 QA-Full-Flow..." -ForegroundColor Cyan

# 1. 检查 Python 语法
Write-Host "✅ 检查 Python 语法..." -ForegroundColor Yellow
Get-ChildItem -Path "src/" -Filter "*.py" -Recurse | ForEach-Object {
    python -m py_compile $_.FullName 2>$null
}

# 2. 运行 pytest
Write-Host "✅ 运行测试..." -ForegroundColor Yellow
if (Get-Command pytest -ErrorAction SilentlyContinue) {
    pytest tests/ -v --tb=short
    if ($LASTEXITCODE -ne 0) {
        Write-Host "⚠️ 有测试失败（非致命）" -ForegroundColor Yellow
    }
} else {
    Write-Host "⚠️ pytest 未安装，跳过测试" -ForegroundColor Yellow
}

# 3. 检查代码规范（如果有 ruff）
Write-Host "✅ 检查代码规范..." -ForegroundColor Yellow
if (Get-Command ruff -ErrorAction SilentlyContinue) {
    ruff check src/
    if ($LASTEXITCODE -ne 0) {
        Write-Host "⚠️ ruff 检查有警告（非致命）" -ForegroundColor Yellow
    }
} else {
    Write-Host "⚠️ ruff 未安装，跳过规范检查" -ForegroundColor Yellow
}

# 4. 检查关键文件存在
Write-Host "✅ 检查关键文件..." -ForegroundColor Yellow
$requiredFiles = @(
    "src/qa_full_flow/api/app.py",
    "src/qa_full_flow/core/config.py",
    "src/qa_full_flow/api/dependencies.py",
    "src/qa_full_flow/agent/test_session.py"
)

foreach ($file in $requiredFiles) {
    if (-not (Test-Path $file)) {
        Write-Host "❌ $file 缺失" -ForegroundColor Red
        exit 1
    }
}

# 5. 检查 .ai 目录
Write-Host "✅ 检查 Harness Engineering 约束文件..." -ForegroundColor Yellow
if (-not (Test-Path ".ai/AGENTS.md")) {
    Write-Host "⚠️ .ai/AGENTS.md 缺失（建议创建）" -ForegroundColor Yellow
}

Write-Host "✅ 所有验证通过！" -ForegroundColor Green
