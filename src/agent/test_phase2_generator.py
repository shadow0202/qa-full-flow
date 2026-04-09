"""阶段2: 测试用例设计生成"""
import logging
from datetime import datetime
from typing import Dict, List
from src.agent.llm_service import LLMService
from src.agent.json_parser import extract_json_array
from src.agent.prompts.test_design import (
    TEST_CASE_GENERATION_SYSTEM_PROMPT_V2,
    TEST_CASE_GENERATION_USER_PROMPT_V2
)

logger = logging.getLogger(__name__)


class Phase2Generator:
    """阶段2：测试用例设计生成器"""
    
    def __init__(self, llm_service: LLMService):
        self.llm = llm_service
    
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
        """调用LLM生成测试用例"""
        
        user_prompt = TEST_CASE_GENERATION_USER_PROMPT_V2.format(
            requirement=f"模块：{module}\n\n详见测试点分析文档",
            module=module,
            prd_content=prd_content or analysis_doc[:1000],
            tech_doc_content=tech_doc_content or "无技术文档",
            other_doc_content=other_doc_content or "无补充文档",
            references="请参考测试点分析文档中的功能点",
            n_examples=n_examples
        )
        
        response = self.llm.generate(
            system_prompt=TEST_CASE_GENERATION_SYSTEM_PROMPT_V2,
            user_prompt=user_prompt
        )

        # 使用容错解析
        test_cases = extract_json_array(response)
        if test_cases:
            # 补充必要字段
            for i, tc in enumerate(test_cases, 1):
                tc["tc_id"] = f"TC-{i:03d}"
                tc["module"] = module
                tc["source"] = "ai_phase2_generated"
            return test_cases
        else:
            logger.warning("Phase2 JSON 解析失败，使用降级方案")
            return self._generate_simple_cases(analysis_doc, module, n_examples)
    
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
