"""API服务启动脚本"""
import uvicorn
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    uvicorn.run(
        "src.qa_full_flow.api.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
