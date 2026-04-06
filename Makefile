.PHONY: help install run api test clean

help:
	@echo "AI测试用例与知识库系统 - 快捷命令"
	@echo ""
	@echo "可用命令："
	@echo "  make install    - 安装依赖"
	@echo "  make run        - 运行主程序（测试入库和检索）"
	@echo "  make api        - 启动API服务"
	@echo "  make test       - 运行测试"
	@echo "  make clean      - 清理缓存和向量库"
	@echo ""

install:
	@echo "📦 安装依赖..."
	uv sync
	@echo "✅ 依赖安装完成"

run:
	@echo "🚀 运行主程序..."
	python main.py

api:
	@echo "🌐 启动API服务..."
	python start_api.py

test:
	@echo "🧪 运行测试..."
	python -m pytest tests/ -v

clean:
	@echo "🧹 清理缓存文件..."
	if exist data\vector_db rd /s /q data\vector_db
	if exist __pycache__ rd /s /q __pycache__
	for /d /r %d in (__pycache__) do @if exist "%d" rd /s /q "%d"
	@echo "✅ 清理完成"
