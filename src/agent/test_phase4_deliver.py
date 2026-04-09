"""阶段4: 测试用例交付"""
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger(__name__)


class Phase4Deliverer:
    """阶段4：测试用例交付器"""
    
    def __init__(self):
        pass
    
    def deliver(
        self,
        module: str,
        analysis_doc: str,
        test_cases: List[Dict],
        review_report: str,
        statistics: Dict,
        output_dir: str = None
    ) -> Dict:
        """
        执行交付（写入实际文件）

        Args:
            module: 模块名称
            analysis_doc: 测试点分析文档
            test_cases: 测试用例列表
            review_report: 自审报告
            statistics: 统计信息
            output_dir: 输出目录（默认 data/deliverables/）

        Returns:
            交付结果
        """
        print("\n" + "="*60)
        print("📦 阶段4：测试用例交付")
        print("="*60)

        # 1. 创建输出目录
        if output_dir is None:
            from src.config import settings
            output_dir = str(settings.DATA_DIR / "deliverables")
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # 2. 写入实际文件
        print("\n📁 正在写入交付物...")
        deliverables = self._write_deliverables(
            module=module,
            analysis_doc=analysis_doc,
            test_cases=test_cases,
            review_report=review_report,
            output_path=output_path
        )

        # 3. 生成交付清单
        print("\n📝 生成交付清单...")
        delivery_list = self._generate_delivery_list(
            module=module,
            test_cases=test_cases,
            statistics=statistics,
            output_path=output_path
        )

        # 4. 统计汇总
        summary = self._calculate_summary(
            module=module,
            test_cases=test_cases,
            statistics=statistics
        )

        print(f"\n✅ 阶段4交付完成")
        print(f"   交付物: {len(deliverables)} 个文件已写入 {output_path}")
        print(f"   用例总数: {summary['total_cases']}")

        return {
            "deliverables": deliverables,
            "delivery_list": delivery_list,
            "summary": summary,
            "output_dir": str(output_path),
            "phase": "phase4"
        }

    def _write_deliverables(
        self,
        module: str,
        analysis_doc: str,
        test_cases: List[Dict],
        review_report: str,
        output_path: Path
    ) -> Dict:
        """写入实际交付物文件"""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        deliverables = {}

        # 1. 测试点分析文档 (Markdown)
        analysis_file = output_path / f"{module}_测试点分析.md"
        analysis_file.write_text(analysis_doc, encoding="utf-8")
        deliverables["analysis_doc"] = {
            "filename": str(analysis_file),
            "type": "markdown",
            "description": "需求分析产物",
            "size_bytes": analysis_file.stat().st_size
        }
        print(f"   ✅ 已写入: {analysis_file}")

        # 2. 测试用例 (JSON)
        test_cases_file = output_path / f"{module}_测试用例.json"
        test_cases_file.write_text(
            json.dumps(test_cases, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        deliverables["test_cases_json"] = {
            "filename": str(test_cases_file),
            "type": "json",
            "description": "测试用例文件",
            "size_bytes": test_cases_file.stat().st_size,
            "test_cases_count": len(test_cases)
        }
        print(f"   ✅ 已写入: {test_cases_file}")

        # 3. 自审报告 (Markdown)
        review_file = output_path / f"{module}_测试用例自审报告.md"
        review_file.write_text(review_report, encoding="utf-8")
        deliverables["review_report"] = {
            "filename": str(review_file),
            "type": "markdown",
            "description": "自审结果",
            "size_bytes": review_file.stat().st_size
        }
        print(f"   ✅ 已写入: {review_file}")

        return deliverables
    
    def _generate_delivery_list(
        self,
        module: str,
        test_cases: List[Dict],
        statistics: Dict
    ) -> str:
        """生成交付清单（模板E）"""
        
        delivery_list = f"# {module} 测试用例交付清单\n\n"
        
        # 基本信息
        delivery_list += "## 基本信息\n\n"
        delivery_list += f"- **项目名称**: {module}\n"
        delivery_list += f"- **模块名称**: {module}\n"
        delivery_list += f"- **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        # 交付物清单
        delivery_list += "## 交付物清单\n\n"
        delivery_list += "| 文件类型 | 文件名 | 说明 |\n"
        delivery_list += "|----------|--------|------|\n"
        delivery_list += f"| 测试点分析 | `{module}_测试点分析.md` | 需求分析产物 |\n"
        delivery_list += f"| 测试用例JSON | `{module}_测试用例.json` | 测试用例文件 |\n"
        delivery_list += f"| 自审报告 | `{module}_测试用例自审报告.md` | 自审结果 |\n\n"
        
        # 交付物下载
        delivery_list += "## 交付物下载\n\n"
        delivery_list += "| 文件类型 | 说明 |\n"
        delivery_list += "|----------|------|\n"
        delivery_list += "| 测试用例JSON | 可通过API下载或从知识库获取 |\n"
        delivery_list += "| 测试点分析文档 | 可通过API获取 |\n"
        delivery_list += "| 自审报告 | 可通过API获取 |\n\n"
        
        # 统计汇总
        delivery_list += "## 统计汇总\n\n"
        delivery_list += "| 指标 | 数值 |\n"
        delivery_list += "|------|------|\n"
        delivery_list += f"| 模块数 | 1 |\n"
        delivery_list += f"| 用例总数 | {len(test_cases)} |\n"
        
        priority_dist = statistics.get("priority_distribution", {})
        delivery_list += f"| P0用例 | {priority_dist.get('P0', 0)} |\n"
        delivery_list += f"| P1用例 | {priority_dist.get('P1', 0)} |\n"
        delivery_list += f"| P2用例 | {priority_dist.get('P2', 0)} |\n"
        
        type_dist = statistics.get("type_distribution", {})
        for t, count in type_dist.items():
            delivery_list += f"| {t} | {count} |\n"
        
        return delivery_list
    
    def _calculate_summary(
        self,
        module: str,
        test_cases: List[Dict],
        statistics: Dict
    ) -> Dict:
        """统计汇总"""
        
        priority_dist = statistics.get("priority_distribution", {})
        type_dist = statistics.get("type_distribution", {})
        
        return {
            "module": module,
            "total_cases": len(test_cases),
            "priority_distribution": priority_dist,
            "type_distribution": type_dist,
            "deliverables_count": 3  # 分析文档、用例文件、自审报告
        }
