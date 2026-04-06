FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY pyproject.toml uv.lock ./

# 安装uv
RUN pip install --no-cache-dir uv

# 安装项目依赖
RUN uv sync --frozen --no-dev

# 复制源代码
COPY src/ ./src/
COPY configs/ ./configs/

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["uv", "run", "python", "-m", "src.qa_full_flow", "start-api", "--host", "0.0.0.0", "--port", "8000"]
