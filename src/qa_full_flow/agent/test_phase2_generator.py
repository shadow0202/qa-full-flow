"""阶段2: 测试用例设计生成"""
import json
from datetime import datetime
from typing import Dict, List
from src.qa_full_flow.agent.llm_service import LLMService
from src.qa_full_flow.agent.json_parser import extract_json_array
from src.qa_full_flow.agent.prompt_manager import get_prompt_manager


class Phase2Generator:
    """阶段2：测试用例设计生成器"""

    def __init__(self, llm_service: LLMService):
        self.llm = llm_service
        self.prompt_manager = get_prompt_manager()
    
    def generate_test_cases(
        self,
        analysis_result: Dict,
        analysis_doc: str,
        module: str,
        n_examples: int = 5,
        prd_content: str = "",
        tech_doc_content: str = "",
        other_doc_content: str = ""
    ) -> Dict:
        """
        生成测试用例
        
        Args:
            analysis_result: 阶段1的分析结果
            analysis_doc: 测试点分析文档
            module: 模块名称
            n_examples: 生成用例数量
            prd_content: PRD内容
            tech_doc_content: 技术文档内容
            other_doc_content: 补充文档内容
            
        Returns:
            生成结果（包含JSON用例和统计）
        """
        print("\n" + "="*60)
        print("🧪 阶段2：测试用例设计")
        print("="*60)
        
        # 1. 调用LLM生成测试用例
        print("\n🤖 调用LLM生成测试用例...")
        test_cases = self._call_llm(
            analysis_doc=analysis_doc,
            module=module,
            n_examples=n_examples,
            prd_content=prd_content,
            tech_doc_content=tech_doc_content,
            other_doc_content=other_doc_content
        )
        
        # 2. 转换为JSON模板格式
        print("\n📝 转换为JSON格式...")
        json_output = self._convert_to_json_template(
            test_cases=test_cases,
            module=module
        )
        
        # 3. 统计信息
        statistics = self._calculate_statistics(test_cases)
        
        print(f"\n✅ 阶段2生成完成")
        print(f"   用例总数: {statistics['total_test_cases']}")
        print(f"   优先级分布: P0={statistics['priority_distribution'].get('P0', 0)}, "
              f"P1={statistics['priority_distribution'].get('P1', 0)}, "
              f"P2={statistics['priority_distribution'].get('P2', 0)}")
        
        return {
            "test_cases": test_cases,
            "json_output": json_output,
            "statistics": statistics,
            "phase": "phase2"
        }
    
    def _call_llm(
        self,
        analysis_doc: str,
        module: str,
        n_examples: int,
        prd_content: str,
        tech_doc_content: str,
        other_doc_content: str
    ) -> List[Dict]:
        """调用LLM生成测试用例（基于 Phase1 结构化结果）"""

        # 从 Phase1 提取结构化功能点（避免重新投喂全文）
        structured_points = self._extract_function_points(analysis_doc)

        # 只传递结构化功能点，而不是原文全文
        # 使用 PromptManager 渲染模板（支持从文件加载）
        system_prompt = self.prompt_manager.render(
            "phase2_system_prompt",
            version="v3"
        )

        user_prompt = self.prompt_manager.render(
            "phase2_user_prompt",
            version="v3",
            module=module,
            function_points=structured_points,
            analysis_doc=analysis_doc[:2000],
            n_examples=n_examples
        )

        response = self.llm.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=True  # 启用 JSON mode，强制输出 JSON
        )

        # 使用容错解析器
        from src.qa_full_flow.agent.json_parser import extract_json_array
        
        test_cases = extract_json_array(
            response,
            required_fields=["title", "priority"],
            fallback=None
        )

        # 如果解析失败，使用降级方案
        if test_cases is None:
            print(f"⚠️  LLM输出解析失败，使用降级方案")
            return self._generate_simple_cases(analysis_doc, module, n_examples)

        # 补充必要字段
        for i, tc in enumerate(test_cases, 1):
            tc["tc_id"] = f"TC-{i:03d}"
            tc["module"] = module
            tc["source"] = "ai_phase2_generated"

        return test_cases

    def _extract_function_points(self, analysis_doc: str) -> str:
        """
        从 Phase1 分析结果中提取结构化功能点

        避免将原文全文投喂给 Phase2，只传递已提取的功能点。
        """
        import json
        
        # 尝试解析分析文档
        try:
            if isinstance(analysis_doc, str):
                # 如果是 JSON 字符串，解析它
                if analysis_doc.strip().startswith('{'):
                    analysis = json.loads(analysis_doc)
                else:
                    # 如果不是 JSON，直接返回原文
                    return analysis_doc[:1500]
            elif isinstance(analysis_doc, dict):
                analysis = analysis_doc
            else:
                return str(analysis_doc)[:1500]

            # 提取结构化功能点
            function_points = []
            
            if "modules" in analysis:
                for mod in analysis["modules"]:
                    mod_name = mod.get("name", "未知模块")
                    function_points.append(f"\n## 模块: {mod_name}")
                    
                    for func in mod.get("functions", []):
                        func_name = func.get("name", "未知功能")
                        func_desc = func.get("description", "")
                        function_points.append(f"\n### 功能: {func_name}")
                        if func_desc:
                            function_points.append(f"描述: {func_desc}")
                        
                        for point in func.get("points", []):
                            point_name = point.get("name", "")
                            details = point.get("details", [])
                            function_points.append(f"- {point_name}")
                            
                            for detail in details[:3]:  # 最多3个详情
                                item = detail.get("item", "")
                                desc = detail.get("desc", "")
                                pending = detail.get("pending", "")
                                
                                if pending:
                                    function_points.append(f"  - {item}: {desc} 【{pending}】")
                                else:
                                    function_points.append(f"  - {item}: {desc}")

            return "\n".join(function_points)
            
        except Exception as e:
            # 解析失败，返回原文摘要
            print(f"⚠️  功能点提取失败，使用原文摘要: {e}")
            return analysis_doc[:1500] if isinstance(analysis_doc, str) else str(analysis_doc)[:1500]

    def _generate_simple_cases(
        self,
        analysis_doc: str,
        module: str,
        n_examples: int
    ) -> List[Dict]:
        """降级方案：简单模板生成"""
        test_cases = []
        scenarios = [
            {
                "title": f"正常流程测试 - {module}",
                "priority": "P0",
                "test_type": "功能测试",
                "precondition": "系统正常运行，用户已登录",
                "test_steps": f"1. 进入{module}模块\n2. 输入有效数据\n3. 提交操作\n4. 验证结果",
                "test_data": "有效的测试数据",
                "expected_result": "操作成功，数据正确保存"
            },
            {
                "title": f"异常流程测试 - {module}",
                "priority": "P1",
                "test_type": "异常测试",
                "precondition": "系统正常运行",
                "test_steps": f"1. 进入{module}模块\n2. 输入无效或异常数据\n3. 提交操作\n4. 验证错误处理",
                "test_data": "无效或异常数据",
                "expected_result": "系统提示错误信息，数据未保存"
            },
            {
                "title": f"边界条件测试 - {module}",
                "priority": "P1",
                "test_type": "边界测试",
                "precondition": "系统正常运行",
                "test_steps": f"1. 进入{module}模块\n2. 输入边界值数据\n3. 提交操作\n4. 验证系统处理",
                "test_data": "边界值数据（最大值、最小值、空值）",
                "expected_result": "系统正确处理边界情况"
            }
        ]
        
        for i in range(min(n_examples, len(scenarios))):
            scenario = scenarios[i]
            scenario["tc_id"] = f"TC-{i+1:03d}"
            scenario["module"] = module
            scenario["source"] = "ai_template_fallback"
            test_cases.append(scenario)
        
        return test_cases
    
    def _convert_to_json_template(self, test_cases: List[Dict], module: str) -> Dict:
        """转换为模板B的JSON格式"""
        
        # 简化的树形结构（实际应该更复杂）
        json_output = {
            "root": {
                "title": module,
                "children": []
            },
            "metadata": {
                "project_name": module,
                "module_name": module,
                "version": "1.0",
                "create_date": datetime.now().strftime("%Y-%m-%d"),
                "total_test_points": len(test_cases),
                "total_test_cases": len(test_cases),
                "priority_distribution": {},
                "type_distribution": {}
            }
        }
        
        # 构建树形结构（简化版）
        for tc in test_cases:
            case_node = {
                "title": tc.get("title", ""),
                "test_info": {
                    "tc_id": tc.get("tc_id", ""),
                    "priority": tc.get("priority", "P2"),
                    "test_type": tc.get("test_type", "功能测试"),
                    "precondition": tc.get("precondition", ""),
                    "test_steps": tc.get("test_steps", tc.get("steps", "")),
                    "test_data": tc.get("test_data", ""),
                    "expected_result": tc.get("expected_result", tc.get("expected", "")),
                    "reference": tc.get("reference", "")
                }
            }
            
            # 添加到children（简化为单层）
            json_output["root"]["children"].append(case_node)
        
        # 计算统计
        stats = self._calculate_statistics(test_cases)
        json_output["metadata"]["priority_distribution"] = stats["priority_distribution"]
        json_output["metadata"]["type_distribution"] = stats["type_distribution"]
        
        return json_output
    
    def _calculate_statistics(self, test_cases: List[Dict]) -> Dict:
        """统计信息"""
        priority_dist = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
        type_dist = {}
        
        for tc in test_cases:
            priority = tc.get("priority", "P2")
            test_type = tc.get("test_type", "功能测试")
            
            priority_dist[priority] = priority_dist.get(priority, 0) + 1
            type_dist[test_type] = type_dist.get(test_type, 0) + 1
        
        return {
            "total_test_cases": len(test_cases),
            "priority_distribution": priority_dist,
            "type_distribution": type_dist
        }
