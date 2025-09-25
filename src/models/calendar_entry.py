"""
CalendarEntry エンティティモデル

Google Calendarに作成されたイベントの情報を表現します。
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import uuid4

from pydantic import BaseModel, Field, validator


class CalendarStatus(str, Enum):
    """カレンダー作成ステータス列挙"""
    PENDING = "pending"          # 作成待ち
    SUCCESS = "success"          # 作成成功
    FAILED = "failed"           # 作成失敗
    CANCELLED = "cancelled"      # キャンセル済み
    UPDATED = "updated"         # 更新済み


class AttendeeStatus(str, Enum):
    """参加者の回答ステータス（Google Calendar準拠）"""
    NEEDS_ACTION = "needsAction"    # 回答待ち
    DECLINED = "declined"           # 辞退
    TENTATIVE = "tentative"         # 仮承諾
    ACCEPTED = "accepted"           # 承諾


class CalendarAttendee(BaseModel):
    """カレンダー参加者情報"""
    email: str = Field(..., description="参加者のメールアドレス")
    display_name: Optional[str] = Field(None, description="表示名")
    response_status: AttendeeStatus = Field(default=AttendeeStatus.NEEDS_ACTION, description="回答ステータス")
    optional: bool = Field(default=False, description="任意参加者か")
    organizer: bool = Field(default=False, description="主催者か")
    comment: Optional[str] = Field(None, description="参加者からのコメント")

    @validator('email')
    def validate_email(cls, v):
        """メールアドレスの形式検証"""
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError('有効なメールアドレス形式である必要があります')
        return v


class CalendarReminder(BaseModel):
    """カレンダーリマインダー設定"""
    method: str = Field(..., description="リマインダー方法（email, popup）")
    minutes: int = Field(..., description="イベント前の分数")

    @validator('method')
    def validate_method(cls, v):
        """リマインダー方法の検証"""
        valid_methods = ["email", "popup", "sms"]
        if v not in valid_methods:
            raise ValueError(f'リマインダー方法は{valid_methods}のいずれかである必要があります')
        return v

    @validator('minutes')
    def validate_minutes(cls, v):
        """リマインダー時間の検証"""
        if v < 0 or v > 40320:  # 4週間まで
            raise ValueError('リマインダー時間は0分以上4週間以内である必要があります')
        return v


class CalendarEntry(BaseModel):
    """カレンダーエントリエンティティ"""

    # 基本識別情報
    calendar_entry_id: str = Field(default_factory=lambda: str(uuid4()))
    event_id: str = Field(..., description="関連するイベントID")
    google_event_id: Optional[str] = Field(None, description="Google Calendar上のイベントID")

    # カレンダー情報
    calendar_email: str = Field(..., description="対象カレンダーのメールアドレス")
    calendar_id: str = Field(default="primary", description="カレンダーID")

    # イベント詳細
    event_title: str = Field(..., description="カレンダーイベントのタイトル")
    event_description: Optional[str] = Field(None, description="イベントの詳細説明")
    event_summary: Optional[str] = Field(None, description="イベントの概要")

    # 日時情報
    start_time: datetime = Field(..., description="開始日時")
    end_time: datetime = Field(..., description="終了日時")
    timezone: str = Field(default="Asia/Tokyo", description="タイムゾーン")
    all_day: bool = Field(default=False, description="終日イベントか")

    # 場所情報
    location: Optional[str] = Field(None, description="場所（会場名・住所）")
    conference_data: Optional[Dict[str, Any]] = Field(None, description="オンライン会議情報")

    # 参加者管理
    attendees: List[CalendarAttendee] = Field(default_factory=list, description="参加者リスト")
    send_notifications: bool = Field(default=True, description="参加者に通知を送信するか")

    # Google Workspace連携
    meeting_room_resource: Optional[str] = Field(None, description="会議室リソースID")
    meeting_room_name: Optional[str] = Field(None, description="会議室名")

    # 設定・オプション
    visibility: str = Field(default="default", description="公開設定")
    reminders: List[CalendarReminder] = Field(default_factory=list, description="リマインダー設定")
    recurrence: Optional[List[str]] = Field(None, description="繰り返し設定（RRULE）")

    # ステータス・メタデータ
    creation_status: CalendarStatus = Field(default=CalendarStatus.PENDING, description="作成ステータス")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_sync_at: Optional[datetime] = Field(None, description="最後の同期日時")

    # エラー・ログ情報
    error_message: Optional[str] = Field(None, description="エラーメッセージ")
    creation_attempts: int = Field(default=0, description="作成試行回数")

    # 外部リンク
    google_calendar_url: Optional[str] = Field(None, description="Google CalendarのURL")
    ical_uid: Optional[str] = Field(None, description="iCal UID")

    class Config:
        """Pydantic設定"""
        use_enum_values = True
        validate_assignment = True
        arbitrary_types_allowed = True

    @validator('calendar_email')
    def validate_calendar_email(cls, v):
        """カレンダーメールアドレスの形式検証"""
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError('有効なメールアドレス形式である必要があります')
        return v

    @validator('end_time')
    def validate_end_time(cls, v, values):
        """終了時刻の検証"""
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('終了時刻は開始時刻より後である必要があります')
        return v

    @validator('event_title')
    def validate_event_title(cls, v):
        """イベントタイトルの検証"""
        if not v or len(v.strip()) < 1:
            raise ValueError('イベントタイトルは必須です')
        if len(v) > 1024:
            raise ValueError('イベントタイトルは1024文字以下である必要があります')
        return v.strip()

    @validator('visibility')
    def validate_visibility(cls, v):
        """公開設定の検証"""
        valid_visibility = ["default", "public", "private", "confidential"]
        if v not in valid_visibility:
            raise ValueError(f'公開設定は{valid_visibility}のいずれかである必要があります')
        return v

    @validator('creation_attempts')
    def validate_creation_attempts(cls, v):
        """作成試行回数の検証"""
        if v < 0 or v > 10:
            raise ValueError('作成試行回数は0-10回の範囲である必要があります')
        return v

    def update_timestamp(self) -> None:
        """更新タイムスタンプを現在時刻に設定"""
        self.updated_at = datetime.utcnow()

    def mark_creation_success(self, google_event_id: str, calendar_url: Optional[str] = None) -> None:
        """作成成功をマーク"""
        self.creation_status = CalendarStatus.SUCCESS
        self.google_event_id = google_event_id
        if calendar_url:
            self.google_calendar_url = calendar_url
        self.last_sync_at = datetime.utcnow()
        self.update_timestamp()

    def mark_creation_failed(self, error_message: str) -> None:
        """作成失敗をマーク"""
        self.creation_status = CalendarStatus.FAILED
        self.error_message = error_message
        self.creation_attempts += 1
        self.update_timestamp()

    def mark_cancelled(self) -> None:
        """キャンセル済みをマーク"""
        self.creation_status = CalendarStatus.CANCELLED
        self.update_timestamp()

    def mark_updated(self) -> None:
        """更新済みをマーク"""
        self.creation_status = CalendarStatus.UPDATED
        self.last_sync_at = datetime.utcnow()
        self.update_timestamp()

    def add_attendee(
        self,
        email: str,
        display_name: Optional[str] = None,
        optional: bool = False,
        organizer: bool = False
    ) -> None:
        """参加者を追加"""
        # 既存参加者のチェック
        for attendee in self.attendees:
            if attendee.email == email:
                return  # 既に存在する場合は何もしない

        attendee = CalendarAttendee(
            email=email,
            display_name=display_name,
            optional=optional,
            organizer=organizer
        )
        self.attendees.append(attendee)
        self.update_timestamp()

    def remove_attendee(self, email: str) -> bool:
        """参加者を削除"""
        for i, attendee in enumerate(self.attendees):
            if attendee.email == email:
                self.attendees.pop(i)
                self.update_timestamp()
                return True
        return False

    def update_attendee_status(self, email: str, status: AttendeeStatus, comment: Optional[str] = None) -> bool:
        """参加者のステータスを更新"""
        for attendee in self.attendees:
            if attendee.email == email:
                attendee.response_status = status
                if comment:
                    attendee.comment = comment
                self.update_timestamp()
                return True
        return False

    def get_attendee_count(self) -> int:
        """参加者数を取得"""
        return len(self.attendees)

    def get_confirmed_attendee_count(self) -> int:
        """確定参加者数を取得"""
        return sum(
            1 for attendee in self.attendees
            if attendee.response_status == AttendeeStatus.ACCEPTED
        )

    def add_reminder(self, method: str, minutes: int) -> None:
        """リマインダーを追加"""
        reminder = CalendarReminder(method=method, minutes=minutes)
        self.reminders.append(reminder)
        self.update_timestamp()

    def set_meeting_room(self, resource_id: str, room_name: Optional[str] = None) -> None:
        """会議室を設定"""
        self.meeting_room_resource = resource_id
        if room_name:
            self.meeting_room_name = room_name
        self.update_timestamp()

    def set_conference_data(self, conference_info: Dict[str, Any]) -> None:
        """オンライン会議情報を設定"""
        self.conference_data = conference_info
        self.update_timestamp()

    def duration_minutes(self) -> int:
        """イベント時間（分）"""
        return int((self.end_time - self.start_time).total_seconds() / 60)

    def is_in_past(self) -> bool:
        """過去のイベントかチェック"""
        return self.start_time < datetime.utcnow()

    def is_today(self) -> bool:
        """今日のイベントかチェック"""
        today = datetime.utcnow().date()
        return self.start_time.date() == today

    def needs_retry(self, max_attempts: int = 3) -> bool:
        """リトライが必要かチェック"""
        return (
            self.creation_status == CalendarStatus.FAILED and
            self.creation_attempts < max_attempts
        )

    def can_be_updated(self) -> bool:
        """更新可能かチェック"""
        return (
            self.creation_status == CalendarStatus.SUCCESS and
            self.google_event_id is not None and
            not self.is_in_past()
        )

    def get_status_display(self) -> str:
        """ステータスの日本語表示"""
        status_display = {
            CalendarStatus.PENDING: "作成待ち",
            CalendarStatus.SUCCESS: "作成完了",
            CalendarStatus.FAILED: "作成失敗",
            CalendarStatus.CANCELLED: "キャンセル",
            CalendarStatus.UPDATED: "更新済み"
        }
        return status_display.get(self.creation_status, "不明")

    def generate_calendar_event_data(self) -> Dict[str, Any]:
        """Google Calendar API用のイベントデータを生成"""
        event_data = {
            "summary": self.event_title,
            "start": {
                "dateTime": self.start_time.isoformat(),
                "timeZone": self.timezone
            },
            "end": {
                "dateTime": self.end_time.isoformat(),
                "timeZone": self.timezone
            },
            "visibility": self.visibility,
            "sendUpdates": "all" if self.send_notifications else "none"
        }

        if self.event_description:
            event_data["description"] = self.event_description

        if self.location:
            event_data["location"] = self.location

        if self.attendees:
            event_data["attendees"] = [
                {
                    "email": attendee.email,
                    "displayName": attendee.display_name,
                    "optional": attendee.optional,
                    "organizer": attendee.organizer
                }
                for attendee in self.attendees
            ]

        if self.reminders:
            event_data["reminders"] = {
                "useDefault": False,
                "overrides": [
                    {"method": reminder.method, "minutes": reminder.minutes}
                    for reminder in self.reminders
                ]
            }

        if self.meeting_room_resource:
            event_data["attendees"] = event_data.get("attendees", [])
            event_data["attendees"].append({
                "email": self.meeting_room_resource,
                "resource": True
            })

        if self.conference_data:
            event_data["conferenceData"] = self.conference_data

        if self.recurrence:
            event_data["recurrence"] = self.recurrence

        return event_data

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換（Firestore保存用）"""
        return {
            "calendar_entry_id": self.calendar_entry_id,
            "event_id": self.event_id,
            "google_event_id": self.google_event_id,
            "calendar_email": self.calendar_email,
            "calendar_id": self.calendar_id,
            "event_title": self.event_title,
            "event_description": self.event_description,
            "event_summary": self.event_summary,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "timezone": self.timezone,
            "all_day": self.all_day,
            "location": self.location,
            "conference_data": self.conference_data,
            "attendees": [attendee.dict() for attendee in self.attendees],
            "send_notifications": self.send_notifications,
            "meeting_room_resource": self.meeting_room_resource,
            "meeting_room_name": self.meeting_room_name,
            "visibility": self.visibility,
            "reminders": [reminder.dict() for reminder in self.reminders],
            "recurrence": self.recurrence,
            "creation_status": self.creation_status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "error_message": self.error_message,
            "creation_attempts": self.creation_attempts,
            "google_calendar_url": self.google_calendar_url,
            "ical_uid": self.ical_uid
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CalendarEntry":
        """辞書から CalendarEntry インスタンスを作成"""
        # datetimeフィールドの変換
        datetime_fields = ["start_time", "end_time", "created_at", "updated_at", "last_sync_at"]
        for field in datetime_fields:
            if data.get(field):
                data[field] = datetime.fromisoformat(data[field])

        # attendeesリストの変換
        if data.get("attendees"):
            data["attendees"] = [CalendarAttendee(**attendee_data) for attendee_data in data["attendees"]]

        # remindersリストの変換
        if data.get("reminders"):
            data["reminders"] = [CalendarReminder(**reminder_data) for reminder_data in data["reminders"]]

        return cls(**data)