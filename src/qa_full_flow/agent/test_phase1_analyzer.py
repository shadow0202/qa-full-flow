"""阶段1: 需求分析与测试点提取"""
import json
from typing import Dict, List, Optional
from src.qa_full_flow.agent.llm_service import LLMService
from src.qa_full_flow.retrieval.retriever import Retriever
from src.qa_full_flow.agent.prompt_manager import get_prompt_manager
from src.qa_full_flow.agent.document_structurer import preprocess_documents


class Phase1Analyzer:
    """阶段1：需求分析与测试点提取器"""

    def __init__(self, llm_service: LLMService, retriever: Retriever = None):
        self.llm = llm_service
        self.retriever = retriever
        self.prompt_manager = get_prompt_manager()
    
    def analyze(
        self,
        prd_content: str,
        module: str,
        tech_doc_contents: List[str] = None,
        other_doc_contents: List[str] = None,
        use_knowledge_base: bool = True,
        prd_url: str = "",
        tech_doc_urls: List[str] = None,
        other_doc_urls: List[str] = None
    ) -> Dict:
        """执行阶段1分析"""
        print("\n" + "="*60)
        print("📋 阶段1：需求分析与测试点提取")
        print("="*60)

        # 0. 文档结构化预处理（新增：控制 token 预算）
        print("\n📐 文档结构化预处理...")
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

        print(f"✅ PRD 结构化完成: {prd_structured['budget_used']} tokens 使用")
        if preprocessed["any_truncated"]:
            print(f"⚠️  部分内容已截断以符合 token 预算")

        # 1. 可选：检索知识库获取历史相似用例
        knowledge_refs = []
        if use_knowledge_base and self.retriever:
            print("\n🔍 检索知识库...")
            knowledge_refs = self.retriever.search(
                query=prd_content[:300],
                n_results=3
            )
            print(f"✅ 找到 {len(knowledge_refs)} 条参考知识")

        # 2. 构建分析Prompt
        print("\n🤖 调用LLM进行需求分析...")
        analysis_result = self._call_llm(
            prd_structured=prd_structured,
            tech_doc_contents=tech_processed,
            other_doc_contents=other_processed,
            knowledge_refs=knowledge_refs,
            module=module,
            constraints=constraints,
            prd_url=prd_url,
            tech_doc_urls=tech_doc_urls or [],
            other_doc_urls=other_doc_urls or []
        )
        
        # 3. 解析分析结果
        print("\n📝 解析分析结果...")
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
        
        print(f"\n✅ 阶段1分析完成")
        print(f"   功能点数量: {function_points_count}")
        print(f"   待确认项: {pending_confirmations}")
        
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
        other_doc_urls: List[str]
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
        ) + constraint_text

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
