"""
Participant エンティティモデル

イベントに招待された参加者の情報、可用性、設定を表現します。
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import uuid4

from pydantic import BaseModel, Field, validator


class ParticipationStatus(str, Enum):
    """参加ステータス列挙"""
    PENDING = "pending"            # 未回答
    CONFIRMED = "confirmed"        # 参加確定
    DECLINED = "declined"          # 不参加
    NO_RESPONSE = "no_response"    # 回答なし（タイムアウト）


class TimeSlot(BaseModel):
    """時間スロット"""
    start_time: datetime = Field(..., description="開始時刻")
    end_time: datetime = Field(..., description="終了時刻")
    preference_level: int = Field(default=1, description="希望度（1-3、3が最も希望）")
    note: Optional[str] = Field(None, description="備考・条件")

    @validator('end_time')
    def validate_end_time(cls, v, values):
        """終了時刻の検証"""
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('終了時刻は開始時刻より後である必要があります')
        return v

    @validator('preference_level')
    def validate_preference_level(cls, v):
        """希望度の検証"""
        if v not in [1, 2, 3]:
            raise ValueError('希望度は1、2、3のいずれかである必要があります')
        return v

    def duration_minutes(self) -> int:
        """時間スロットの長さ（分）"""
        return int((self.end_time - self.start_time).total_seconds() / 60)

    def overlaps_with(self, other: "TimeSlot") -> bool:
        """他の時間スロットと重複するかチェック"""
        return not (self.end_time <= other.start_time or other.end_time <= self.start_time)

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "preference_level": self.preference_level,
            "note": self.note
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimeSlot":
        """辞書から TimeSlot インスタンスを作成"""
        data["start_time"] = datetime.fromisoformat(data["start_time"])
        data["end_time"] = datetime.fromisoformat(data["end_time"])
        return cls(**data)


class Participant(BaseModel):
    """参加者エンティティ"""

    # 基本識別情報
    participant_id: str = Field(default_factory=lambda: str(uuid4()))
    event_id: str = Field(..., description="関連するイベントID")
    slack_user_id: str = Field(..., description="Slack user ID")

    # 参加状態
    participation_status: ParticipationStatus = Field(
        default=ParticipationStatus.PENDING,
        description="参加ステータス"
    )

    # 可用性情報
    available_time_slots: List[TimeSlot] = Field(
        default_factory=list,
        description="利用可能な時間スロット"
    )

    # 個人設定・制約
    dietary_restrictions: Optional[str] = Field(None, description="食事制限・アレルギー")
    location_preferences: Optional[str] = Field(None, description="場所の希望")
    budget_preference: Optional[int] = Field(None, description="予算希望（円/人）")
    accessibility_needs: Optional[str] = Field(None, description="アクセシビリティ要求")

    # 外部サービス連携
    google_calendar_email: Optional[str] = Field(None, description="Googleカレンダー連携用メール")
    oauth_token_encrypted: Optional[str] = Field(None, description="暗号化されたOAuthトークン")

    # Slack通信情報
    dm_thread_ts: Optional[str] = Field(None, description="DM会話のスレッドタイムスタンプ")
    last_dm_sent_at: Optional[datetime] = Field(None, description="最後のDM送信時刻")
    reminder_count: int = Field(default=0, description="リマインダー送信回数")

    # 確認・応答情報
    confirmed_at: Optional[datetime] = Field(None, description="参加確定時刻")
    declined_at: Optional[datetime] = Field(None, description="不参加決定時刻")
    response_message: Optional[str] = Field(None, description="参加者からの返答メッセージ")
    last_contacted_at: Optional[datetime] = Field(None, description="最後の連絡時刻")

    # メタデータ
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # 表示用情報（キャッシュ）
    display_name: Optional[str] = Field(None, description="表示名")
    profile_image_url: Optional[str] = Field(None, description="プロフィール画像URL")

    class Config:
        """Pydantic設定"""
        use_enum_values = True
        validate_assignment = True
        arbitrary_types_allowed = True

    @validator('slack_user_id')
    def validate_slack_user_id(cls, v):
        """Slack user IDの形式検証"""
        if not v.startswith('U') or len(v) != 11:
            raise ValueError('Slack user IDは有効な形式である必要があります')
        return v

    @validator('google_calendar_email')
    def validate_email(cls, v):
        """メールアドレスの形式検証"""
        if v is not None:
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, v):
                raise ValueError('有効なメールアドレス形式である必要があります')
        return v

    @validator('budget_preference')
    def validate_budget(cls, v):
        """予算の検証"""
        if v is not None and (v < 0 or v > 50000):
            raise ValueError('予算は0円以上50,000円以下である必要があります')
        return v

    @validator('reminder_count')
    def validate_reminder_count(cls, v):
        """リマインダー回数の検証"""
        if v < 0 or v > 10:
            raise ValueError('リマインダー回数は0-10回の範囲である必要があります')
        return v

    def update_timestamp(self) -> None:
        """更新タイムスタンプを現在時刻に設定"""
        self.updated_at = datetime.utcnow()

    def confirm_participation(self, message: Optional[str] = None) -> None:
        """参加を確定"""
        self.participation_status = ParticipationStatus.CONFIRMED
        self.confirmed_at = datetime.utcnow()
        if message:
            self.response_message = message
        self.update_timestamp()

    def decline_participation(self, message: Optional[str] = None) -> None:
        """参加を辞退"""
        self.participation_status = ParticipationStatus.DECLINED
        self.declined_at = datetime.utcnow()
        if message:
            self.response_message = message
        self.update_timestamp()

    def mark_no_response(self) -> None:
        """無回答としてマーク"""
        self.participation_status = ParticipationStatus.NO_RESPONSE
        self.update_timestamp()

    def add_time_slot(self, time_slot: TimeSlot) -> None:
        """利用可能時間スロットを追加"""
        # 重複チェック
        for existing_slot in self.available_time_slots:
            if time_slot.overlaps_with(existing_slot):
                raise ValueError('追加しようとする時間スロットが既存のスロットと重複しています')

        self.available_time_slots.append(time_slot)
        self.update_timestamp()

    def remove_time_slot(self, index: int) -> None:
        """時間スロットを削除"""
        if 0 <= index < len(self.available_time_slots):
            self.available_time_slots.pop(index)
            self.update_timestamp()

    def clear_time_slots(self) -> None:
        """全時間スロットをクリア"""
        self.available_time_slots.clear()
        self.update_timestamp()

    def get_total_available_hours(self) -> float:
        """利用可能な総時間数を計算"""
        total_minutes = sum(slot.duration_minutes() for slot in self.available_time_slots)
        return total_minutes / 60.0

    def has_time_slot_at(self, target_time: datetime, duration_minutes: int = 60) -> bool:
        """指定時刻に利用可能な時間スロットがあるかチェック"""
        target_end = target_time + datetime.timedelta(minutes=duration_minutes)

        for slot in self.available_time_slots:
            if slot.start_time <= target_time and target_end <= slot.end_time:
                return True
        return False

    def get_preference_score_for_time(self, target_time: datetime, duration_minutes: int = 60) -> int:
        """指定時刻の希望度スコアを取得（0-3）"""
        target_end = target_time + datetime.timedelta(minutes=duration_minutes)

        max_score = 0
        for slot in self.available_time_slots:
            if slot.start_time <= target_time and target_end <= slot.end_time:
                max_score = max(max_score, slot.preference_level)

        return max_score

    def is_available_for_event(self, event_start: datetime, duration_minutes: int = 60) -> bool:
        """イベント時刻に参加可能かチェック"""
        return (
            self.participation_status == ParticipationStatus.CONFIRMED and
            self.has_time_slot_at(event_start, duration_minutes)
        )

    def needs_reminder(self, max_reminders: int = 3, reminder_interval_hours: int = 24) -> bool:
        """リマインダーが必要かチェック"""
        if self.participation_status != ParticipationStatus.PENDING:
            return False

        if self.reminder_count >= max_reminders:
            return False

        if self.last_contacted_at is None:
            return True

        hours_since_last_contact = (
            datetime.utcnow() - self.last_contacted_at
        ).total_seconds() / 3600

        return hours_since_last_contact >= reminder_interval_hours

    def send_reminder(self) -> None:
        """リマインダー送信を記録"""
        self.reminder_count += 1
        self.last_contacted_at = datetime.utcnow()
        self.update_timestamp()

    def has_dietary_restrictions(self) -> bool:
        """食事制限があるかチェック"""
        return bool(self.dietary_restrictions and self.dietary_restrictions.strip())

    def has_accessibility_needs(self) -> bool:
        """アクセシビリティ要求があるかチェック"""
        return bool(self.accessibility_needs and self.accessibility_needs.strip())

    def is_calendar_integrated(self) -> bool:
        """カレンダー連携が設定されているかチェック"""
        return bool(self.google_calendar_email and self.oauth_token_encrypted)

    def get_status_display(self) -> str:
        """ステータスの日本語表示"""
        status_display = {
            ParticipationStatus.PENDING: "回答待ち",
            ParticipationStatus.CONFIRMED: "参加",
            ParticipationStatus.DECLINED: "不参加",
            ParticipationStatus.NO_RESPONSE: "未回答"
        }
        return status_display.get(self.participation_status, "不明")

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換（Firestore保存用）"""
        return {
            "participant_id": self.participant_id,
            "event_id": self.event_id,
            "slack_user_id": self.slack_user_id,
            "participation_status": self.participation_status.value,
            "available_time_slots": [slot.to_dict() for slot in self.available_time_slots],
            "dietary_restrictions": self.dietary_restrictions,
            "location_preferences": self.location_preferences,
            "budget_preference": self.budget_preference,
            "accessibility_needs": self.accessibility_needs,
            "google_calendar_email": self.google_calendar_email,
            "oauth_token_encrypted": self.oauth_token_encrypted,
            "dm_thread_ts": self.dm_thread_ts,
            "last_dm_sent_at": self.last_dm_sent_at.isoformat() if self.last_dm_sent_at else None,
            "reminder_count": self.reminder_count,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "declined_at": self.declined_at.isoformat() if self.declined_at else None,
            "response_message": self.response_message,
            "last_contacted_at": self.last_contacted_at.isoformat() if self.last_contacted_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "display_name": self.display_name,
            "profile_image_url": self.profile_image_url
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Participant":
        """辞書から Participant インスタンスを作成"""
        # datetimeフィールドの変換
        datetime_fields = [
            "last_dm_sent_at", "confirmed_at", "declined_at",
            "last_contacted_at", "created_at", "updated_at"
        ]

        for field in datetime_fields:
            if data.get(field):
                data[field] = datetime.fromisoformat(data[field])

        # TimeSlotリストの変換
        if data.get("available_time_slots"):
            data["available_time_slots"] = [
                TimeSlot.from_dict(slot_data)
                for slot_data in data["available_time_slots"]
            ]

        return cls(**data)