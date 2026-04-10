"""阶段1: 需求分析与测试点提取"""
import json
import logging
import jieba.analyse
from typing import Dict, List, Optional
from src.qa_full_flow.agent.llm_service import LLMService
from src.qa_full_flow.retrieval.retriever import Retriever
from src.qa_full_flow.agent.prompt_manager import get_prompt_manager
from src.qa_full_flow.agent.document_structurer import preprocess_documents

logger = logging.getLogger(__name__)


class Phase1Analyzer:
    """阶段1：需求分析与测试点提取器"""

    def __init__(self, llm_service: LLMService, retriever: Retriever = None):
        self.llm = llm_service
        self.retriever = retriever
        self.prompt_manager = get_prompt_manager()
    
    def _retrieve_knowledge_refs(
        self,
        prd_content: str,
        module: str,
        n_results: int = 5
    ) -> List[Dict]:
        """
        多轮检索知识库参考知识

        检索策略：
        - 向量路：tag_query + core_content（合并，语义信息最完整）
        - BM25 路：全文 top10 关键词（精准关键词匹配）
        - 元数据路：同 BM25 的 top10 关键词（精准匹配 tags/module）

        Args:
            prd_content: PRD 文档内容
            module: 模块名称
            n_results: 期望返回的结果数

        Returns:
            检索结果列表
        """
        # 1. 先用现有的结构化预处理提取核心内容
        preprocessed = preprocess_documents(
            prd_content=prd_content,
            module_name=module,
        )
        core_content = preprocessed["prd"]["content"]

        # 2. 提取核心内容的关键词（前 3 个）
        core_tags = jieba.analyse.extract_tags(core_content, topK=3)
        tag_query = ' '.join(core_tags) if core_tags else ""

        # 3. 提取全文的 top10 关键词（用于 BM25 和元数据路）
        full_keywords = jieba.analyse.extract_tags(prd_content, topK=10)
        bm25_query = ' '.join(full_keywords) if full_keywords else ""

        # 4. 构建向量路 query：关键词 + 核心内容（语义信息最完整）
        vector_query = f"{tag_query} {core_content}".strip()

        # 5. 打印调试信息
        logger.info(f"   📝 向量路 query: {vector_query[:100]}...")
        logger.info(f"   📝 BM25/元数据路 query: {bm25_query}")

        # 6. 调用检索（每路使用不同的 query）
        results = self.retriever.search(
            query=vector_query,           # 向量路用
            bm25_query=bm25_query,        # BM25 路用
            metadata_query=bm25_query,    # 元数据路用
            n_results=n_results
        )

        logger.info(f"   📊 检索结果: {len(results)} 条")

        return results[:n_results]

    def _deduplicate_refs(self, refs: List[Dict]) -> List[Dict]:
        """
        按 doc_id 去重

        Args:
            refs: 检索结果列表

        Returns:
            去重后的结果列表
        """
        seen = set()
        result = []
        for ref in refs:
            doc_id = ref.get('doc_id', '')
            if doc_id not in seen:
                seen.add(doc_id)
                result.append(ref)
        return result

    def analyze(
        self,
        prd_content: str,
        module: str,
        tech_doc_contents: List[str] = None,
        other_doc_contents: List[str] = None,
        use_knowledge_base: bool = True,
        prd_url: str = "",
        tech_doc_urls: List[str] = None,
        other_doc_urls: List[str] = None,
        feedback_history: List[Dict] = None
    ) -> Dict:
        """执行阶段1分析"""
        logger.info("\n" + "="*60)
        logger.info("📋 阶段1：需求分析与测试点提取")
        logger.info("="*60)

        # 0. 文档结构化预处理（新增：控制 token 预算）
        logger.info("\n📐 文档结构化预处理...")
        preprocessed = preprocess_documents(
            prd_content=prd_content,
            module_name=module,
            tech_docs=tech_doc_contents or [],
            other_docs=other_doc_contents or [],
        )

        # 使用预处理后的内容
        prd_structured = preprocessed["prd"]
        tech_processed = [d["content"] for d in preprocessed["tech_docs"]]
        other_processed = [d["content"] for d in preprocessed["other_docs"]]
        constraints = preprocessed["constraints"]

        logger.info(f"✅ PRD 结构化完成: {prd_structured['budget_used']} tokens 使用")
        if preprocessed["any_truncated"]:
            logger.info(f"⚠️  部分内容已截断以符合 token 预算")

        # 1. 可选：检索知识库获取历史相似用例（多轮检索）
        knowledge_refs = []
        if use_knowledge_base and self.retriever:
            logger.info("\n🔍 多轮检索知识库...")
            knowledge_refs = self._retrieve_knowledge_refs(
                prd_content=prd_content,
                module=module,
                n_results=5
            )
            logger.info(f"✅ 找到 {len(knowledge_refs)} 条参考知识")

        # 2. 构建分析Prompt
        logger.info("\n🤖 调用LLM进行需求分析...")
        analysis_result = self._call_llm(
            prd_structured=prd_structured,
            tech_doc_contents=tech_processed,
            other_doc_contents=other_processed,
            knowledge_refs=knowledge_refs,
            module=module,
            constraints=constraints,
            prd_url=prd_url,
            tech_doc_urls=tech_doc_urls or [],
            other_doc_urls=other_doc_urls or [],
            feedback_history=feedback_history or []
        )
        
        # 3. 解析分析结果
        logger.info("\n📝 解析分析结果...")
        analysis_doc = self._format_analysis_doc(
            analysis_result,
            module=module,
            prd_url=prd_url,
            tech_doc_urls=tech_doc_urls or [],
            other_doc_urls=other_doc_urls or []
        )
        
        # 4. 统计信息
        function_points_count = self._count_function_points(analysis_result)
        pending_confirmations = self._count_pending_confirmations(analysis_result)
        
        logger.info(f"\n✅ 阶段1分析完成")
        logger.info(f"   功能点数量: {function_points_count}")
        logger.info(f"   待确认项: {pending_confirmations}")
        
        return {
            "analysis_doc": analysis_doc,
            "analysis_result": analysis_result,
            "function_points_count": function_points_count,
            "pending_confirmations": pending_confirmations,
            "knowledge_refs_count": len(knowledge_refs),
            "phase": "phase1"
        }
    
    def _call_llm(
        self,
        prd_structured: Dict,
        tech_doc_contents: List[str],
        other_doc_contents: List[str],
        knowledge_refs: List[Dict],
        module: str,
        constraints: Dict,
        prd_url: str,
        tech_doc_urls: List[str],
        other_doc_urls: List[str],
        feedback_history: List[Dict]
    ) -> Dict:
        """调用LLM进行分析"""

        # 使用结构化 PRD 内容
        prd_content = prd_structured.get("content", "")

        tech_doc_text = ""
        if tech_doc_contents:
            tech_doc_text = "\n\n".join([
                f"### 技术文档 {i+1}\n{content}"
                for i, content in enumerate(tech_doc_contents)
            ])

        other_doc_text = ""
        if other_doc_contents:
            other_doc_text = "\n\n".join([
                f"### 补充文档 {i+1}\n{content}"
                for i, content in enumerate(other_doc_contents)
            ])

        knowledge_text = ""
        if knowledge_refs:
            knowledge_text = "\n\n".join([
                f"### 历史参考 {i+1}\n{ref.get('content', '')}"
                for i, ref in enumerate(knowledge_refs)
            ])

        # 添加显式约束（未提及内容）
        constraint_text = constraints.get("warning", "")
        if constraint_text:
            constraint_text = f"\n\n## ⚠️ 重要约束\n{constraint_text}"

        # 添加用户反馈历史（如果存在）
        feedback_text = ""
        if feedback_history:
            feedback_items = []
            for i, fb in enumerate(feedback_history, 1):
                feedback_items.append(
                    f"{i}. **{fb.get('phase', '未知阶段')}**: {fb.get('feedback', '')}"
                )
            feedback_text = (
                f"\n\n## 📝 用户反馈历史（请根据以下反馈调整本次输出）\n"
                + "\n".join(feedback_items)
                + "\n\n**重要**: 请认真分析以上反馈，针对性地改进输出质量。"
            )

        # 使用 PromptManager 渲染模板（支持从文件加载）
        system_prompt = self.prompt_manager.render(
            "phase1_system_prompt",
            version="v1"
        )

        user_prompt = self.prompt_manager.render(
            "phase1_user_prompt",
            version="v1",
            module=module,
            prd_content=prd_content,
            tech_doc_content=tech_doc_text or "无技术文档",
            other_doc_content=other_doc_text or "无补充文档",
            knowledge_refs=knowledge_text or "无知识库参考",
            prd_url=prd_url,
            tech_doc_urls=", ".join(tech_doc_urls) if tech_doc_urls else "无",
            other_doc_urls=", ".join(other_doc_urls) if other_doc_urls else "无"
        ) + constraint_text + feedback_text

        response = self.llm.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=True  # 启用 JSON mode，强制输出 JSON
        )

        # 使用容错解析器
        from src.qa_full_flow.agent.json_parser import extract_json_object
        
        result = extract_json_object(
            response,
            fallback={"raw_analysis": response}
        )
        
        return result
    
    def _format_analysis_doc(
        self,
        analysis_result: Dict,
        module: str,
        prd_url: str,
        tech_doc_urls: List[str],
        other_doc_urls: List[str]
    ) -> str:
        """格式化为测试点分析文档"""
        
        if "modules" in analysis_result:
            return self._format_structured_analysis(
                analysis_result, module, prd_url, tech_doc_urls, other_doc_urls
            )
        
        return analysis_result.get("raw_analysis", "分析失败")
    
    def _format_structured_analysis(
        self,
        result: Dict,
        module: str,
        prd_url: str,
        tech_doc_urls: List[str],
        other_doc_urls: List[str]
    ) -> str:
        """格式化结构化分析结果"""
        
        doc = f"# {module} 测试点分析\n\n"
        doc += "## 项目概述\n\n"
        doc += f"**项目名称**: {module}\n"
        doc += f"**测试范围**: {result.get('scope', '待补充')}\n"
        doc += f"**模块名称**: {module}\n\n"
        
        doc += "## 业务背景\n\n"
        doc += f"{result.get('background', '文档未提供')}\n\n"
        
        doc += "## 核心功能模块及功能点\n\n"
        
        modules = result.get("modules", [])
        for mod in modules:
            doc += f"### 模块: {mod.get('name', '未命名')}\n\n"
            
            functions = mod.get("functions", [])
            for func in functions:
                doc += f"#### {func.get('name', '未命名')}\n\n"
                doc += f"**逻辑描述**: {func.get('description', '无')}\n\n"
                doc += "**功能点**:\n\n"
                
                points = func.get("points", [])
                for i, point in enumerate(points, 1):
                    doc += f"{i}. {point.get('name', '未命名')}\n"
                    details = point.get("details", [])
                    for detail in details:
                        if isinstance(detail, dict):
                            doc += f"   - {detail.get('item', '')}: {detail.get('desc', '')}"
                            if detail.get('pending'):
                                doc += f" 【待确认：{detail['pending']}】"
                            doc += "\n"
                        else:
                            doc += f"   - {detail}\n"
                    doc += "\n"
        
        doc += "## 非功能需求\n\n"
        non_functional = result.get("non_functional", {})
        if non_functional:
            for key, value in non_functional.items():
                doc += f"### {key}\n\n"
                doc += f"{value}\n\n"
        else:
            doc += "文档未明确提及非功能需求\n\n"
        
        doc += "## 风险点识别\n\n"
        risks = result.get("risks", [])
        if risks:
            for risk in risks:
                doc += f"- {risk}\n"
        else:
            doc += "暂未识别到明显风险点\n"
        
        doc += "\n## 参考资料利用情况\n\n"
        doc += f"- PRD文档: {prd_url}\n"
        if tech_doc_urls:
            doc += f"- 技术方案: {', '.join(tech_doc_urls)}\n"
        if other_doc_urls:
            doc += f"- 补充文档: {', '.join(other_doc_urls)}\n"
        
        return doc
    
    def _count_function_points(self, result: Dict) -> int:
        """统计功能点数量"""
        if "modules" not in result:
            return 0
        
        count = 0
        for mod in result.get("modules", []):
            for func in mod.get("functions", []):
                count += len(func.get("points", []))
        return count
    
    def _count_pending_confirmations(self, result: Dict) -> int:
        """统计待确认项数量"""
        if "modules" not in result:
            return 0
        
        count = 0
        for mod in result.get("modules", []):
            for func in mod.get("functions", []):
                for point in func.get("points", []):
                    for detail in point.get("details", []):
                        if isinstance(detail, dict) and detail.get("pending"):
                            count += 1
        return count
