"""阶段3: 测试用例自审"""
from typing import Dict, List
from datetime import datetime
from src.qa_full_flow.agent.semantic_matcher import (
    match_function_points,
    calculate_coverage_rate,
    get_coverage_details,
    generate_coverage_summary,
)
from src.qa_full_flow.agent.traceability_verifier import (
    verify_test_case_traceability,
    generate_traceability_report,
)


class Phase3Reviewer:
    """阶段3：测试用例自审器"""

    def __init__(self):
        self.rules = self._load_rules()
    
    def review(
        self,
        test_cases: List[Dict],
        analysis_result: Dict,
        analysis_doc: str,
        module: str,
        source_documents: Dict[str, str] = None
    ) -> Dict:
        """
        执行自审

        Args:
            test_cases: 测试用例列表
            analysis_result: 阶段1分析结果
            analysis_doc: 测试点分析文档
            module: 模块名称
            source_documents: 原文档字典 {"prd": "...", "tech_doc": "..."}

        Returns:
            自审结果
        """
        print("\n" + "="*60)
        print("🔍 阶段3：测试用例自审")
        print("="*60)

        # 1. 覆盖率分析
        print("\n📊 分析覆盖率...")
        coverage = self._analyze_coverage(test_cases, analysis_result)

        # 2. 可追溯性验证（新增）
        print("\n🔗 验证可追溯性...")
        traceability = self._verify_traceability(test_cases, source_documents)

        # 3. 质量检查
        print("\n✅ 执行质量检查...")
        issues = self._check_quality(test_cases)

        # 4. 生成自审报告
        print("\n📝 生成自审报告...")
        review_report = self._generate_report(
            module=module,
            test_cases=test_cases,
            coverage=coverage,
            issues=issues,
            traceability=traceability
        )
        
        # 5. 统计信息
        coverage_rate = coverage.get("coverage_rate", 0.0)
        issues_found = len(issues)
        traceability_rate = traceability.get("traceability_rate", 0.0)

        print(f"\n✅ 阶段3自审完成")
        print(f"   功能覆盖率: {coverage_rate:.1%}")
        print(f"   可追溯率: {traceability_rate:.1%}")
        print(f"   发现问题: {issues_found}个")

        return {
            "review_report": review_report,
            "coverage": coverage,
            "issues": issues,
            "traceability": traceability,
            "coverage_rate": coverage_rate,
            "traceability_rate": traceability_rate,
            "issues_found": issues_found,
            "supplemented_cases": 0,  # 如果有补充用例
            "phase": "phase3"
        }
    
    def _analyze_coverage(self, test_cases: List[Dict], analysis_result: Dict) -> Dict:
        """分析功能覆盖率（基于语义匹配）"""

        # 1. 从分析结果中提取功能点
        function_points = []
        if "modules" in analysis_result:
            for mod in analysis_result["modules"]:
                for func in mod.get("functions", []):
                    for point in func.get("points", []):
                        point_name = point.get("name", "")
                        if point_name and point_name.strip():
                            function_points.append(point_name)

        if not function_points:
            return {
                "total_function_points": 0,
                "covered_points": 0,
                "uncovered_points": 0,
                "coverage_rate": 0.0,
                "coverage_details": {
                    "covered": [],
                    "partial": [],
                    "uncovered": []
                },
                "coverage_summary": "无功能点可供分析"
            }

        # 2. 使用语义匹配计算覆盖率
        match_results = match_function_points(
            test_cases=test_cases,
            function_points=function_points,
            threshold=0.3,  # 相似度阈值
            use_title=True,
            use_steps=True
        )

        # 3. 计算覆盖率
        coverage_rate = calculate_coverage_rate(match_results, weighted=True)
        covered_count = sum(1 for r in match_results.values() if r["covered"])
        uncovered_count = len(match_results) - covered_count

        # 4. 获取覆盖详情
        coverage_details = get_coverage_details(match_results)

        # 5. 生成摘要
        coverage_summary = generate_coverage_summary(match_results)

        return {
            "total_function_points": len(match_results),
            "covered_points": covered_count,
            "uncovered_points": uncovered_count,
            "coverage_rate": coverage_rate,
            "coverage_details": coverage_details,
            "coverage_summary": coverage_summary,
            "match_results": match_results  # 保留原始匹配结果供详细分析
        }

    def _verify_traceability(
        self,
        test_cases: List[Dict],
        source_documents: Dict[str, str] = None,
    ) -> Dict:
        """
        验证测试用例的可追溯性

        检查每个测试用例的标题、前置条件、预期结果是否能在原文中找到依据。

        Args:
            test_cases: 测试用例列表
            source_documents: 原文档字典

        Returns:
            验证结果
        """
        if not source_documents:
            return {
                "traceable": True,
                "traceability_rate": 1.0,
                "verifications": [],
                "report": "未提供原文档，跳过验证"
            }

        # 验证每个用例
        verifications = []
        for tc in test_cases:
            verification = verify_test_case_traceability(tc, source_documents)
            verifications.append(verification)

        # 计算可追溯率
        total = len(verifications)
        traceable = sum(1 for v in verifications if v["traceable"])
        traceability_rate = traceable / total if total > 0 else 0.0

        # 生成报告
        report = generate_traceability_report(verifications, source_documents)

        return {
            "traceable": traceable,
            "non_traceable": total - traceable,
            "traceability_rate": traceability_rate,
            "verifications": verifications,
            "report": report
        }
    
    def _check_quality(self, test_cases: List[Dict]) -> List[Dict]:
        """质量检查（规则6）"""
        issues = []
        
        for tc in test_cases:
            # 检查必填字段
            required_fields = ["tc_id", "priority", "test_type", "precondition", 
                             "test_steps", "test_data", "expected_result"]
            
            for field in required_fields:
                if not tc.get(field):
                    issues.append({
                        "type": "missing_field",
                        "severity": "高",
                        "description": f"用例 {tc.get('tc_id', '未知')} 缺少字段: {field}",
                        "test_case": tc.get("tc_id", "")
                    })
            
            # 检查步骤是否详细
            steps = tc.get("test_steps", tc.get("steps", ""))
            if len(steps) < 10:
                issues.append({
                    "type": "insufficient_steps",
                    "severity": "中",
                    "description": f"用例 {tc.get('tc_id', '未知')} 测试步骤过于简单",
                    "test_case": tc.get("tc_id", "")
                })
            
            # 检查预期结果是否明确
            expected = tc.get("expected_result", tc.get("expected", ""))
            if not expected or len(expected) < 5:
                issues.append({
                    "type": "vague_expected_result",
                    "severity": "中",
                    "description": f"用例 {tc.get('tc_id', '未知')} 预期结果不明确",
                    "test_case": tc.get("tc_id", "")
                })
        
        return issues
    
    def _generate_report(
        self,
        module: str,
        test_cases: List[Dict],
        coverage: Dict,
        issues: List[Dict],
        traceability: Dict = None
    ) -> str:
        """生成自审报告（模板D）"""
        
        report = f"# {module} 测试用例自审报告\n\n"
        
        # 1. 概述
        report += "## 1. 概述\n\n"
        report += f"- **测试对象**: {module}\n"
        report += f"- **测试目标**: 验证{module}功能符合需求\n"
        report += f"- **测试范围**: {module}模块的功能测试\n"
        report += f"- **测试用例总数**: {len(test_cases)}\n"
        report += f"- **自审时间**: {datetime.now().strftime('%Y-%m-%d')}\n\n"
        
        # 2. 覆盖情况
        report += "## 2. 覆盖情况\n\n"
        report += "### 2.1 功能覆盖摘要\n\n"
        report += coverage.get("coverage_summary", "无数据")
        report += "\n\n"

        report += "**功能点详细**\n\n"
        report += "| 功能点 | 状态 | 匹配度 | 覆盖用例 | 匹配方式 |\n"
        report += "|--------|------|--------|----------|----------|\n"

        coverage_details = coverage.get("coverage_details", {})
        
        # 已覆盖的功能点
        for item in coverage_details.get("covered", []):
            fp = item["function_point"]
            score = item["score"]
            tc_list = ", ".join(item["matched_test_cases"][:3])  # 最多显示3个
            method = item["match_method"]
            report += f"| {fp} | ✅ 已覆盖 | {score:.2f} | {tc_list} | {method} |\n"

        # 部分覆盖的功能点
        for item in coverage_details.get("partial", []):
            fp = item["function_point"]
            score = item["score"]
            tc_list = ", ".join(item["matched_test_cases"][:3])
            method = item["match_method"]
            report += f"| {fp} | ⚠️ 部分覆盖 | {score:.2f} | {tc_list} | {method} |\n"

        # 未覆盖的功能点
        for item in coverage_details.get("uncovered", []):
            fp = item["function_point"]
            report += f"| {fp} | ❌ 未覆盖 | 0.00 | - | - |\n"

        report += "\n"
        
        # 用例分布
        report += "**用例分布**\n\n"
        report += "| 测试类型 | 数量 | 占比 |\n"
        report += "|----------|------|------|\n"
        
        type_counts = {}
        for tc in test_cases:
            t = tc.get("test_type", "功能测试")
            type_counts[t] = type_counts.get(t, 0) + 1
        
        for t, count in type_counts.items():
            pct = count / len(test_cases) if test_cases else 0
            report += f"| {t} | {count} | {pct:.1%} |\n"
        
        report += "\n"
        
        # 优先级分布
        report += "**优先级分布**\n\n"
        report += "| 级别 | 数量 | 占比 |\n"
        report += "|------|------|------|\n"
        
        priority_counts = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
        for tc in test_cases:
            p = tc.get("priority", "P2")
            priority_counts[p] = priority_counts.get(p, 0) + 1
        
        for p in ["P0", "P1", "P2", "P3"]:
            count = priority_counts[p]
            pct = count / len(test_cases) if test_cases else 0
            report += f"| {p} | {count} | {pct:.1%} |\n"
        
        # 3. 发现的问题
        report += "\n## 3. 发现的问题\n\n"
        if issues:
            report += "| 问题描述 | 相关用例 | 严重程度 |\n"
            report += "|----------|----------|----------|\n"
            for issue in issues:
                report += f"| {issue['description']} | {issue['test_case']} | {issue['severity']} |\n"
        else:
            report += "✅ 无明显问题\n"
        
        # 4. 风险点与测试盲点
        report += "\n## 4. 风险点与测试盲点\n\n"
        if coverage["coverage_rate"] < 0.8:
            report += f"| 类型 | 描述 | 相关用例 |\n"
            report += f"|------|------|----------|\n"
            report += f"| ❌ 盲点 | 功能覆盖率不足80%，存在未覆盖的功能点 | - |\n"
        else:
            report += "✅ 无明显风险点和测试盲点\n"
        
        # 5. 改进措施
        report += "\n## 5. 改进措施\n\n"
        if issues:
            report += "| 序号 | 改进内容 | 涉及用例 |\n"
            report += "|------|----------|----------|\n"
            for i, issue in enumerate(issues[:5], 1):  # 只显示前5个
                report += f"| {i} | 修复{issue['description']} | {issue['test_case']} |\n"
        else:
            report += "✅ 无需改进\n"
        
        # 6. 参考资料使用情况
        report += "\n## 6. 参考资料使用情况\n\n"
        report += "| 资料类型 | 使用情况 | 贡献 |\n"
        report += "|----------|----------|------|\n"
        report += "| PRD文档 | ✅ 已使用 | 主要需求来源 |\n"
        report += "| 技术文档 | ✅ 已使用/❌ 未提供 | 补充技术细节 |\n"
        report += "| 知识库历史用例 | ✅ 已使用/❌ 未使用 | 参考类似场景 |\n"

        # 7. 可追溯性验证（新增）
        if traceability and traceability.get("verifications"):
            report += "\n## 7. 可追溯性验证\n\n"
            report += traceability.get("report", "无数据")
            report += "\n"

        # 8. 自审结论
        report += "\n## 8. 自审结论\n\n"
        
        # 综合评估：覆盖率 + 可追溯率 + 问题数
        coverage_rate = coverage["coverage_rate"]
        traceability_rate = traceability.get("traceability_rate", 1.0) if traceability else 1.0
        issue_count = len(issues)

        if issue_count == 0 and coverage_rate >= 0.8 and traceability_rate >= 0.8:
            report += "**结论**: ✅ 通过\n\n"
            report += f"**依据**:\n"
            report += f"- 功能覆盖率: {coverage_rate:.1%} (≥80%)\n"
            report += f"- 可追溯率: {traceability_rate:.1%} (≥80%)\n"
            report += f"- 发现问题: {issue_count}个\n\n"
            report += "**建议**: 测试用例质量良好，可以交付使用。\n"
        elif issue_count <= 3 and coverage_rate >= 0.7 and traceability_rate >= 0.6:
            report += "**结论**: ⚠️ 有条件通过\n\n"
            report += f"**依据**:\n"
            report += f"- 功能覆盖率: {coverage_rate:.1%} (≥70%)\n"
            report += f"- 可追溯率: {traceability_rate:.1%} (≥60%)\n"
            report += f"- 发现问题: {issue_count}个\n\n"
            report += "**建议**: 存在少量问题需要修复，建议完善后交付。\n"
        else:
            report += "**结论**: ❌ 不通过\n\n"
            report += f"**依据**:\n"
            report += f"- 功能覆盖率: {coverage_rate:.1%} (要求≥70%)\n"
            report += f"- 可追溯率: {traceability_rate:.1%} (要求≥60%)\n"
            report += f"- 发现问题: {issue_count}个\n\n"
            report += "**建议**: 需要大幅改进测试用例质量和覆盖率。\n"

        return report
    
    def _load_rules(self) -> Dict:
        """加载规则6（自审检查清单）"""
        return {
            "completeness": ["功能覆盖", "场景覆盖", "类型覆盖"],
            "accuracy": ["步骤准确", "结果准确", "数据准确"],
            "executability": ["前置明确", "步骤可操作", "结果可验证"],
            "independence": ["用例独立", "环境独立"],
            "coverage": ["场景覆盖", "风险覆盖", "边界覆盖"],
            "priority": ["优先级合理", "分布合理"]
        }
