"""测试用例会话管理器 - 状态机模式 + 持久化后端"""
import uuid
import json
import logging
import threading
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
from pathlib import Path
from abc import ABC, abstractmethod

from src.qa_full_flow.core.config import settings

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
                if k != "test_cases"  # 用例数据可能很大
            },
            "test_cases_count": len(self.artifacts.get("test_cases", [])),
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


class SessionBackend(ABC):
    """会话持久化后端抽象基类"""

    @abstractmethod
    def save(self, session: TestSession) -> None:
        """保存会话"""
        pass

    @abstractmethod
    def load(self, session_id: str) -> Optional[TestSession]:
        """加载会话"""
        pass

    @abstractmethod
    def delete(self, session_id: str) -> None:
        """删除会话"""
        pass

    @abstractmethod
    def list_all(self) -> List[Dict]:
        """列出所有会话摘要"""
        pass

    @abstractmethod
    def cleanup_old(self, max_age_hours: int) -> int:
        """清理过期会话"""
        pass


class MemoryBackend(SessionBackend):
    """内存后端（向后兼容）"""

    def __init__(self):
        self._sessions: Dict[str, TestSession] = {}
        self._lock = threading.Lock()

    def save(self, session: TestSession) -> None:
        with self._lock:
            self._sessions[session.session_id] = session

    def load(self, session_id: str) -> Optional[TestSession]:
        with self._lock:
            return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def list_all(self) -> List[Dict]:
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

    def cleanup_old(self, max_age_hours: int) -> int:
        now = datetime.now()
        with self._lock:
            to_remove = []
            for session_id, session in self._sessions.items():
                created = datetime.fromisoformat(session.created_at)
                if (now - created).total_seconds() > max_age_hours * 3600:
                    to_remove.append(session_id)

            for session_id in to_remove:
                del self._sessions[session_id]

        if to_remove:
            logger.info(f"🧹 清理了 {len(to_remove)} 个过期会话")
        return len(to_remove)


class SQLiteBackend(SessionBackend):
    """SQLite持久化后端"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接（线程安全）"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # 并发优化
        conn.execute("PRAGMA busy_timeout=5000")  # 锁等待超时
        return conn

    def _init_db(self) -> None:
        """初始化数据库表"""
        # 确保目录存在
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY,
                        config TEXT NOT NULL,
                        status TEXT NOT NULL,
                        artifacts TEXT,
                        feedback_history TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                conn.commit()
                logger.info(f"✅ SQLite会话后端已初始化: {self.db_path}")
            finally:
                conn.close()

    def save(self, session: TestSession) -> None:
        """保存或更新会话（UPSERT）"""
        with self._lock:
            conn = self._get_connection()
            try:
                # 序列化artifacts（排除test_cases以减小体积）
                artifacts_data = json.dumps({
                    k: v for k, v in session.artifacts.items()
                    if k != "test_cases"
                }, ensure_ascii=False)

                feedback_data = json.dumps(session.feedback_history, ensure_ascii=False)
                config_data = json.dumps(session.config, ensure_ascii=False)

                conn.execute("""
                    INSERT OR REPLACE INTO sessions
                    (session_id, config, status, artifacts, feedback_history, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    session.session_id,
                    config_data,
                    session.status.value,
                    artifacts_data,
                    feedback_data,
                    session.created_at,
                    session.updated_at
                ))
                conn.commit()
            finally:
                conn.close()

    def load(self, session_id: str) -> Optional[TestSession]:
        """加载会话"""
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT * FROM sessions WHERE session_id = ?",
                    (session_id,)
                ).fetchone()

                if not row:
                    return None

                # 反序列化
                session = TestSession(
                    session_id=row["session_id"],
                    config=json.loads(row["config"])
                )
                session.status = SessionStatus(row["status"])
                session.artifacts = json.loads(row["artifacts"] or "{}")
                session.feedback_history = json.loads(row["feedback_history"] or "[]")
                session.created_at = row["created_at"]
                session.updated_at = row["updated_at"]

                return session
            finally:
                conn.close()

    def delete(self, session_id: str) -> None:
        """删除会话"""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    "DELETE FROM sessions WHERE session_id = ?",
                    (session_id,)
                )
                conn.commit()
            finally:
                conn.close()

    def list_all(self) -> List[Dict]:
        """列出所有会话摘要"""
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(
                    "SELECT session_id, config, status, created_at FROM sessions ORDER BY updated_at DESC"
                ).fetchall()

                return [
                    {
                        "session_id": row["session_id"],
                        "status": row["status"],
                        "module": json.loads(row["config"]).get("module", ""),
                        "created_at": row["created_at"]
                    }
                    for row in rows
                ]
            finally:
                conn.close()

    def cleanup_old(self, max_age_hours: int) -> int:
        """清理过期会话"""
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()

        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    "DELETE FROM sessions WHERE created_at < ?",
                    (cutoff,)
                )
                conn.commit()
                deleted = cursor.rowcount

                if deleted > 0:
                    logger.info(f"🧹 清理了 {deleted} 个过期会话")
                return deleted
            finally:
                conn.close()


class SessionManager:
    """会话管理器（单例 + 线程安全 + 可插拔后端）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:  # 双重检查锁定
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # 选择后端
        backend_type = settings.SESSION_BACKEND
        if backend_type == "sqlite":
            db_path = settings.SESSION_DB_PATH
            # 转换为绝对路径
            if not Path(db_path).is_absolute():
                from src.qa_full_flow.core.config import settings as app_settings
                db_path = str(app_settings.root_dir / db_path.lstrip("./"))
            self.backend: SessionBackend = SQLiteBackend(db_path)
            logger.info(f"✅ 使用SQLite会话后端: {db_path}")
        else:
            self.backend = MemoryBackend()
            logger.info("✅ 使用内存会话后端")

        self._initialized = True

    def create_session(self, config: Dict) -> TestSession:
        """创建新会话（线程安全）"""
        session_id = str(uuid.uuid4())[:8]
        session = TestSession(session_id, config)
        self.backend.save(session)
        logger.info(f"✅ 创建会话: {session_id}")
        return session

    def get_session(self, session_id: str) -> Optional[TestSession]:
        """获取会话（线程安全）"""
        return self.backend.load(session_id)

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

    def update_session(self, session: TestSession) -> None:
        """更新会话（状态/产物/反馈）"""
        self.backend.save(session)

    def cleanup_old_sessions(self, max_age_hours: int = 24) -> int:
        """清理过期会话（线程安全）"""
        return self.backend.cleanup_old(max_age_hours)

    def get_all_sessions(self) -> List[Dict]:
        """获取所有会话摘要（线程安全）"""
        return self.backend.list_all()


# 全局会话管理器实例
session_manager = SessionManager()
