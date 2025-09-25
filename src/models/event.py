"""
Event エンティティモデル

計画されたイベントとその調整ワークフロー状態を表現します。
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import uuid4

from pydantic import BaseModel, Field, validator


class EventType(str, Enum):
    """イベントタイプ列挙"""
    DINING = "dining"      # 飲み会・ランチ
    STUDY = "study"        # 勉強会
    MEETING = "meeting"    # 会議・MTG


class EventStatus(str, Enum):
    """イベントステータス列挙"""
    CREATED = "created"
    COLLECTING_PARTICIPANTS = "collecting_participants"
    SCHEDULING = "scheduling"
    VENUE_SEARCH = "venue_search"
    CALENDAR_BOOKING = "calendar_booking"
    FINAL_CONFIRMATION = "final_confirmation"
    ANNOUNCED = "announced"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


class CoordinationPreferences(BaseModel):
    """調整設定"""
    enable_intermediate_confirmations: bool = True
    auto_venue_booking: bool = False
    max_participants: Optional[int] = None
    require_all_participants: bool = False
    timezone: str = "Asia/Tokyo"
    language: str = "ja"


class Event(BaseModel):
    """イベントエンティティ"""

    # 基本識別情報
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    channel_id: str = Field(..., description="Slackチャンネル ID")
    organizer_id: str = Field(..., description="主催者のSlack user ID")

    # イベント詳細
    event_type: EventType = Field(..., description="イベントタイプ")
    purpose: str = Field(..., description="イベントの目的・説明")
    title: Optional[str] = Field(None, description="イベントタイトル")

    # ワークフロー状態
    status: EventStatus = Field(default=EventStatus.CREATED, description="調整ステータス")

    # 関連エンティティの参照
    participant_ids: List[str] = Field(default_factory=list, description="参加者IDリスト")
    venue_id: Optional[str] = Field(None, description="選択された会場ID")
    calendar_entry_ids: List[str] = Field(default_factory=list, description="カレンダーエントリIDリスト")
    coordination_session_id: Optional[str] = Field(None, description="調整セッションID")

    # 決定済み情報
    scheduled_datetime: Optional[datetime] = Field(None, description="確定した日時")
    duration_minutes: Optional[int] = Field(None, description="予定時間（分）")

    # 設定
    coordination_preferences: CoordinationPreferences = Field(
        default_factory=CoordinationPreferences,
        description="調整設定"
    )

    # メタデータ
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Slack関連
    thread_ts: Optional[str] = Field(None, description="主催者との会話スレッド")
    original_message_ts: Optional[str] = Field(None, description="元のメッセージタイムスタンプ")

    class Config:
        """Pydantic設定"""
        use_enum_values = True
        validate_assignment = True
        arbitrary_types_allowed = True

    @validator('organizer_id')
    def validate_organizer_id(cls, v):
        """主催者IDの形式検証"""
        if not v.startswith('U') or len(v) != 11:
            raise ValueError('主催者IDは有効なSlack user ID形式である必要があります')
        return v

    @validator('channel_id')
    def validate_channel_id(cls, v):
        """チャンネルIDの形式検証"""
        if not v.startswith('C') or len(v) != 11:
            raise ValueError('チャンネルIDは有効なSlack channel ID形式である必要があります')
        return v

    @validator('scheduled_datetime')
    def validate_scheduled_datetime(cls, v):
        """予定日時の検証"""
        if v is not None and v <= datetime.utcnow():
            raise ValueError('予定日時は未来の日時である必要があります')
        return v

    @validator('duration_minutes')
    def validate_duration(cls, v):
        """時間の検証"""
        if v is not None and (v <= 0 or v > 1440):  # 24時間以内
            raise ValueError('時間は1分以上1440分以下である必要があります')
        return v

    @validator('purpose')
    def validate_purpose(cls, v):
        """目的の検証"""
        if not v or len(v.strip()) < 3:
            raise ValueError('イベントの目的は3文字以上である必要があります')
        return v.strip()

    def update_timestamp(self) -> None:
        """更新タイムスタンプを現在時刻に設定"""
        self.updated_at = datetime.utcnow()

    def add_participant(self, participant_id: str) -> None:
        """参加者を追加"""
        if participant_id not in self.participant_ids:
            self.participant_ids.append(participant_id)
            self.update_timestamp()

    def remove_participant(self, participant_id: str) -> None:
        """参加者を削除"""
        if participant_id in self.participant_ids:
            self.participant_ids.remove(participant_id)
            self.update_timestamp()

    def can_transition_to(self, new_status: EventStatus) -> bool:
        """ステータス遷移が可能かチェック"""
        transitions = {
            EventStatus.CREATED: [
                EventStatus.COLLECTING_PARTICIPANTS,
                EventStatus.CANCELLED
            ],
            EventStatus.COLLECTING_PARTICIPANTS: [
                EventStatus.SCHEDULING,
                EventStatus.CANCELLED
            ],
            EventStatus.SCHEDULING: [
                EventStatus.VENUE_SEARCH,
                EventStatus.CALENDAR_BOOKING,  # 会場不要の場合
                EventStatus.CANCELLED
            ],
            EventStatus.VENUE_SEARCH: [
                EventStatus.CALENDAR_BOOKING,
                EventStatus.CANCELLED,
                EventStatus.ERROR
            ],
            EventStatus.CALENDAR_BOOKING: [
                EventStatus.FINAL_CONFIRMATION,
                EventStatus.CANCELLED,
                EventStatus.ERROR
            ],
            EventStatus.FINAL_CONFIRMATION: [
                EventStatus.ANNOUNCED,
                EventStatus.CANCELLED
            ],
            EventStatus.ANNOUNCED: [
                EventStatus.COMPLETED,
                EventStatus.CANCELLED
            ],
            EventStatus.COMPLETED: [],  # 終了状態
            EventStatus.CANCELLED: [],  # 終了状態
            EventStatus.ERROR: [
                EventStatus.SCHEDULING,  # エラーからのリトライ
                EventStatus.VENUE_SEARCH,
                EventStatus.CALENDAR_BOOKING,
                EventStatus.CANCELLED
            ]
        }

        return new_status in transitions.get(self.status, [])

    def transition_to(self, new_status: EventStatus) -> bool:
        """ステータス遷移を実行"""
        if self.can_transition_to(new_status):
            self.status = new_status
            self.update_timestamp()
            return True
        return False

    def is_active(self) -> bool:
        """アクティブなイベントかどうか"""
        inactive_statuses = {
            EventStatus.COMPLETED,
            EventStatus.CANCELLED
        }
        return self.status not in inactive_statuses

    def requires_venue(self) -> bool:
        """会場が必要なイベントタイプかどうか"""
        venue_required_types = {
            EventType.DINING,
            EventType.STUDY
        }
        return self.event_type in venue_required_types

    def get_participant_count(self) -> int:
        """参加者数を取得"""
        return len(self.participant_ids)

    def is_ready_for_scheduling(self) -> bool:
        """スケジュール調整準備完了かどうか"""
        min_participants = 1 if not self.coordination_preferences.require_all_participants else 2
        return (
            self.status == EventStatus.COLLECTING_PARTICIPANTS and
            self.get_participant_count() >= min_participants
        )

    def is_ready_for_venue_search(self) -> bool:
        """会場検索準備完了かどうか"""
        return (
            self.status == EventStatus.SCHEDULING and
            self.scheduled_datetime is not None and
            self.requires_venue()
        )

    def is_ready_for_calendar_booking(self) -> bool:
        """カレンダー予約準備完了かどうか"""
        venue_ready = not self.requires_venue() or self.venue_id is not None
        return (
            self.status in [EventStatus.SCHEDULING, EventStatus.VENUE_SEARCH] and
            self.scheduled_datetime is not None and
            venue_ready
        )

    def generate_title(self) -> str:
        """イベントタイトルを自動生成"""
        if self.title:
            return self.title

        type_names = {
            EventType.DINING: "食事会",
            EventType.STUDY: "勉強会",
            EventType.MEETING: "ミーティング"
        }

        base_title = type_names.get(self.event_type, "イベント")

        if self.scheduled_datetime:
            date_str = self.scheduled_datetime.strftime("%m月%d日")
            return f"{date_str} {base_title}"

        return base_title

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換（Firestore保存用）"""
        return {
            "event_id": self.event_id,
            "channel_id": self.channel_id,
            "organizer_id": self.organizer_id,
            "event_type": self.event_type.value,
            "purpose": self.purpose,
            "title": self.title,
            "status": self.status.value,
            "participant_ids": self.participant_ids,
            "venue_id": self.venue_id,
            "calendar_entry_ids": self.calendar_entry_ids,
            "coordination_session_id": self.coordination_session_id,
            "scheduled_datetime": self.scheduled_datetime.isoformat() if self.scheduled_datetime else None,
            "duration_minutes": self.duration_minutes,
            "coordination_preferences": self.coordination_preferences.dict(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "thread_ts": self.thread_ts,
            "original_message_ts": self.original_message_ts
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """辞書から Event インスタンスを作成"""
        # datetimeフィールドの変換
        if data.get("scheduled_datetime"):
            data["scheduled_datetime"] = datetime.fromisoformat(data["scheduled_datetime"])
        if data.get("created_at"):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if data.get("updated_at"):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        # coordination_preferencesの変換
        if data.get("coordination_preferences"):
            data["coordination_preferences"] = CoordinationPreferences(**data["coordination_preferences"])

        return cls(**data)