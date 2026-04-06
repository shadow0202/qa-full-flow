"""API数据模型"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, List


class TestCaseSource(BaseModel):
    """测试用例来源标注"""
    document_type: str = Field(..., description="文档类型: PRD文档/技术文档/补充文档/历史用例")
    section: str = Field(..., description="对应的章节或功能模块名称")
    quote: str = Field(..., description="文档中的原文引用（20-50字）")


class TestCaseItem(BaseModel):
    """测试用例项"""
    title: str = Field(..., description="用例标题")
    priority: str = Field(..., description="优先级: P0/P1/P2")
    precondition: str = Field("", description="前置条件")
    steps: List[str] = Field(default_factory=list, description="测试步骤")
    expected: str = Field(..., description="预期结果")
    tags: List[str] = Field(default_factory=list, description="标签")
    source: Optional[TestCaseSource] = Field(None, description="来源标注（新增）")
    confidence: Optional[float] = Field(None, description="置信度评分 0.0-1.0（新增）")


class IngestRequest(BaseModel):
    """数据入库请求"""
    source_path: str = Field(..., description="数据源文件路径")
    source_type: str = Field("jsonl", description="数据源类型")
    skip_existing: bool = Field(True, description="是否跳过已存在的数据")


class IngestResponse(BaseModel):
    """数据入库响应"""
    success: bool
    message: str
    stats: Optional[Dict] = None


class SearchRequest(BaseModel):
    """检索请求"""
    query: str = Field(..., description="查询文本")
    n_results: int = Field(5, description="返回结果数", ge=1, le=20)
    filters: Optional[Dict] = Field(None, description="过滤条件")


class SearchResult(BaseModel):
    """检索结果"""
    rank: int
    content: str
    metadata: Dict
    similarity: Optional[float] = None


class SearchResponse(BaseModel):
    """检索响应"""
    success: bool
    query: str
    results: List[SearchResult]
    total: int


class TestCaseGenerateRequest(BaseModel):
    """测试用例生成请求"""
    # 必填：PRD文档链接
    prd_url: str = Field(..., description="PRD文档的Confluence链接（必填）")
    
    # 非必填：技术文档链接列表
    tech_doc_urls: Optional[List[str]] = Field(
        default_factory=list, 
        description="技术文档的Confluence链接列表（非必填）"
    )
    
    # 非必填：其他补充文档链接列表
    other_doc_urls: Optional[List[str]] = Field(
        default_factory=list, 
        description="其他补充文档的Confluence链接列表（非必填）"
    )
    
    # 知识库控制
    use_knowledge_base: bool = Field(
        True, 
        description="是否使用知识库中的历史用例作为参考（默认true）"
    )
    reference_count: int = Field(
        3, 
        description="参考历史用例数（仅当use_knowledge_base=true时有效）"
    )
    
    # 生成控制
    module: str = Field(..., description="所属模块")
    n_examples: int = Field(3, description="生成用例数量", ge=1, le=10)
    save_to_kb: bool = Field(True, description="是否保存到知识库")


class TestCaseGenerateResponse(BaseModel):
    """测试用例生成响应"""
    success: bool
    requirement: str
    test_cases: List[TestCaseItem]
    references: Optional[List[SearchResult]] = None
    saved_to_kb: int = Field(0, description="保存到知识库的数量")
    doc_stats: Optional[Dict] = Field(None, description="文档统计信息")


class TestCaseSaveRequest(BaseModel):
    """手动保存测试用例请求"""
    test_cases: List[Dict] = Field(..., description="测试用例列表")
    requirement: str = Field("", description="关联需求")
    module: str = Field(..., description="所属模块")


class TestCaseSaveResponse(BaseModel):
    """手动保存测试用例响应"""
    success: bool
    message: str
    saved_count: int = Field(0, description="保存数量")


class CollectionInfoResponse(BaseModel):
    """知识库信息响应"""
    success: bool
    info: Dict


# ============ 分阶段测试用例生成 Schema ============

class TestCaseSessionCreateRequest(BaseModel):
    """创建测试用例会话请求"""
    prd_url: str = Field(..., description="PRD文档的Confluence链接（必填）")
    tech_doc_urls: Optional[List[str]] = Field(
        default_factory=list, 
        description="技术文档的Confluence链接列表（非必填）"
    )
    other_doc_urls: Optional[List[str]] = Field(
        default_factory=list, 
        description="其他补充文档的Confluence链接列表（非必填）"
    )
    module: str = Field(..., description="所属模块")
    use_knowledge_base: bool = Field(True, description="是否使用知识库")
    n_examples: int = Field(5, description="期望生成用例数量", ge=1, le=20)


class TestCaseSessionCreateResponse(BaseModel):
    """创建测试用例会话响应"""
    success: bool
    session_id: str
    status: str
    message: str


class TestCasePhase1Request(BaseModel):
    """阶段1请求（无需额外参数，使用会话配置）"""
    pass


class TestCasePhase1Response(BaseModel):
    """阶段1响应"""
    success: bool
    session_id: str
    status: str
    analysis_doc: str = Field(..., description="测试点分析文档")
    function_points_count: int = Field(0, description="功能点数量")
    pending_confirmations: int = Field(0, description="待确认项数量")
    message: str


class TestCaseConfirmRequest(BaseModel):
    """确认请求"""
    confirmed: bool = Field(..., description="是否确认通过")
    feedback: Optional[str] = Field(None, description="用户反馈意见")


class TestCaseConfirmResponse(BaseModel):
    """确认响应"""
    success: bool
    session_id: str
    status: str
    message: str


class TestCasePhase2Request(BaseModel):
    """阶段2请求"""
    pass


class TestCasePhase2Response(BaseModel):
    """阶段2响应"""
    success: bool
    session_id: str
    status: str
    test_cases: List[Dict] = Field(..., description="生成的测试用例")
    statistics: Dict = Field(..., description="用例统计信息")
    message: str


class TestCasePhase3Request(BaseModel):
    """阶段3请求"""
    pass


class TestCasePhase3Response(BaseModel):
    """阶段3响应"""
    success: bool
    session_id: str
    status: str
    review_report: str = Field(..., description="自审报告")
    coverage_rate: float = Field(0.0, description="功能覆盖率")
    issues_found: int = Field(0, description="发现问题数")
    supplemented_cases: int = Field(0, description="补充用例数")
    message: str


class TestCasePhase4Request(BaseModel):
    """阶段4请求"""
    pass


class TestCasePhase4Response(BaseModel):
    """阶段4响应"""
    success: bool
    session_id: str
    status: str
    deliverables: Dict = Field(..., description="交付物清单")
    summary: Dict = Field(..., description="统计汇总")
    message: str


class TestCaseSessionInfoResponse(BaseModel):
    """会话信息响应"""
    success: bool
    session_id: str
    status: str
    config: Dict
    artifacts: Dict
    created_at: str
    updated_at: str


class KnowledgeSyncRequest(BaseModel):
    """知识库统一同步请求"""
    type: str = Field(..., description="数据源类型: jsonl, bug, doc")
    config: Dict = Field(..., description="配置参数，根据type不同而不同")
    """
    type="jsonl" 时:
        - file_path: str (JSONL 文件路径)
        - chunk_size: int (可选，默认500)
        - chunk_overlap: int (可选，默认50)

    type="bug" 时:
        - jira_url: str (JIRA 地址)
        - jira_email: str (邮箱)
        - jira_api_token: str (API Token)
        - project_key: str (项目Key，可选)
        - issue_type: str (问题类型，默认Bug)
        - status: str (状态过滤，可选)
        - max_results: int (最大结果数，默认100)

    type="doc" 时:
        - confluence_url: str (Confluence 地址)
        - confluence_email: str (邮箱)
        - confluence_api_token: str (API Token)
        - space_key: str (空间Key，可选)
        - max_results: int (最大结果数，默认50)
    """
    update_mode: str = Field("incremental", description="更新模式: skip, incremental, force")


class KnowledgeSyncResponse(BaseModel):
    """知识库统一同步响应"""
    success: bool
    message: str
    stats: Optional[Dict] = None
    """
    stats 包含:
        - loaded: 加载的文档数
        - ingested: 入库的文档数
        - skipped: 跳过的文档数
        - updated: 更新的文档数
    """
