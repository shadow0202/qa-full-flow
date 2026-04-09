"""测试Agent - AI测试用例生成与分析"""
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional
from src.agent.llm_service import LLMService
from src.agent.json_parser import extract_json_array
from src.agent.prompts.test_design import (
    TEST_CASE_GENERATION_SYSTEM_PROMPT,
    TEST_CASE_GENERATION_USER_PROMPT
)
from src.retrieval.retriever import Retriever
from src.vector_store.chroma_store import ChromaStore
from src.embedding.embedder import Embedder

logger = logging.getLogger(__name__)


class TestAgent:
    """测试Agent核心"""

    def __init__(self, retriever: Retriever,
                 llm_service: Optional[LLMService] = None,
                 embedder: Optional[Embedder] = None,
                 vector_store: Optional[ChromaStore] = None,
                 confluence_loader=None):
        self.retriever = retriever
        self.llm = llm_service
        self.embedder = embedder
        self.vector_store = vector_store
        self.confluence_loader = confluence_loader
    
    def generate_test_cases(self, requirement: str = "",
                           module: str = "",
                           n_examples: int = 3,
                           reference_count: int = 3,
                           save_to_kb: bool = True,
                           prd_docs: List[Dict] = None,
                           tech_docs: List[Dict] = None,
                           other_docs: List[Dict] = None,
                           use_knowledge_base: bool = True) -> Dict:
        """
        AI生成测试用例

        Args:
            requirement: 需求描述（兼容旧接口）
            module: 所属模块
            n_examples: 生成用例数量
            reference_count: 参考历史用例数
            save_to_kb: 是否保存到知识库
            prd_docs: PRD文档列表
            tech_docs: 技术文档列表
            other_docs: 其他补充文档列表
            use_knowledge_base: 是否使用知识库

        Returns:
            生成结果
        """
        # 1. 从文档中提取需求文本（用于检索知识库）
        search_query = requirement
        if prd_docs:
            # 优先使用PRD文档内容的一部分作为检索 query
            prd_content = prd_docs[0].get("content", "")
            search_query = prd_content[:200] if prd_content else requirement
        
        # 2. 检索相关知识（如果需要）
        references = []
        if use_knowledge_base:
            filters = {"module": module} if module else None
            references = self.retriever.search(
                query=search_query,
                n_results=reference_count,
                filters=filters
            )

        # 3. 判断是否使用LLM
        if self.llm and self.llm.is_available():
            # 使用LLM生成
            test_cases = self._generate_with_llm(
                requirement=requirement,
                module=module,
                n_examples=n_examples,
                references=references,
                prd_docs=prd_docs or [],
                tech_docs=tech_docs or [],
                other_docs=other_docs or []
            )
        else:
            # 使用简单模板
            test_cases = self._generate_simple(
                requirement=requirement,
                module=module,
                n_examples=n_examples,
                references=references
            )

        # 4. 保存到知识库
        if save_to_kb and self.vector_store and self.embedder:
            saved_count = self._save_test_cases_to_kb(test_cases, requirement, module)
        else:
            saved_count = 0

        return {
            "success": True,
            "requirement": requirement,
            "test_cases": test_cases,
            "references": references,
            "method": "llm" if (self.llm and self.llm.is_available()) else "simple",
            "saved_to_kb": saved_count,
            "doc_stats": {
                "prd_count": len(prd_docs or []),
                "tech_doc_count": len(tech_docs or []),
                "other_doc_count": len(other_docs or [])
            }
        }
    
    def _generate_with_llm(self, requirement: str, module: str,
                           n_examples: int, references: List[Dict],
                           prd_docs: List[Dict] = None,
                           tech_docs: List[Dict] = None,
                           other_docs: List[Dict] = None) -> List[Dict]:
        """使用LLM生成测试用例"""
        # 构建PRD文档内容
        prd_text = ""
        if prd_docs:
            prd_text = "\n\n".join([
                f"### PRD文档 {i+1}: {doc.get('metadata', {}).get('page_title', '未命名')}\n{doc.get('content', '')}"
                for i, doc in enumerate(prd_docs)
            ])
        
        # 构建技术文档内容
        tech_doc_text = ""
        if tech_docs:
            tech_doc_text = "\n\n".join([
                f"### 技术文档 {i+1}: {doc.get('metadata', {}).get('page_title', '未命名')}\n{doc.get('content', '')}"
                for i, doc in enumerate(tech_docs)
            ])
        
        # 构建补充文档内容
        other_doc_text = ""
        if other_docs:
            other_doc_text = "\n\n".join([
                f"### 补充文档 {i+1}: {doc.get('metadata', {}).get('page_title', '未命名')}\n{doc.get('content', '')}"
                for i, doc in enumerate(other_docs)
            ])
        
        # 构建历史参考用例内容
        ref_text = ""
        for i, ref in enumerate(references, 1):
            ref_text += f"\n{i}. [{ref['metadata'].get('source_type', 'unknown')}] {ref['content']}\n"

        if not ref_text:
            ref_text = "无历史参考用例"

        # 构建Prompt
        from src.agent.prompts.test_design import (
            TEST_CASE_GENERATION_SYSTEM_PROMPT_V2,
            TEST_CASE_GENERATION_USER_PROMPT_V2
        )
        
        user_prompt = TEST_CASE_GENERATION_USER_PROMPT_V2.format(
            requirement=requirement,
            module=module,
            prd_content=prd_text or "无PRD文档",
            tech_doc_content=tech_doc_text or "无技术文档",
            other_doc_content=other_doc_text or "无补充文档",
            references=ref_text,
            n_examples=n_examples
        )

        # 调用LLM
        response = self.llm.generate(
            system_prompt=TEST_CASE_GENERATION_SYSTEM_PROMPT_V2,
            user_prompt=user_prompt
        )

        # 解析JSON - 使用容错解析
        test_cases = extract_json_array(response)
        if test_cases:
            # 补充元数据
            for i, tc in enumerate(test_cases, 1):
                tc["doc_id"] = f"TC_GEN_{i:03d}"
                tc["module"] = module
                # 保留 LLM 输出的 source 和 confidence 字段
                # 如果 LLM 没有输出这些字段，设置默认值
                if "source" not in tc:
                    tc["source"] = {
                        "document_type": "AI推断",
                        "section": "通用测试场景",
                        "quote": "未提供来源标注"
                    }
                if "confidence" not in tc:
                    tc["confidence"] = 0.5  # 默认中等置信度

            return test_cases
        else:
            logger.warning("LLM JSON 解析失败，使用简单模板")
            return self._generate_simple(requirement, module, n_examples, references)
    
    def _generate_simple(self, requirement: str, module: str,
                        n_examples: int, references: List[Dict]) -> List[Dict]:
        """简单模板方式生成测试用例"""
        # 从参考文档中提取标签
        tags_set = set()
        for ref in references:
            tags_str = ref.get("metadata", {}).get("tags", "")
            if tags_str:
                tags_set.update(tags_str.split(","))
        
        # 生成基础测试用例
        test_cases = []
        scenarios = [
            {
                "title": f"正常流程测试 - {module}",
                "priority": "P0",
                "precondition": "系统正常运行，用户已登录",
                "steps": [
                    f"进入{module}模块",
                    "输入有效数据",
                    "提交操作",
                    "验证结果"
                ],
                "expected": "操作成功，数据正确保存"
            },
            {
                "title": f"异常流程测试 - {module}",
                "priority": "P1",
                "precondition": "系统正常运行",
                "steps": [
                    f"进入{module}模块",
                    "输入无效或异常数据",
                    "提交操作",
                    "验证错误处理"
                ],
                "expected": "系统提示错误信息，数据未保存"
            },
            {
                "title": f"边界条件测试 - {module}",
                "priority": "P1",
                "precondition": "系统正常运行",
                "steps": [
                    f"进入{module}模块",
                    "输入边界值数据（最大值、最小值、空值）",
                    "提交操作",
                    "验证系统处理"
                ],
                "expected": "系统正确处理边界情况"
            }
        ]
        
        for i in range(min(n_examples, len(scenarios))):
            scenario = scenarios[i]
            tc = {
                "doc_id": f"TC_GEN_{i+1:03d}",
                "module": module,
                "title": scenario["title"],
                "priority": scenario["priority"],
                "precondition": scenario["precondition"],
                "steps": scenario["steps"],
                "expected": scenario["expected"],
                "tags": list(tags_set)[:5],
                "source": {
                    "document_type": "模板生成",
                    "section": "通用测试模板",
                    "quote": "基于标准测试模板生成"
                },
                "confidence": 0.6,  # 模板生成的默认置信度
                "metadata": {
                    "priority": scenario["priority"],
                    "source": "ai_template_generated",
                    "version": "v1.0.0",
                    "requirement": requirement
                }
            }
            test_cases.append(tc)
        
        return test_cases
    
    def _save_test_cases_to_kb(self, test_cases: List[Dict], 
                                requirement: str, module: str) -> int:
        """
        将生成的测试用例保存到知识库
        
        Args:
            test_cases: 测试用例列表
            requirement: 需求描述
            module: 所属模块
            
        Returns:
            保存的数量
        """
        if not test_cases:
            return 0
        
        print(f"\n💾 正在将 {len(test_cases)} 个测试用例保存到知识库...")
        
        ids = []
        embeddings = []
        documents = []
        metadatas = []
        
        for tc in test_cases:
            # 构建文档ID
            doc_id = tc.get("doc_id", f"TC_AI_GEN_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(test_cases)}")
            
            # 构建文档内容（用于向量化和检索）
            content_parts = []
            if tc.get("title"):
                content_parts.append(f"标题：{tc['title']}")
            if tc.get("precondition"):
                content_parts.append(f"前置条件：{tc['precondition']}")
            if tc.get("steps"):
                steps_text = "\n".join([f"  {i+1}. {step}" for i, step in enumerate(tc['steps'])])
                content_parts.append(f"测试步骤：\n{steps_text}")
            if tc.get("expected"):
                content_parts.append(f"预期结果：{tc['expected']}")
            
            content = "\n\n".join(content_parts)
            
            # 构建元数据
            tags = tc.get("tags", [])
            metadata = {
                "source_type": "ai_generated_test_case",
                "module": module,
                "tags": ",".join(tags) if isinstance(tags, list) else str(tags),
                "priority": tc.get("priority", "P2"),
                "version": tc.get("metadata", {}).get("version", "v1.0.0"),
                "author": "AI Agent",
                "create_date": datetime.now().strftime("%Y-%m-%d"),
                "requirement": requirement,
                "generation_method": tc.get("metadata", {}).get("source", "ai_generated")
            }
            
            ids.append(doc_id)
            documents.append(content)
            metadatas.append(metadata)
        
        # 向量化
        try:
            embeddings = self.embedder.encode(documents, normalize=True)
            
            # 写入向量库
            self.vector_store.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            
            print(f"✅ 已保存 {len(ids)} 个测试用例到知识库")
            return len(ids)
        except Exception as e:
            print(f"⚠️  保存测试用例到知识库失败: {e}")
            return 0
