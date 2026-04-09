"""测试用例会话管理器 - 状态机模式"""
import uuid
import json
import time
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class SessionStatus(str, Enum):
    """会话状态枚举"""
    CREATED = "created"
    PHASE1_DONE = "phase1_done"
    PHASE1_CONFIRMED = "phase1_confirmed"
    PHASE2_DONE = "phase2_done"
    PHASE2_CONFIRMED = "phase2_confirmed"
    PHASE3_DONE = "phase3_done"
    PHASE3_CONFIRMED = "phase3_confirmed"
    COMPLETED = "completed"
    FAILED = "failed"


class TestSession:
    """测试用例会话"""
    
    def __init__(self, session_id: str, config: Dict):
        self.session_id = session_id
        self.config = config
        self.status = SessionStatus.CREATED
        self.artifacts = {
            "prd_doc": None,
            "tech_docs": [],
            "other_docs": [],
            "analysis_doc": None,
            "test_cases": [],
            "review_report": None,
            "deliverables": {}
        }
        self.feedback_history = []
        self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
    
    def update_status(self, new_status: SessionStatus):
        """更新状态"""
        self.status = new_status
        self.updated_at = datetime.now().isoformat()
    
    def add_artifact(self, name: str, content: Any):
        """添加产物"""
        self.artifacts[name] = content
        self.updated_at = datetime.now().isoformat()
    
    def add_feedback(self, phase: str, feedback: str):
        """添加反馈记录"""
        self.feedback_history.append({
            "phase": phase,
            "feedback": feedback,
            "timestamp": datetime.now().isoformat()
        })
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "status": self.status.value,
            "config": self.config,
            "artifacts": {
                k: v for k, v in self.artifacts.items() 
                if k not in ["test_cases"]  # 用例可能很大，单独处理
            },
            "test_cases_count": len(self.artifacts.get("test_cases", [])),
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


class SessionManager:
    """会话管理器（单例 + 线程安全）"""

    _instance = None
    _lock = threading.Lock()
    _sessions: Dict[str, TestSession] = {}
    _cleanup_thread: Optional[threading.Thread] = None
    _cleanup_interval: int = 3600  # 1 小时
    _max_age_hours: int = 24

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:  # 双重检查锁定
                    cls._instance = super().__new__(cls)
        return cls._instance

    def start_auto_cleanup(self, max_age_hours: int = 24):
        """启动自动清理任务（只调用一次）"""
        self._max_age_hours = max_age_hours
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            return  # 已经在运行

        self._cleanup_thread = threading.Thread(
            target=self._auto_cleanup_loop,
            daemon=True,
            name="SessionCleanup"
        )
        self._cleanup_thread.start()
        logger.info(f"✅ 会话自动清理已启动，间隔: {self._cleanup_interval}s, 最大存活: {max_age_hours}h")

    def _auto_cleanup_loop(self):
        """自动清理循环"""
        while True:
            time.sleep(self._cleanup_interval)
            try:
                self.cleanup_old_sessions()
            except Exception as e:
                logger.error(f"会话清理失败: {e}")

    def create_session(self, config: Dict) -> TestSession:
        """创建新会话（线程安全）"""
        with self._lock:
            session_id = str(uuid.uuid4())[:8]
            session = TestSession(session_id, config)
            self._sessions[session_id] = session
            logger.info(f"✅ 创建会话: {session_id}")
            return session

    def get_session(self, session_id: str) -> Optional[TestSession]:
        """获取会话"""
        return self._sessions.get(session_id)

    def validate_transition(self, session: TestSession, action: str) -> bool:
        """验证状态转换是否合法"""
        valid_transitions = {
            "phase1": [SessionStatus.CREATED],
            "confirm": [
                SessionStatus.PHASE1_DONE,
                SessionStatus.PHASE2_DONE,
                SessionStatus.PHASE3_DONE
            ],
            "phase2": [SessionStatus.PHASE1_CONFIRMED],
            "phase3": [SessionStatus.PHASE2_CONFIRMED],
            "phase4": [SessionStatus.PHASE3_CONFIRMED]
        }

        allowed_statuses = valid_transitions.get(action, [])
        return session.status in allowed_statuses

    def cleanup_old_sessions(self, max_age_hours: int = None):
        """清理过期会话（线程安全）"""
        if max_age_hours is None:
            max_age_hours = self._max_age_hours

        now = datetime.now()
        to_remove = []

        with self._lock:
            for session_id, session in self._sessions.items():
                created = datetime.fromisoformat(session.created_at)
                if (now - created).total_seconds() > max_age_hours * 3600:
                    to_remove.append(session_id)

            for session_id in to_remove:
                del self._sessions[session_id]

        if to_remove:
            logger.info(f"🧹 清理了 {len(to_remove)} 个过期会话")

    def get_all_sessions(self) -> List[Dict]:
        """获取所有会话摘要"""
        with self._lock:
            return [
                {
                    "session_id": sid,
                    "status": s.status.value,
                    "module": s.config.get("module", ""),
                    "created_at": s.created_at
                }
                for sid, s in self._sessions.items()
            ]


# 全局会话管理器实例
session_manager = SessionManager()
