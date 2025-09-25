"""
ベースエージェントクラスと通信インターフェース

ADKフレームワークを使用したマルチエージェント通信の基盤を提供します。
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Awaitable
from uuid import uuid4

from pydantic import BaseModel, Field, validator

# ログ設定
logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    """エージェントステータス"""
    INITIALIZING = "initializing"    # 初期化中
    IDLE = "idle"                   # 待機中
    ACTIVE = "active"               # 実行中
    WAITING = "waiting"             # 待機（依存関係）
    COMPLETED = "completed"         # 完了
    ERROR = "error"                 # エラー
    TIMEOUT = "timeout"             # タイムアウト
    PAUSED = "paused"              # 一時停止


class MessageType(str, Enum):
    """メッセージタイプ"""
    COMMAND = "command"              # コマンド
    QUERY = "query"                  # クエリ
    RESPONSE = "response"            # レスポンス
    EVENT = "event"                  # イベント通知
    STATUS_UPDATE = "status_update"   # ステータス更新
    ERROR_REPORT = "error_report"     # エラー報告
    HEARTBEAT = "heartbeat"          # ハートビート


class MessagePriority(str, Enum):
    """メッセージ優先度"""
    LOW = "low"          # 低優先度
    NORMAL = "normal"    # 通常
    HIGH = "high"        # 高優先度
    URGENT = "urgent"    # 緊急


class AgentCapability(BaseModel):
    """エージェント能力定義"""
    capability_name: str = Field(..., description="能力名")
    description: str = Field(..., description="能力の説明")
    input_types: List[str] = Field(default_factory=list, description="受け入れ可能な入力タイプ")
    output_types: List[str] = Field(default_factory=list, description="出力タイプ")
    dependencies: List[str] = Field(default_factory=list, description="依存する他の能力")
    is_async: bool = Field(default=True, description="非同期実行可能か")
    estimated_duration_ms: Optional[int] = Field(None, description="推定実行時間（ミリ秒）")


class AgentMessage(BaseModel):
    """エージェント間メッセージ"""
    message_id: str = Field(default_factory=lambda: str(uuid4()))
    sender_id: str = Field(..., description="送信者エージェントID")
    recipient_id: Optional[str] = Field(None, description="受信者エージェントID（Noneはブロードキャスト）")
    message_type: MessageType = Field(..., description="メッセージタイプ")
    priority: MessagePriority = Field(default=MessagePriority.NORMAL, description="優先度")

    # メッセージ内容
    subject: str = Field(..., description="件名")
    payload: Dict[str, Any] = Field(default_factory=dict, description="メッセージペイロード")
    correlation_id: Optional[str] = Field(None, description="相関ID（リクエスト・レスポンス関連付け）")

    # メタデータ
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = Field(None, description="有効期限")
    retry_count: int = Field(default=0, description="リトライ回数")

    # コンテキスト
    event_id: Optional[str] = Field(None, description="関連するイベントID")
    session_id: Optional[str] = Field(None, description="関連するセッションID")
    user_context: Dict[str, Any] = Field(default_factory=dict, description="ユーザーコンテキスト")

    def is_expired(self) -> bool:
        """メッセージが期限切れかチェック"""
        return self.expires_at is not None and datetime.utcnow() > self.expires_at

    def create_response(
        self,
        sender_id: str,
        payload: Dict[str, Any],
        subject: Optional[str] = None
    ) -> "AgentMessage":
        """レスポンスメッセージを作成"""
        return AgentMessage(
            sender_id=sender_id,
            recipient_id=self.sender_id,
            message_type=MessageType.RESPONSE,
            subject=subject or f"Re: {self.subject}",
            payload=payload,
            correlation_id=self.message_id,
            event_id=self.event_id,
            session_id=self.session_id,
            user_context=self.user_context
        )


class AgentMetrics(BaseModel):
    """エージェントメトリクス"""
    agent_id: str = Field(..., description="エージェントID")
    messages_sent: int = Field(default=0, description="送信メッセージ数")
    messages_received: int = Field(default=0, description="受信メッセージ数")
    errors_count: int = Field(default=0, description="エラー数")
    total_processing_time_ms: int = Field(default=0, description="総処理時間（ミリ秒）")
    last_activity: Optional[datetime] = Field(None, description="最後の活動時刻")
    uptime_seconds: int = Field(default=0, description="稼働時間（秒）")

    def record_message_sent(self) -> None:
        """送信メッセージを記録"""
        self.messages_sent += 1
        self.last_activity = datetime.utcnow()

    def record_message_received(self) -> None:
        """受信メッセージを記録"""
        self.messages_received += 1
        self.last_activity = datetime.utcnow()

    def record_error(self) -> None:
        """エラーを記録"""
        self.errors_count += 1
        self.last_activity = datetime.utcnow()

    def record_processing_time(self, duration_ms: int) -> None:
        """処理時間を記録"""
        self.total_processing_time_ms += duration_ms
        self.last_activity = datetime.utcnow()


class BaseAgent(ABC):
    """ベースエージェントクラス"""

    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str,
        capabilities: List[AgentCapability],
        event_id: Optional[str] = None,
        session_id: Optional[str] = None
    ):
        """
        エージェントを初期化

        Args:
            agent_id: エージェント固有ID
            name: エージェント名
            description: エージェントの説明
            capabilities: エージェントの能力リスト
            event_id: 関連するイベントID
            session_id: 関連するセッションID
        """
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.capabilities = capabilities
        self.event_id = event_id
        self.session_id = session_id

        # 状態管理
        self.status = AgentStatus.INITIALIZING
        self.created_at = datetime.utcnow()
        self.last_heartbeat = datetime.utcnow()

        # メトリクス
        self.metrics = AgentMetrics(agent_id=agent_id)

        # メッセージハンドラー
        self.message_handlers: Dict[MessageType, Callable] = {}
        self.error_handlers: List[Callable] = []

        # 内部状態
        self.context: Dict[str, Any] = {}
        self.pending_messages: List[AgentMessage] = []

        # 通信設定
        self.message_bus: Optional[Any] = None  # ADKメッセージバス

        logger.info(f"エージェント初期化: {self.name} (ID: {self.agent_id})")

    async def initialize(self) -> None:
        """エージェントを初期化"""
        try:
            logger.info(f"エージェント初期化開始: {self.name}")

            # 基本メッセージハンドラーを登録
            self.register_handler(MessageType.HEARTBEAT, self._handle_heartbeat)
            self.register_handler(MessageType.STATUS_UPDATE, self._handle_status_update)
            self.register_handler(MessageType.ERROR_REPORT, self._handle_error_report)

            # 派生クラスの初期化処理
            await self._initialize_impl()

            self.status = AgentStatus.IDLE
            logger.info(f"エージェント初期化完了: {self.name}")

        except Exception as e:
            self.status = AgentStatus.ERROR
            logger.error(f"エージェント初期化エラー: {self.name} - {e}")
            raise

    @abstractmethod
    async def _initialize_impl(self) -> None:
        """派生クラス固有の初期化処理（実装必須）"""
        pass

    async def start(self) -> None:
        """エージェントを開始"""
        if self.status != AgentStatus.IDLE:
            raise RuntimeError(f"エージェントは開始できません。現在のステータス: {self.status}")

        try:
            logger.info(f"エージェント開始: {self.name}")
            self.status = AgentStatus.ACTIVE
            await self._start_impl()

        except Exception as e:
            self.status = AgentStatus.ERROR
            logger.error(f"エージェント開始エラー: {self.name} - {e}")
            raise

    @abstractmethod
    async def _start_impl(self) -> None:
        """派生クラス固有の開始処理（実装必須）"""
        pass

    async def stop(self) -> None:
        """エージェントを停止"""
        try:
            logger.info(f"エージェント停止: {self.name}")
            await self._stop_impl()
            self.status = AgentStatus.COMPLETED

        except Exception as e:
            self.status = AgentStatus.ERROR
            logger.error(f"エージェント停止エラー: {self.name} - {e}")
            raise

    @abstractmethod
    async def _stop_impl(self) -> None:
        """派生クラス固有の停止処理（実装必須）"""
        pass

    def register_handler(
        self,
        message_type: MessageType,
        handler: Callable[[AgentMessage], Awaitable[Optional[AgentMessage]]]
    ) -> None:
        """メッセージハンドラーを登録"""
        self.message_handlers[message_type] = handler
        logger.debug(f"メッセージハンドラー登録: {message_type} - {self.name}")

    def register_error_handler(self, handler: Callable[[Exception], Awaitable[None]]) -> None:
        """エラーハンドラーを登録"""
        self.error_handlers.append(handler)

    async def send_message(self, message: AgentMessage) -> None:
        """メッセージを送信"""
        try:
            message.sender_id = self.agent_id
            if not message.event_id and self.event_id:
                message.event_id = self.event_id
            if not message.session_id and self.session_id:
                message.session_id = self.session_id

            # メッセージバス経由で送信
            if self.message_bus:
                await self.message_bus.publish(message)
            else:
                # メッセージバスが設定されていない場合はペンディングに追加
                self.pending_messages.append(message)

            self.metrics.record_message_sent()
            logger.debug(f"メッセージ送信: {self.name} -> {message.recipient_id or 'ALL'}")

        except Exception as e:
            logger.error(f"メッセージ送信エラー: {self.name} - {e}")
            await self._handle_error(e)

    async def handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """受信メッセージを処理"""
        try:
            # 期限切れメッセージをチェック
            if message.is_expired():
                logger.warning(f"期限切れメッセージを無視: {message.message_id}")
                return None

            self.metrics.record_message_received()
            logger.debug(f"メッセージ受信: {self.name} <- {message.sender_id}")

            # 対応するハンドラーを実行
            handler = self.message_handlers.get(message.message_type)
            if handler:
                start_time = datetime.utcnow()
                response = await handler(message)
                processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                self.metrics.record_processing_time(int(processing_time))
                return response
            else:
                logger.warning(f"未対応メッセージタイプ: {message.message_type} - {self.name}")
                return None

        except Exception as e:
            logger.error(f"メッセージ処理エラー: {self.name} - {e}")
            await self._handle_error(e)
            return None

    async def send_heartbeat(self) -> None:
        """ハートビートを送信"""
        heartbeat_message = AgentMessage(
            sender_id=self.agent_id,
            message_type=MessageType.HEARTBEAT,
            subject="ハートビート",
            payload={
                "status": self.status,
                "metrics": self.metrics.dict(),
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        await self.send_message(heartbeat_message)
        self.last_heartbeat = datetime.utcnow()

    async def broadcast_status(self, status: AgentStatus, details: Optional[Dict[str, Any]] = None) -> None:
        """ステータス更新をブロードキャスト"""
        self.status = status
        status_message = AgentMessage(
            sender_id=self.agent_id,
            message_type=MessageType.STATUS_UPDATE,
            subject=f"ステータス更新: {status}",
            payload={
                "status": status,
                "details": details or {},
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        await self.send_message(status_message)

    async def report_error(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> None:
        """エラーを報告"""
        error_message = AgentMessage(
            sender_id=self.agent_id,
            message_type=MessageType.ERROR_REPORT,
            subject=f"エラー報告: {type(error).__name__}",
            payload={
                "error_type": type(error).__name__,
                "error_message": str(error),
                "context": context or {},
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        await self.send_message(error_message)
        self.metrics.record_error()

    def get_capability(self, capability_name: str) -> Optional[AgentCapability]:
        """指定された能力を取得"""
        for capability in self.capabilities:
            if capability.capability_name == capability_name:
                return capability
        return None

    def has_capability(self, capability_name: str) -> bool:
        """指定された能力を持っているかチェック"""
        return self.get_capability(capability_name) is not None

    def get_status_info(self) -> Dict[str, Any]:
        """ステータス情報を取得"""
        uptime = (datetime.utcnow() - self.created_at).total_seconds()
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "status": self.status,
            "uptime_seconds": int(uptime),
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "metrics": self.metrics.dict(),
            "capabilities": [cap.capability_name for cap in self.capabilities],
            "event_id": self.event_id,
            "session_id": self.session_id
        }

    # 内部メッセージハンドラー

    async def _handle_heartbeat(self, message: AgentMessage) -> Optional[AgentMessage]:
        """ハートビートメッセージの処理"""
        # 他のエージェントからのハートビートを記録
        logger.debug(f"ハートビート受信: {message.sender_id}")
        return None

    async def _handle_status_update(self, message: AgentMessage) -> Optional[AgentMessage]:
        """ステータス更新メッセージの処理"""
        sender_status = message.payload.get("status")
        logger.info(f"ステータス更新受信: {message.sender_id} -> {sender_status}")
        return None

    async def _handle_error_report(self, message: AgentMessage) -> Optional[AgentMessage]:
        """エラー報告メッセージの処理"""
        error_type = message.payload.get("error_type")
        error_message = message.payload.get("error_message")
        logger.error(f"エラー報告受信: {message.sender_id} - {error_type}: {error_message}")
        return None

    async def _handle_error(self, error: Exception) -> None:
        """内部エラー処理"""
        try:
            # エラーハンドラーを実行
            for handler in self.error_handlers:
                await handler(error)

            # エラーを報告
            await self.report_error(error)

        except Exception as e:
            logger.critical(f"エラーハンドリング中にエラーが発生: {self.name} - {e}")

    def set_message_bus(self, message_bus: Any) -> None:
        """メッセージバスを設定"""
        self.message_bus = message_bus
        logger.info(f"メッセージバス設定完了: {self.name}")

        # ペンディングメッセージを送信
        if self.pending_messages:
            logger.info(f"ペンディングメッセージを送信: {len(self.pending_messages)}件")
            # 非同期でペンディングメッセージを処理する場合は別途実装が必要