"""
CoordinationSession エンティティモデル

完全なワークフローインスタンスとエージェント調整状態を追跡します。
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import uuid4

from pydantic import BaseModel, Field, validator


class CoordinationPhase(str, Enum):
    """調整フェーズ列挙"""
    INITIALIZATION = "initialization"              # 初期化
    PARTICIPANT_COLLECTION = "participant_collection"  # 参加者収集
    SCHEDULE_COORDINATION = "schedule_coordination"    # スケジュール調整
    VENUE_COORDINATION = "venue_coordination"          # 会場調整
    CALENDAR_INTEGRATION = "calendar_integration"      # カレンダー統合
    FINAL_CONFIRMATION = "final_confirmation"          # 最終確認
    ANNOUNCEMENT = "announcement"                      # 告知
    COMPLETED = "completed"                           # 完了


class AgentStatus(str, Enum):
    """エージェントステータス列挙"""
    IDLE = "idle"              # 待機中
    ACTIVE = "active"          # 実行中
    WAITING = "waiting"        # 待機（依存関係）
    COMPLETED = "completed"    # 完了
    ERROR = "error"           # エラー
    TIMEOUT = "timeout"       # タイムアウト


class ErrorEntry(BaseModel):
    """エラーエントリ"""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    agent_name: str = Field(..., description="エラーが発生したエージェント名")
    error_type: str = Field(..., description="エラータイプ")
    error_message: str = Field(..., description="エラーメッセージ")
    stack_trace: Optional[str] = Field(None, description="スタックトレース")
    context_data: Dict[str, Any] = Field(default_factory=dict, description="エラー発生時のコンテキスト")
    recovery_action: Optional[str] = Field(None, description="実行された復旧アクション")
    resolved: bool = Field(default=False, description="解決済みかどうか")


class AgentInstance(BaseModel):
    """エージェントインスタンス情報"""
    agent_name: str = Field(..., description="エージェント名")
    agent_id: str = Field(default_factory=lambda: str(uuid4()), description="エージェントインスタンスID")
    status: AgentStatus = Field(default=AgentStatus.IDLE, description="エージェントステータス")
    started_at: Optional[datetime] = Field(None, description="開始時刻")
    completed_at: Optional[datetime] = Field(None, description="完了時刻")
    last_heartbeat: Optional[datetime] = Field(None, description="最後のハートビート")
    current_task: Optional[str] = Field(None, description="現在実行中のタスク")
    progress_percentage: int = Field(default=0, description="進捗率（0-100）")
    result_data: Dict[str, Any] = Field(default_factory=dict, description="実行結果データ")
    error_count: int = Field(default=0, description="エラー発生回数")

    @validator('progress_percentage')
    def validate_progress(cls, v):
        """進捗率の検証"""
        if v < 0 or v > 100:
            raise ValueError('進捗率は0-100の範囲である必要があります')
        return v


class WorkflowCheckpoint(BaseModel):
    """ワークフローチェックポイント"""
    checkpoint_id: str = Field(default_factory=lambda: str(uuid4()))
    phase: CoordinationPhase = Field(..., description="フェーズ")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data_snapshot: Dict[str, Any] = Field(default_factory=dict, description="データスナップショット")
    agent_states: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="エージェント状態")
    decision_points: List[str] = Field(default_factory=list, description="意思決定ポイント")


class CoordinationSession(BaseModel):
    """調整セッションエンティティ"""

    # 基本識別情報
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    event_id: str = Field(..., description="関連するイベントID")

    # ワークフロー状態
    current_phase: CoordinationPhase = Field(
        default=CoordinationPhase.INITIALIZATION,
        description="現在のフェーズ"
    )
    previous_phase: Optional[CoordinationPhase] = Field(None, description="前のフェーズ")

    # エージェント管理
    active_agents: List[AgentInstance] = Field(default_factory=list, description="アクティブなエージェント")
    completed_agents: List[str] = Field(default_factory=list, description="完了したエージェント名")

    # 設定・環境
    intermediate_confirmations: Dict[str, bool] = Field(
        default_factory=dict,
        description="中間確認設定"
    )
    automation_level: str = Field(default="semi_auto", description="自動化レベル")
    timeout_settings: Dict[str, int] = Field(default_factory=dict, description="タイムアウト設定（秒）")

    # 会話・コンテキスト管理
    conversation_context: Dict[str, Any] = Field(
        default_factory=dict,
        description="会話コンテキスト"
    )
    thread_ts: str = Field(..., description="主催者とのSlackスレッドタイムスタンプ")
    last_user_interaction: Optional[datetime] = Field(None, description="最後のユーザー操作")

    # データ・状態保存
    workflow_data: Dict[str, Any] = Field(default_factory=dict, description="フェーズ固有データ")
    shared_state: Dict[str, Any] = Field(default_factory=dict, description="エージェント間共有状態")

    # エラー・ログ管理
    error_log: List[ErrorEntry] = Field(default_factory=list, description="エラーログ")
    activity_log: List[str] = Field(default_factory=list, description="活動ログ")

    # パフォーマンス・監視
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    total_processing_time: int = Field(default=0, description="総処理時間（秒）")
    checkpoints: List[WorkflowCheckpoint] = Field(default_factory=list, description="チェックポイント")

    # セッション管理
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = Field(None, description="セッション有効期限")
    is_paused: bool = Field(default=False, description="一時停止中か")
    pause_reason: Optional[str] = Field(None, description="一時停止理由")

    class Config:
        """Pydantic設定"""
        use_enum_values = True
        validate_assignment = True
        arbitrary_types_allowed = True

    @validator('thread_ts')
    def validate_thread_ts(cls, v):
        """Slackスレッドタイムスタンプの形式検証"""
        import re
        if not re.match(r'^\d{10}\.\d{6}$', v):
            raise ValueError('Slackスレッドタイムスタンプは正しい形式である必要があります')
        return v

    @validator('automation_level')
    def validate_automation_level(cls, v):
        """自動化レベルの検証"""
        valid_levels = ["manual", "semi_auto", "full_auto"]
        if v not in valid_levels:
            raise ValueError(f'自動化レベルは{valid_levels}のいずれかである必要があります')
        return v

    def update_timestamp(self) -> None:
        """更新タイムスタンプを現在時刻に設定"""
        self.updated_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()

    def transition_to_phase(self, new_phase: CoordinationPhase) -> bool:
        """フェーズ遷移を実行"""
        valid_transitions = {
            CoordinationPhase.INITIALIZATION: [
                CoordinationPhase.PARTICIPANT_COLLECTION
            ],
            CoordinationPhase.PARTICIPANT_COLLECTION: [
                CoordinationPhase.SCHEDULE_COORDINATION
            ],
            CoordinationPhase.SCHEDULE_COORDINATION: [
                CoordinationPhase.VENUE_COORDINATION,
                CoordinationPhase.CALENDAR_INTEGRATION  # 会場不要の場合
            ],
            CoordinationPhase.VENUE_COORDINATION: [
                CoordinationPhase.CALENDAR_INTEGRATION
            ],
            CoordinationPhase.CALENDAR_INTEGRATION: [
                CoordinationPhase.FINAL_CONFIRMATION
            ],
            CoordinationPhase.FINAL_CONFIRMATION: [
                CoordinationPhase.ANNOUNCEMENT
            ],
            CoordinationPhase.ANNOUNCEMENT: [
                CoordinationPhase.COMPLETED
            ],
            CoordinationPhase.COMPLETED: []
        }

        if new_phase in valid_transitions.get(self.current_phase, []):
            self.previous_phase = self.current_phase
            self.current_phase = new_phase
            self.create_checkpoint(f"フェーズ遷移: {self.previous_phase} → {new_phase}")
            self.update_timestamp()
            return True
        return False

    def add_agent(self, agent_name: str) -> str:
        """エージェントを追加し、エージェントIDを返す"""
        agent = AgentInstance(agent_name=agent_name)
        self.active_agents.append(agent)
        self.log_activity(f"エージェント追加: {agent_name} (ID: {agent.agent_id})")
        self.update_timestamp()
        return agent.agent_id

    def start_agent(self, agent_name: str, task: Optional[str] = None) -> bool:
        """エージェントを開始"""
        for agent in self.active_agents:
            if agent.agent_name == agent_name and agent.status == AgentStatus.IDLE:
                agent.status = AgentStatus.ACTIVE
                agent.started_at = datetime.utcnow()
                agent.last_heartbeat = datetime.utcnow()
                if task:
                    agent.current_task = task
                self.log_activity(f"エージェント開始: {agent_name} - {task or '一般タスク'}")
                self.update_timestamp()
                return True
        return False

    def complete_agent(self, agent_name: str, result_data: Optional[Dict[str, Any]] = None) -> bool:
        """エージェントを完了"""
        for agent in self.active_agents:
            if agent.agent_name == agent_name and agent.status == AgentStatus.ACTIVE:
                agent.status = AgentStatus.COMPLETED
                agent.completed_at = datetime.utcnow()
                agent.progress_percentage = 100
                if result_data:
                    agent.result_data = result_data

                self.completed_agents.append(agent_name)
                self.log_activity(f"エージェント完了: {agent_name}")
                self.update_timestamp()
                return True
        return False

    def fail_agent(self, agent_name: str, error_message: str) -> bool:
        """エージェントをエラー状態にする"""
        for agent in self.active_agents:
            if agent.agent_name == agent_name:
                agent.status = AgentStatus.ERROR
                agent.error_count += 1
                self.log_error(agent_name, "AgentError", error_message)
                self.update_timestamp()
                return True
        return False

    def update_agent_progress(self, agent_name: str, progress: int, task: Optional[str] = None) -> bool:
        """エージェントの進捗を更新"""
        for agent in self.active_agents:
            if agent.agent_name == agent_name and agent.status == AgentStatus.ACTIVE:
                agent.progress_percentage = progress
                agent.last_heartbeat = datetime.utcnow()
                if task:
                    agent.current_task = task
                self.update_timestamp()
                return True
        return False

    def log_error(
        self,
        agent_name: str,
        error_type: str,
        error_message: str,
        context_data: Optional[Dict[str, Any]] = None,
        stack_trace: Optional[str] = None
    ) -> None:
        """エラーをログに記録"""
        error_entry = ErrorEntry(
            agent_name=agent_name,
            error_type=error_type,
            error_message=error_message,
            context_data=context_data or {},
            stack_trace=stack_trace
        )
        self.error_log.append(error_entry)
        self.log_activity(f"エラー発生: {agent_name} - {error_type}: {error_message}")
        self.update_timestamp()

    def log_activity(self, message: str) -> None:
        """活動をログに記録"""
        timestamp = datetime.utcnow().strftime("%H:%M:%S")
        self.activity_log.append(f"[{timestamp}] {message}")
        # ログサイズ制限（最新1000件まで）
        if len(self.activity_log) > 1000:
            self.activity_log = self.activity_log[-1000:]

    def create_checkpoint(self, description: str) -> None:
        """チェックポイントを作成"""
        checkpoint = WorkflowCheckpoint(
            phase=self.current_phase,
            data_snapshot=self.workflow_data.copy(),
            agent_states={
                agent.agent_name: {
                    "status": agent.status,
                    "progress": agent.progress_percentage,
                    "current_task": agent.current_task
                }
                for agent in self.active_agents
            },
            decision_points=[description]
        )
        self.checkpoints.append(checkpoint)
        self.log_activity(f"チェックポイント作成: {description}")

    def pause_session(self, reason: str) -> None:
        """セッションを一時停止"""
        self.is_paused = True
        self.pause_reason = reason
        self.log_activity(f"セッション一時停止: {reason}")
        self.update_timestamp()

    def resume_session(self) -> None:
        """セッションを再開"""
        self.is_paused = False
        self.pause_reason = None
        self.log_activity("セッション再開")
        self.update_timestamp()

    def get_active_agent_count(self) -> int:
        """アクティブなエージェント数を取得"""
        return sum(1 for agent in self.active_agents if agent.status == AgentStatus.ACTIVE)

    def get_error_count(self) -> int:
        """エラー数を取得"""
        return len([error for error in self.error_log if not error.resolved])

    def has_unresolved_errors(self) -> bool:
        """未解決のエラーがあるかチェック"""
        return any(not error.resolved for error in self.error_log)

    def get_phase_duration(self) -> Optional[int]:
        """現在のフェーズの実行時間（秒）を取得"""
        if self.checkpoints:
            for checkpoint in reversed(self.checkpoints):
                if checkpoint.phase != self.current_phase:
                    phase_start = checkpoint.timestamp
                    return int((datetime.utcnow() - phase_start).total_seconds())
        return int((datetime.utcnow() - self.created_at).total_seconds())

    def is_expired(self) -> bool:
        """セッションが期限切れかチェック"""
        return self.expires_at is not None and datetime.utcnow() > self.expires_at

    def needs_user_interaction(self) -> bool:
        """ユーザー操作が必要な状態かチェック"""
        confirmation_phases = {
            CoordinationPhase.SCHEDULE_COORDINATION,
            CoordinationPhase.VENUE_COORDINATION,
            CoordinationPhase.FINAL_CONFIRMATION
        }

        return (
            self.current_phase in confirmation_phases and
            self.intermediate_confirmations.get(self.current_phase.value, True)
        )

    def get_status_summary(self) -> Dict[str, Any]:
        """ステータス概要を取得"""
        return {
            "session_id": self.session_id,
            "current_phase": self.current_phase,
            "active_agents": len(self.active_agents),
            "completed_agents": len(self.completed_agents),
            "error_count": self.get_error_count(),
            "is_paused": self.is_paused,
            "phase_duration_seconds": self.get_phase_duration(),
            "last_activity": self.last_activity.isoformat(),
            "needs_user_interaction": self.needs_user_interaction()
        }

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換（Firestore保存用）"""
        return {
            "session_id": self.session_id,
            "event_id": self.event_id,
            "current_phase": self.current_phase.value,
            "previous_phase": self.previous_phase.value if self.previous_phase else None,
            "active_agents": [agent.dict() for agent in self.active_agents],
            "completed_agents": self.completed_agents,
            "intermediate_confirmations": self.intermediate_confirmations,
            "automation_level": self.automation_level,
            "timeout_settings": self.timeout_settings,
            "conversation_context": self.conversation_context,
            "thread_ts": self.thread_ts,
            "last_user_interaction": self.last_user_interaction.isoformat() if self.last_user_interaction else None,
            "workflow_data": self.workflow_data,
            "shared_state": self.shared_state,
            "error_log": [error.dict() for error in self.error_log],
            "activity_log": self.activity_log,
            "last_activity": self.last_activity.isoformat(),
            "total_processing_time": self.total_processing_time,
            "checkpoints": [checkpoint.dict() for checkpoint in self.checkpoints],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_paused": self.is_paused,
            "pause_reason": self.pause_reason
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CoordinationSession":
        """辞書から CoordinationSession インスタンスを作成"""
        # datetimeフィールドの変換
        datetime_fields = [
            "last_user_interaction", "last_activity",
            "created_at", "updated_at", "expires_at"
        ]
        for field in datetime_fields:
            if data.get(field):
                data[field] = datetime.fromisoformat(data[field])

        # active_agentsリストの変換
        if data.get("active_agents"):
            agents = []
            for agent_data in data["active_agents"]:
                # AgentInstance内のdatetimeフィールドも変換
                for dt_field in ["started_at", "completed_at", "last_heartbeat"]:
                    if agent_data.get(dt_field):
                        agent_data[dt_field] = datetime.fromisoformat(agent_data[dt_field])
                agents.append(AgentInstance(**agent_data))
            data["active_agents"] = agents

        # error_logリストの変換
        if data.get("error_log"):
            errors = []
            for error_data in data["error_log"]:
                if error_data.get("timestamp"):
                    error_data["timestamp"] = datetime.fromisoformat(error_data["timestamp"])
                errors.append(ErrorEntry(**error_data))
            data["error_log"] = errors

        # checkpointsリストの変換
        if data.get("checkpoints"):
            checkpoints = []
            for checkpoint_data in data["checkpoints"]:
                if checkpoint_data.get("timestamp"):
                    checkpoint_data["timestamp"] = datetime.fromisoformat(checkpoint_data["timestamp"])
                checkpoints.append(WorkflowCheckpoint(**checkpoint_data))
            data["checkpoints"] = checkpoints

        return cls(**data)