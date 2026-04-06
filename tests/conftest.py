"""
Pytest配置和通用Fixtures

按照Superpowers的TDD原则，提供完整的测试基础设施。
"""
import pytest
from pathlib import Path
from typing import Dict, Any
from unittest.mock import Mock, MagicMock
import os
import tempfile
import json


# ============ 目录Fixtures ============

@pytest.fixture
def project_root() -> Path:
    """项目根目录"""
    return Path(__file__).parent.parent


@pytest.fixture
def temp_dir():
    """临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def data_dir(project_root: Path) -> Path:
    """数据目录"""
    data = project_root / "data"
    data.mkdir(exist_ok=True)
    return data


# ============ 配置Fixtures ============

@pytest.fixture
def mock_settings():
    """Mock配置"""
    from unittest.mock import patch
    
    settings_dict = {
        "EMBEDDING_MODEL": "BAAI/bge-m3",
        "EMBEDDING_DEVICE": "cpu",
        "CHROMA_PATH": ":memory:",
        "CHROMA_COLLECTION_NAME": "test_knowledge",
        "LLM_API_KEY": "test-key",
        "LLM_BASE_URL": "https://api.test.com/v1",
        "LLM_MODEL": "gpt-3.5-turbo",
        "CONFLUENCE_URL": "https://test.atlassian.net/wiki",
        "CONFLUENCE_EMAIL": "test@test.com",
        "CONFLUENCE_API_TOKEN": "test-token",
    }
    
    with patch.dict(os.environ, settings_dict, clear=True):
        yield settings_dict


# ============ 数据库Fixtures ============

@pytest.fixture
def chroma_client():
    """ChromaDB测试客户端"""
    try:
        import chromadb
        client = chromadb.Client()
        yield client
    except ImportError:
        pytest.skip("chromadb not installed")


@pytest.fixture
def test_collection(chroma_client):
    """测试集合"""
    collection = chroma_client.create_collection(
        name="test_collection",
        metadata={"hnsw:space": "cosine"}
    )
    yield collection
    chroma_client.delete_collection("test_collection")


# ============ API Fixtures ============

@pytest.fixture
def app():
    """FastAPI应用实例"""
    from src.api.app import create_app
    return create_app()


@pytest.fixture
async def client(app):
    """HTTP测试客户端"""
    from httpx import AsyncClient, ASGITransport
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ============ LLM Service Fixtures ============

@pytest.fixture
def mock_llm_response():
    """Mock LLM响应"""
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps([
                        {
                            "title": "测试用例1",
                            "priority": "P0",
                            "precondition": "前置条件",
                            "steps": ["步骤1", "步骤2"],
                            "expected": "预期结果",
                            "tags": ["标签1"]
                        }
                    ])
                }
            }
        ]
    }


@pytest.fixture
def mock_llm_service(mock_llm_response):
    """Mock LLM服务"""
    from unittest.mock import AsyncMock, patch
    from src.agent.llm_service import LLMService
    
    with patch.object(LLMService, '__init__', return_value=None):
        mock_service = LLMService()
        mock_service.is_available = Mock(return_value=True)
        mock_service.generate = Mock(return_value=json.dumps([
            {
                "title": "测试用例1",
                "priority": "P0",
                "precondition": "前置条件",
                "steps": ["步骤1", "步骤2"],
                "expected": "预期结果",
                "tags": ["标签1"]
            }
        ]))
        yield mock_service


# ============ Confluence Fixtures ============

@pytest.fixture
def sample_confluence_page() -> Dict[str, Any]:
    """示例Confluence页面"""
    return {
        "id": "123456789",
        "title": "测试需求文档",
        "spaceId": "TEST",
        "version": {
            "number": 1,
            "authorId": "user123"
        },
        "body": {
            "storage": {
                "value": "<h1>需求标题</h1><p>需求内容...</p>",
                "representation": "storage"
            }
        }
    }


@pytest.fixture
def mock_confluence_response(sample_confluence_page):
    """Mock Confluence API响应"""
    from unittest.mock import Mock, patch
    import requests
    
    mock_response = Mock(spec=requests.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = sample_confluence_page
    mock_response.raise_for_status = Mock()
    
    with patch('requests.Session.get', return_value=mock_response):
        yield mock_response


# ============ 测试数据Fixtures ============

@pytest.fixture
def sample_test_case() -> Dict[str, Any]:
    """示例测试用例"""
    return {
        "tc_id": "TC-001",
        "title": "正常流程测试",
        "priority": "P0",
        "test_type": "功能测试",
        "precondition": "系统正常运行",
        "test_steps": "1. 步骤1\n2. 步骤2",
        "test_data": "测试数据",
        "expected_result": "预期结果",
        "tags": ["功能", "正常流程"]
    }


@pytest.fixture
def sample_test_cases() -> list:
    """示例测试用例列表"""
    return [
        {
            "tc_id": "TC-001",
            "title": "正常流程测试",
            "priority": "P0",
            "test_type": "功能测试",
            "precondition": "系统正常运行",
            "test_steps": "1. 步骤1\n2. 步骤2",
            "test_data": "测试数据",
            "expected_result": "预期结果"
        },
        {
            "tc_id": "TC-002",
            "title": "异常流程测试",
            "priority": "P1",
            "test_type": "异常测试",
            "precondition": "系统正常运行",
            "test_steps": "1. 步骤1\n2. 步骤2",
            "test_data": "异常数据",
            "expected_result": "错误处理"
        }
    ]


# ============ 辅助函数 ============

@pytest.fixture
def assert_response():
    """响应断言辅助函数"""
    def _assert(response, status_code: int, expected_keys: list = None):
        assert response.status_code == status_code
        if expected_keys:
            data = response.json()
            for key in expected_keys:
                assert key in data, f"Missing key: {key}"
    return _assert
