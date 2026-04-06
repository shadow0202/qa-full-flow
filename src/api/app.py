"""FastAPI应用主模块"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from src.config import settings
from src.embedding.embedder import Embedder
from src.vector_store.chroma_store import ChromaStore
from src.retrieval.retriever import Retriever
from src.retrieval.reranker import Reranker
from src.data_pipeline.pipeline import DataPipeline
from src.data_pipeline.loaders.jsonl_loader import JSONLLoader
from src.api.schemas import (
    IngestRequest, IngestResponse,
    SearchRequest, SearchResponse, SearchResult,
    TestCaseGenerateRequest, TestCaseGenerateResponse,
    TestCaseSaveRequest, TestCaseSaveResponse,
    CollectionInfoResponse,
    # 分阶段API Schema
    TestCaseSessionCreateRequest, TestCaseSessionCreateResponse,
    TestCasePhase1Request, TestCasePhase1Response,
    TestCaseConfirmRequest, TestCaseConfirmResponse,
    TestCasePhase2Request, TestCasePhase2Response,
    TestCasePhase3Request, TestCasePhase3Response,
    TestCasePhase4Request, TestCasePhase4Response,
    TestCaseSessionInfoResponse,
    # 知识库同步 Schema
    KnowledgeSyncRequest, KnowledgeSyncResponse,
)


# 全局服务实例
embedder: Embedder = None
vector_store: ChromaStore = None
retriever: Retriever = None
reranker: Reranker = None
pipeline: DataPipeline = None
test_agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    print("\n" + "="*50)
    print("🚀 正在初始化AI测试用例与知识库系统...")
    print("="*50)
    
    global embedder, vector_store, retriever, reranker, pipeline, test_agent

    embedder = Embedder()
    vector_store = ChromaStore()
    
    # 初始化 Reranker（可选）
    try:
        reranker = Reranker()
        print("✅ Reranker服务已初始化")
    except Exception as e:
        print(f"⚠️  Reranker初始化失败: {e}，将使用纯向量检索")
        reranker = None
    
    retriever = Retriever(embedder, vector_store, reranker=reranker)
    pipeline = DataPipeline(embedder, vector_store)

    # 构建 BM25 索引（用于混合检索）
    try:
        print("\n🔍 正在构建 BM25 索引...")
        all_docs = vector_store.get()
        if all_docs.get("ids"):
            documents = [
                {"doc_id": doc_id, "content": doc, "metadata": meta}
                for doc_id, doc, meta in zip(
                    all_docs["ids"],
                    all_docs["documents"],
                    all_docs["metadatas"]
                )
            ]
            retriever.build_bm25_index(documents)
            print(f"✅ BM25 索引已构建，共 {len(documents)} 个文档")
        else:
            print("ℹ️  向量库为空，BM25 索引将在数据入库时构建")
    except Exception as e:
        print(f"⚠️  BM25 索引构建失败: {e}")
    
    # 初始化Agent（可选LLM）
    try:
        from src.agent.test_agent import TestAgent
        from src.agent.llm_service import LLMService
        
        llm = LLMService()
        if llm.is_available():
            print("🤖 LLM服务可用，启用AI测试用例生成")
        else:
            print("⚠️  LLM服务未配置，使用简单模板模式")
        
        # 注意：传入embedder和vector_store以支持保存到知识库
        test_agent = TestAgent(retriever, llm, embedder, vector_store)
    except Exception as e:
        print(f"⚠️  Agent初始化失败: {e}，将使用基础功能")
    
    print("\n✅ 系统初始化完成，准备就绪！\n")
    
    yield
    
    # 关闭时清理（如果需要）
    print("\n👋 系统关闭")


def create_app() -> FastAPI:
    """创建FastAPI应用"""
    app = FastAPI(
        title="AI测试用例与知识库系统",
        description="基于向量知识库的智能测试用例生成与检索系统",
        version="0.2.0",
        lifespan=lifespan
    )
    
    # 健康检查
    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "service": "AI测试用例与知识库系统",
            "version": "0.2.0"
        }
    
    # 数据入库API
    @app.post("/api/v1/ingest", response_model=IngestResponse)
    async def ingest_data(request: IngestRequest):
        """数据入库接口"""
        try:
            loader = JSONLLoader()
            stats = pipeline.ingest(
                loader=loader,
                source=request.source_path,
                skip_existing=request.skip_existing
            )
            
            return IngestResponse(
                success=True,
                message="数据入库完成",
                stats=stats
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"入库失败: {str(e)}")
    
    # 检索API
    @app.post("/api/v1/search", response_model=SearchResponse)
    async def search_knowledge(request: SearchRequest):
        """知识库检索接口"""
        try:
            results = retriever.search(
                query=request.query,
                n_results=request.n_results,
                filters=request.filters
            )
            
            formatted_results = [
                SearchResult(
                    rank=r["rank"],
                    content=r["content"],
                    metadata=r["metadata"],
                    similarity=r.get("similarity")
                )
                for r in results
            ]
            
            return SearchResponse(
                success=True,
                query=request.query,
                results=formatted_results,
                total=len(results)
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"检索失败: {str(e)}")
    
    # 知识库信息API
    @app.get("/api/v1/collection/info", response_model=CollectionInfoResponse)
    async def get_collection_info():
        """获取知识库信息"""
        try:
            info = retriever.get_collection_info()
            return CollectionInfoResponse(
                success=True,
                info=info
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"获取信息失败: {str(e)}")

    # 知识库统一同步API
    @app.post("/api/v1/knowledge/sync", response_model=KnowledgeSyncResponse)
    async def sync_knowledge(request: KnowledgeSyncRequest):
        """
        知识库统一同步接口

        支持三种数据源类型：
        - jsonl: 本地 JSONL 文件上传
        - bug: 从 JIRA 拉取缺陷数据
        - doc: 从 Confluence 获取文档数据
        """
        try:
            sync_type = request.type
            config = request.config
            update_mode = request.update_mode

            print(f"\n🔄 开始知识库同步: type={sync_type}, mode={update_mode}")

            if sync_type == "jsonl":
                # JSONL 文件上传
                file_path = config.get("file_path")
                if not file_path:
                    raise HTTPException(status_code=400, detail="缺少 file_path 参数")

                from src.data_pipeline.loaders.jsonl_loader import JSONLLoader
                from src.data_pipeline.chunker import RecursiveCharacterSplitter

                loader = JSONLLoader()
                chunker = RecursiveCharacterSplitter(
                    chunk_size=config.get("chunk_size", 500),
                    chunk_overlap=config.get("chunk_overlap", 50)
                )

                # 临时替换 pipeline 的 chunker
                original_chunker = pipeline.chunker
                pipeline.chunker = chunker
                stats = pipeline.ingest(loader, file_path, update_mode=update_mode)
                pipeline.chunker = original_chunker

                return KnowledgeSyncResponse(
                    success=True,
                    message="JSONL 文件同步完成",
                    stats=stats
                )

            elif sync_type == "bug":
                # JIRA 缺陷同步
                jira_url = config.get("jira_url")
                jira_email = config.get("jira_email")
                jira_token = config.get("jira_api_token")

                if not all([jira_url, jira_email, jira_token]):
                    raise HTTPException(
                        status_code=400,
                        detail="缺少 jira_url, jira_email, 或 jira_api_token 参数"
                    )

                from src.data_pipeline.loaders.jira_loader import JiraLoader

                loader = JiraLoader(
                    url=jira_url,
                    email=jira_email,
                    api_token=jira_token,
                    project_key=config.get("project_key", ""),
                    verify_ssl=True
                )

                # 测试连接
                if not loader.test_connection():
                    raise HTTPException(status_code=500, detail="JIRA 连接失败")

                stats = pipeline.ingest(
                    loader,
                    source="",
                    update_mode=update_mode,
                    issue_type=config.get("issue_type", "Bug"),
                    status=config.get("status", ""),
                    max_results=config.get("max_results", 100)
                )

                return KnowledgeSyncResponse(
                    success=True,
                    message="JIRA 缺陷同步完成",
                    stats=stats
                )

            elif sync_type == "doc":
                # Confluence 文档同步
                confl_url = config.get("confluence_url")
                confl_email = config.get("confluence_email")
                confl_token = config.get("confluence_api_token")

                if not all([confl_url, confl_email, confl_token]):
                    raise HTTPException(
                        status_code=400,
                        detail="缺少 confluence_url, confluence_email, 或 confluence_api_token 参数"
                    )

                from src.data_pipeline.loaders.confluence_loader import ConfluenceLoader

                loader = ConfluenceLoader(
                    url=confl_url,
                    email=confl_email,
                    api_token=confl_token,
                    verify_ssl=True
                )

                # 测试连接
                if not loader.test_connection():
                    raise HTTPException(status_code=500, detail="Confluence 连接失败")

                stats = pipeline.ingest(
                    loader,
                    source="",
                    update_mode=update_mode,
                    space_key=config.get("space_key", ""),
                    max_results=config.get("max_results", 50)
                )

                return KnowledgeSyncResponse(
                    success=True,
                    message="Confluence 文档同步完成",
                    stats=stats
                )

            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"不支持的数据源类型: {sync_type}，支持: jsonl, bug, doc"
                )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"同步失败: {str(e)}")
    
    # 测试用例生成API
    @app.post("/api/v1/testcase/generate", response_model=TestCaseGenerateResponse)
    async def generate_testcase(request: TestCaseGenerateRequest):
        """AI生成测试用例（支持PRD、技术文档、补充文档链接）"""
        try:
            if test_agent is None:
                raise HTTPException(status_code=503, detail="Agent未初始化")

            # 1. 从Confluence链接获取文档内容
            prd_docs = []
            tech_docs = []
            other_docs = []
            
            # 获取Confluence Loader（如果可用）
            confl_loader = None
            try:
                from src.data_pipeline.loaders.confluence_loader import ConfluenceLoader
                from src.config import settings
                
                # 检查Confluence配置
                if settings.confluence_url and settings.confluence_email and settings.confluence_api_token:
                    confl_loader = ConfluenceLoader(
                        url=settings.confluence_url,
                        email=settings.confluence_email,
                        api_token=settings.confluence_api_token,
                        verify_ssl=True
                    )
                    print("✅ Confluence连接器已初始化")
                else:
                    print("⚠️  Confluence未配置，跳过文档获取")
            except Exception as e:
                print(f"⚠️  初始化Confluence连接器失败: {e}")
            
            # 获取PRD文档（必填）
            if confl_loader and request.prd_url:
                print(f"\n📥 正在获取PRD文档...")
                prd_doc = confl_loader.load_from_url(request.prd_url)
                if prd_doc:
                    prd_docs.append(prd_doc)
                else:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"无法获取PRD文档，请检查URL是否正确: {request.prd_url}"
                    )
            
            # 获取技术文档（非必填）
            if confl_loader and request.tech_doc_urls:
                print(f"\n📥 正在获取技术文档...")
                tech_docs = confl_loader.load_from_urls(request.tech_doc_urls)
            
            # 获取补充文档（非必填）
            if confl_loader and request.other_doc_urls:
                print(f"\n📥 正在获取补充文档...")
                other_docs = confl_loader.load_from_urls(request.other_doc_urls)
            
            # 2. 构建需求描述（从PRD文档中提取）
            requirement = ""
            if prd_docs:
                # 使用PRD标题和内容前500字符作为需求描述
                prd_title = prd_docs[0].get("metadata", {}).get("page_title", "")
                prd_content = prd_docs[0].get("content", "")
                requirement = f"{prd_title}\n\n{prd_content[:500]}..."
            else:
                requirement = f"PRD链接: {request.prd_url}"
            
            # 3. 使用Agent生成测试用例
            result = test_agent.generate_test_cases(
                requirement=requirement,
                module=request.module,
                n_examples=request.n_examples,
                reference_count=request.reference_count,
                save_to_kb=request.save_to_kb,
                prd_docs=prd_docs,
                tech_docs=tech_docs,
                other_docs=other_docs,
                use_knowledge_base=request.use_knowledge_base
            )

            formatted_refs = [
                SearchResult(
                    rank=r["rank"],
                    content=r["content"],
                    metadata=r["metadata"],
                    similarity=r.get("similarity")
                )
                for r in result.get("references", [])
            ]

            return TestCaseGenerateResponse(
                success=True,
                requirement=requirement,
                test_cases=result["test_cases"],
                references=formatted_refs,
                saved_to_kb=result.get("saved_to_kb", 0)
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")
    
    # 手动保存测试用例到知识库
    @app.post("/api/v1/testcase/save", response_model=TestCaseSaveResponse)
    async def save_testcase(request: TestCaseSaveRequest):
        """手动保存测试用例到知识库"""
        try:
            if test_agent is None:
                raise HTTPException(status_code=503, detail="Agent未初始化")

            # 调用Agent的保存方法
            saved_count = test_agent._save_test_cases_to_kb(
                test_cases=request.test_cases,
                requirement=request.requirement,
                module=request.module
            )

            return TestCaseSaveResponse(
                success=True,
                message=f"成功保存 {saved_count} 个测试用例到知识库",
                saved_count=saved_count
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")

    # ============ 分阶段测试用例生成API ============

    @app.post("/api/v1/testcase/session/create", response_model=TestCaseSessionCreateResponse)
    async def create_testcase_session(request: TestCaseSessionCreateRequest):
        """创建测试用例会话"""
        try:
            from src.agent.test_session import session_manager
            
            config = {
                "prd_url": request.prd_url,
                "tech_doc_urls": request.tech_doc_urls or [],
                "other_doc_urls": request.other_doc_urls or [],
                "module": request.module,
                "use_knowledge_base": request.use_knowledge_base,
                "n_examples": request.n_examples
            }
            
            session = session_manager.create_session(config)
            
            return TestCaseSessionCreateResponse(
                success=True,
                session_id=session.session_id,
                status=session.status.value,
                message=f"会话已创建，可以开始执行阶段1"
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"创建会话失败: {str(e)}")

    @app.post("/api/v1/testcase/session/{session_id}/phase1", response_model=TestCasePhase1Response)
    async def execute_phase1(session_id: str):
        """执行阶段1：需求分析与测试点提取"""
        try:
            from src.agent.test_session import session_manager
            from src.data_pipeline.loaders.confluence_loader import ConfluenceLoader
            from src.agent.test_phase1_analyzer import Phase1Analyzer
            from src.agent.llm_service import LLMService
            
            # 获取会话
            session = session_manager.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="会话不存在")
            
            # 验证状态转换
            if not session_manager.validate_transition(session, "phase1"):
                raise HTTPException(
                    status_code=400, 
                    detail=f"当前状态 {session.status.value} 不允许执行阶段1"
                )
            
            # 获取Confluence文档
            confl_loader = ConfluenceLoader(
                url=settings.confluence_url,
                email=settings.confluence_email,
                api_token=settings.confluence_api_token
            )
            
            prd_doc = confl_loader.load_from_url(session.config["prd_url"])
            if not prd_doc:
                raise HTTPException(status_code=400, detail="无法获取PRD文档")
            
            tech_docs = confl_loader.load_from_urls(session.config.get("tech_doc_urls", []))
            other_docs = confl_loader.load_from_urls(session.config.get("other_doc_urls", []))
            
            # 保存文档到会话
            session.add_artifact("prd_doc", prd_doc)
            session.add_artifact("tech_docs", tech_docs)
            session.add_artifact("other_docs", other_docs)
            
            # 执行阶段1分析
            llm = LLMService()
            analyzer = Phase1Analyzer(llm, retriever)
            
            result = analyzer.analyze(
                prd_content=prd_doc.get("content", ""),
                module=session.config["module"],
                tech_doc_contents=[d.get("content", "") for d in tech_docs],
                other_doc_contents=[d.get("content", "") for d in other_docs],
                use_knowledge_base=session.config.get("use_knowledge_base", True),
                prd_url=session.config["prd_url"],
                tech_doc_urls=session.config.get("tech_doc_urls", []),
                other_doc_urls=session.config.get("other_doc_urls", [])
            )
            
            # 保存结果到会话
            session.add_artifact("analysis_doc", result["analysis_doc"])
            session.add_artifact("analysis_result", result["analysis_result"])
            session.update_status("phase1_done")
            
            return TestCasePhase1Response(
                success=True,
                session_id=session_id,
                status=session.status.value,
                analysis_doc=result["analysis_doc"],
                function_points_count=result["function_points_count"],
                pending_confirmations=result["pending_confirmations"],
                message=f"阶段1完成，请复核测试点分析文档"
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"阶段1执行失败: {str(e)}")

    @app.post("/api/v1/testcase/session/{session_id}/confirm", response_model=TestCaseConfirmResponse)
    async def confirm_phase(session_id: str, request: TestCaseConfirmRequest):
        """确认阶段结果"""
        try:
            from src.agent.test_session import session_manager
            
            session = session_manager.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="会话不存在")
            
            if not request.confirmed:
                # 用户未确认，记录反馈
                if request.feedback:
                    session.add_feedback(session.status.value, request.feedback)
                return TestCaseConfirmResponse(
                    success=True,
                    session_id=session_id,
                    status=session.status.value,
                    message=f"已记录反馈，请修改后重新执行当前阶段"
                )
            
            # 用户确认，推进状态
            status_map = {
                "phase1_done": "phase1_confirmed",
                "phase2_done": "phase2_confirmed",
                "phase3_done": "phase3_confirmed"
            }
            
            current_status = session.status.value
            if current_status in status_map:
                from src.agent.test_session import SessionStatus
                session.update_status(SessionStatus(status_map[current_status]))
            
            return TestCaseConfirmResponse(
                success=True,
                session_id=session_id,
                status=session.status.value,
                message=f"已确认，可以继续下一阶段"
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"确认失败: {str(e)}")

    @app.post("/api/v1/testcase/session/{session_id}/phase2", response_model=TestCasePhase2Response)
    async def execute_phase2(session_id: str):
        """执行阶段2：测试用例设计"""
        try:
            from src.agent.test_session import session_manager
            from src.agent.test_phase2_generator import Phase2Generator
            from src.agent.llm_service import LLMService
            
            session = session_manager.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="会话不存在")
            
            if not session_manager.validate_transition(session, "phase2"):
                raise HTTPException(
                    status_code=400,
                    detail=f"当前状态 {session.status.value} 不允许执行阶段2"
                )
            
            # 获取阶段1的结果
            analysis_result = session.artifacts.get("analysis_result", {})
            analysis_doc = session.artifacts.get("analysis_doc", "")
            prd_doc = session.artifacts.get("prd_doc", {})
            tech_docs = session.artifacts.get("tech_docs", [])
            other_docs = session.artifacts.get("other_docs", [])
            
            # 执行阶段2
            llm = LLMService()
            generator = Phase2Generator(llm)
            
            result = generator.generate_test_cases(
                analysis_result=analysis_result,
                analysis_doc=analysis_doc,
                module=session.config["module"],
                n_examples=session.config.get("n_examples", 5),
                prd_content=prd_doc.get("content", ""),
                tech_doc_content="\n\n".join([d.get("content", "") for d in tech_docs]),
                other_doc_content="\n\n".join([d.get("content", "") for d in other_docs])
            )
            
            # 保存结果
            session.add_artifact("test_cases", result["test_cases"])
            session.add_artifact("test_cases_json", result["json_output"])
            session.update_status("phase2_done")
            
            return TestCasePhase2Response(
                success=True,
                session_id=session_id,
                status=session.status.value,
                test_cases=result["test_cases"],
                statistics=result["statistics"],
                message=f"阶段2完成，生成了 {result['statistics']['total_test_cases']} 个测试用例"
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"阶段2执行失败: {str(e)}")

    @app.post("/api/v1/testcase/session/{session_id}/phase3", response_model=TestCasePhase3Response)
    async def execute_phase3(session_id: str):
        """执行阶段3：测试用例自审"""
        try:
            from src.agent.test_session import session_manager
            from src.agent.test_phase3_reviewer import Phase3Reviewer
            
            session = session_manager.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="会话不存在")
            
            if not session_manager.validate_transition(session, "phase3"):
                raise HTTPException(
                    status_code=400,
                    detail=f"当前状态 {session.status.value} 不允许执行阶段3"
                )
            
            # 获取需要的产物
            test_cases = session.artifacts.get("test_cases", [])
            analysis_result = session.artifacts.get("analysis_result", {})
            analysis_doc = session.artifacts.get("analysis_doc", "")
            
            # 执行阶段3
            reviewer = Phase3Reviewer()
            
            result = reviewer.review(
                test_cases=test_cases,
                analysis_result=analysis_result,
                analysis_doc=analysis_doc,
                module=session.config["module"]
            )
            
            # 保存结果
            session.add_artifact("review_report", result["review_report"])
            session.update_status("phase3_done")
            
            return TestCasePhase3Response(
                success=True,
                session_id=session_id,
                status=session.status.value,
                review_report=result["review_report"],
                coverage_rate=result["coverage_rate"],
                issues_found=result["issues_found"],
                supplemented_cases=result["supplemented_cases"],
                message=f"阶段3完成，发现问题 {result['issues_found']} 个"
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"阶段3执行失败: {str(e)}")

    @app.post("/api/v1/testcase/session/{session_id}/phase4", response_model=TestCasePhase4Response)
    async def execute_phase4(session_id: str):
        """执行阶段4：交付"""
        try:
            from src.agent.test_session import session_manager
            from src.agent.test_phase4_deliver import Phase4Deliverer
            
            session = session_manager.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="会话不存在")
            
            if not session_manager.validate_transition(session, "phase4"):
                raise HTTPException(
                    status_code=400,
                    detail=f"当前状态 {session.status.value} 不允许执行阶段4"
                )
            
            # 获取所有产物
            analysis_doc = session.artifacts.get("analysis_doc", "")
            test_cases = session.artifacts.get("test_cases", [])
            review_report = session.artifacts.get("review_report", "")
            
            # 获取统计信息（从阶段2）
            test_cases_json = session.artifacts.get("test_cases_json", {})
            statistics = test_cases_json.get("metadata", {})
            
            # 执行阶段4
            deliverer = Phase4Deliverer()
            
            result = deliverer.deliver(
                module=session.config["module"],
                analysis_doc=analysis_doc,
                test_cases=test_cases,
                review_report=review_report,
                statistics=statistics
            )
            
            # 保存结果
            session.add_artifact("deliverables", result["deliverables"])
            session.add_artifact("delivery_list", result["delivery_list"])
            session.update_status("completed")
            
            return TestCasePhase4Response(
                success=True,
                session_id=session_id,
                status=session.status.value,
                deliverables=result["deliverables"],
                summary=result["summary"],
                message=f"🎉 全流程完成！生成了 {result['summary']['total_cases']} 个测试用例"
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"阶段4执行失败: {str(e)}")

    @app.get("/api/v1/testcase/session/{session_id}", response_model=TestCaseSessionInfoResponse)
    async def get_session_info(session_id: str):
        """获取会话信息"""
        try:
            from src.agent.test_session import session_manager
            
            session = session_manager.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="会话不存在")
            
            return TestCaseSessionInfoResponse(
                success=True,
                session_id=session_id,
                status=session.status.value,
                config=session.config,
                artifacts={
                    k: v for k, v in session.artifacts.items()
                    if k != "test_cases"  # 用例数据可能很大
                },
                created_at=session.created_at,
                updated_at=session.updated_at
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"获取会话信息失败: {str(e)}")

    return app
