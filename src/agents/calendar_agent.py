"""
Calendar Agent - Google Calendar統合とイベント作成
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field
import logging

from .base_agent import BaseAgent, AgentMessage, MessageType, AgentCapability
from ..models.event import Event, EventStatus
from ..models.calendar_entry import CalendarEntry, CalendarEntryType, RoomBookingStatus
from ..models.venue import Venue, VenueType
from ..models.coordination_session import CoordinationSession
from ..models.participant import Participant

logger = logging.getLogger(__name__)


class CalendarEventRequest(BaseModel):
    """カレンダーイベント作成リクエスト"""
    event_id: str
    title: str
    description: str
    start_time: datetime
    end_time: datetime
    venue: Optional[Venue] = None
    participants: List[Participant]
    organizer_email: str
    meeting_room_required: bool = False


class CalendarEventResponse(BaseModel):
    """カレンダーイベント作成レスポンス"""
    success: bool
    calendar_entry_id: Optional[str] = None
    google_event_id: Optional[str] = None
    meeting_room_booking_id: Optional[str] = None
    error_message: Optional[str] = None
    booking_confirmation_url: Optional[str] = None


class MeetingRoomSearchCriteria(BaseModel):
    """会議室検索条件"""
    start_time: datetime
    end_time: datetime
    capacity: int
    location_preference: Optional[str] = None
    equipment_requirements: List[str] = Field(default_factory=list)


class MeetingRoomOption(BaseModel):
    """会議室選択肢"""
    room_id: str
    name: str
    capacity: int
    location: str
    equipment: List[str]
    availability_score: float
    booking_url: str


class OAuth2Credentials(BaseModel):
    """OAuth2認証情報"""
    access_token: str
    refresh_token: str
    expires_at: datetime
    scope: List[str]


class CalendarNotification(BaseModel):
    """カレンダー通知設定"""
    email_reminder_minutes: List[int] = Field(default_factory=lambda: [1440, 60])  # 1日前、1時間前
    popup_reminder_minutes: List[int] = Field(default_factory=lambda: [15])       # 15分前
    send_invitations: bool = True
    japanese_locale: bool = True


class CalendarAgent(BaseAgent):
    """
    Google Calendar統合エージェント
    - OAuth2.0認証フロー
    - Google Calendarイベント作成
    - 会議室予約管理
    - 日本語通知対応
    """

    def __init__(self, agent_id: str = "calendar_agent"):
        capabilities = [
            AgentCapability(
                name="google_calendar_integration",
                description="Google Calendarとの統合",
                inputs=["event_details", "participant_list", "venue_info"],
                outputs=["calendar_event", "meeting_room_booking"]
            ),
            AgentCapability(
                name="oauth2_authentication",
                description="Google OAuth2.0認証管理",
                inputs=["user_credentials"],
                outputs=["access_token", "authentication_status"]
            ),
            AgentCapability(
                name="meeting_room_booking",
                description="会議室予約システム統合",
                inputs=["room_requirements", "time_slot"],
                outputs=["room_reservation", "booking_confirmation"]
            ),
            AgentCapability(
                name="japanese_notification",
                description="日本語対応通知システム",
                inputs=["event_info", "participant_preferences"],
                outputs=["localized_invitations", "reminder_notifications"]
            )
        ]

        super().__init__(
            agent_id=agent_id,
            name="Calendar Agent",
            description="Google Calendar統合とイベント作成を管理するエージェント",
            capabilities=capabilities
        )

        # 日本語メッセージテンプレート
        self.japanese_templates = {
            "event_created": "{title}のイベントを作成しました。\n開始時刻: {start_time}\n場所: {location}",
            "room_booked": "会議室「{room_name}」を予約しました。\n日時: {datetime}\n参加者: {participants}",
            "invitation_sent": "参加者への招待状を送信しました。",
            "reminder_set": "リマインダーを設定しました: {reminders}",
            "booking_failed": "申し訳ございません。{resource}の予約に失敗しました。\n理由: {error}",
            "manual_booking_required": "自動予約ができませんでした。以下のURLから手動で予約してください:\n{url}"
        }

        # Mock OAuth2クライアント設定
        self.oauth_config = {
            "client_id": "mock_google_client_id",
            "client_secret": "mock_google_client_secret",
            "redirect_uri": "http://localhost:8080/oauth/callback",
            "scopes": [
                "https://www.googleapis.com/auth/calendar",
                "https://www.googleapis.com/auth/calendar.events",
                "https://www.googleapis.com/auth/admin.directory.resource.calendar"
            ]
        }

        # 会議室データベース（Mock）
        self.meeting_rooms = {
            "room_001": {
                "name": "大会議室A",
                "capacity": 20,
                "location": "本社1F",
                "equipment": ["プロジェクター", "ホワイトボード", "ビデオ会議システム"],
                "booking_url": "https://booking.company.com/rooms/001"
            },
            "room_002": {
                "name": "会議室B",
                "capacity": 8,
                "location": "本社2F",
                "equipment": ["モニター", "ホワイトボード"],
                "booking_url": "https://booking.company.com/rooms/002"
            },
            "room_003": {
                "name": "小会議室C",
                "capacity": 4,
                "location": "本社3F",
                "equipment": ["モニター"],
                "booking_url": "https://booking.company.com/rooms/003"
            }
        }

        self._register_message_handlers()

    def _register_message_handlers(self):
        """メッセージハンドラーの登録"""
        self.message_handlers[MessageType.CREATE_CALENDAR_EVENT] = self._handle_create_calendar_event
        self.message_handlers[MessageType.BOOK_MEETING_ROOM] = self._handle_book_meeting_room
        self.message_handlers[MessageType.OAUTH_AUTHENTICATE] = self._handle_oauth_authenticate
        self.message_handlers[MessageType.SEND_NOTIFICATIONS] = self._handle_send_notifications

    async def _handle_create_calendar_event(self, message: AgentMessage) -> AgentMessage:
        """Google Calendarイベント作成"""
        try:
            request = CalendarEventRequest(**message.payload)
            logger.info(f"カレンダーイベント作成開始: {request.title}")

            # OAuth2認証確認
            auth_result = await self._verify_oauth_credentials(request.organizer_email)
            if not auth_result:
                return self._create_error_response(
                    "OAuth2認証が必要です。認証フローを開始してください。",
                    message.conversation_id
                )

            # 会議室が必要な場合の予約
            meeting_room_booking = None
            if request.meeting_room_required:
                room_result = await self._book_meeting_room_for_event(request)
                if room_result.success:
                    meeting_room_booking = room_result
                else:
                    logger.warning(f"会議室予約失敗: {room_result.error_message}")

            # Google Calendarイベント作成
            calendar_result = await self._create_google_calendar_event(request, meeting_room_booking)

            if calendar_result.success:
                # カレンダーエントリ保存
                calendar_entry = await self._save_calendar_entry(request, calendar_result, meeting_room_booking)

                # 日本語通知送信
                await self._send_japanese_notifications(request, calendar_entry)

                response_message = self.japanese_templates["event_created"].format(
                    title=request.title,
                    start_time=request.start_time.strftime("%Y年%m月%d日 %H:%M"),
                    location=self._get_location_text(request.venue, meeting_room_booking)
                )

                return AgentMessage(
                    sender_id=self.agent_id,
                    recipient_id=message.sender_id,
                    message_type=MessageType.TASK_COMPLETED,
                    conversation_id=message.conversation_id,
                    payload={
                        "success": True,
                        "calendar_entry_id": calendar_entry.entry_id,
                        "google_event_id": calendar_result.google_event_id,
                        "message": response_message,
                        "meeting_room_booking": meeting_room_booking.dict() if meeting_room_booking else None
                    }
                )
            else:
                return self._create_error_response(
                    f"カレンダーイベント作成に失敗しました: {calendar_result.error_message}",
                    message.conversation_id
                )

        except Exception as e:
            logger.error(f"カレンダーイベント作成エラー: {str(e)}")
            return self._create_error_response(
                f"予期しないエラーが発生しました: {str(e)}",
                message.conversation_id
            )

    async def _handle_book_meeting_room(self, message: AgentMessage) -> AgentMessage:
        """会議室予約処理"""
        try:
            criteria = MeetingRoomSearchCriteria(**message.payload)
            logger.info(f"会議室検索開始: {criteria.capacity}人用")

            # 利用可能な会議室検索
            available_rooms = await self._search_available_meeting_rooms(criteria)

            if not available_rooms:
                return self._create_error_response(
                    "指定された時間帯に利用可能な会議室が見つかりませんでした。",
                    message.conversation_id
                )

            # 最適な会議室選択
            best_room = max(available_rooms, key=lambda r: r.availability_score)

            # 予約実行（Mock）
            booking_result = await self._execute_room_booking(best_room, criteria)

            if booking_result.success:
                response_message = self.japanese_templates["room_booked"].format(
                    room_name=best_room.name,
                    datetime=f"{criteria.start_time.strftime('%Y年%m月%d日 %H:%M')}-{criteria.end_time.strftime('%H:%M')}",
                    participants=f"{criteria.capacity}名"
                )

                return AgentMessage(
                    sender_id=self.agent_id,
                    recipient_id=message.sender_id,
                    message_type=MessageType.TASK_COMPLETED,
                    conversation_id=message.conversation_id,
                    payload={
                        "success": True,
                        "room_booking": booking_result.dict(),
                        "message": response_message
                    }
                )
            else:
                fallback_message = self.japanese_templates["manual_booking_required"].format(
                    url=best_room.booking_url
                )

                return AgentMessage(
                    sender_id=self.agent_id,
                    recipient_id=message.sender_id,
                    message_type=MessageType.MANUAL_INTERVENTION_REQUIRED,
                    conversation_id=message.conversation_id,
                    payload={
                        "success": False,
                        "manual_booking_url": best_room.booking_url,
                        "message": fallback_message
                    }
                )

        except Exception as e:
            logger.error(f"会議室予約エラー: {str(e)}")
            return self._create_error_response(
                f"会議室予約でエラーが発生しました: {str(e)}",
                message.conversation_id
            )

    async def _handle_oauth_authenticate(self, message: AgentMessage) -> AgentMessage:
        """OAuth2認証処理"""
        try:
            user_email = message.payload.get("user_email")
            logger.info(f"OAuth2認証開始: {user_email}")

            # Mock認証フロー
            auth_url = self._generate_oauth_url(user_email)

            return AgentMessage(
                sender_id=self.agent_id,
                recipient_id=message.sender_id,
                message_type=MessageType.OAUTH_REQUIRED,
                conversation_id=message.conversation_id,
                payload={
                    "auth_url": auth_url,
                    "message": f"Google Calendarとの連携のため、以下のURLで認証を完了してください:\n{auth_url}"
                }
            )

        except Exception as e:
            logger.error(f"OAuth2認証エラー: {str(e)}")
            return self._create_error_response(
                f"認証プロセスでエラーが発生しました: {str(e)}",
                message.conversation_id
            )

    async def _handle_send_notifications(self, message: AgentMessage) -> AgentMessage:
        """通知送信処理"""
        try:
            event_info = message.payload
            logger.info(f"通知送信開始: {event_info.get('event_title')}")

            # 日本語招待状作成
            invitation_text = self._create_japanese_invitation(event_info)

            # リマインダー設定
            reminders = self._setup_event_reminders(event_info)

            # Mock通知送信
            await self._send_mock_notifications(event_info, invitation_text, reminders)

            response_message = self.japanese_templates["invitation_sent"] + "\n" + \
                             self.japanese_templates["reminder_set"].format(
                                 reminders=", ".join([f"{r}分前" for r in [1440, 60, 15]])
                             )

            return AgentMessage(
                sender_id=self.agent_id,
                recipient_id=message.sender_id,
                message_type=MessageType.TASK_COMPLETED,
                conversation_id=message.conversation_id,
                payload={
                    "success": True,
                    "message": response_message
                }
            )

        except Exception as e:
            logger.error(f"通知送信エラー: {str(e)}")
            return self._create_error_response(
                f"通知送信でエラーが発生しました: {str(e)}",
                message.conversation_id
            )

    async def _verify_oauth_credentials(self, user_email: str) -> bool:
        """OAuth2認証情報確認（Mock）"""
        # 実際の実装では、データベースから認証情報を取得して有効性を確認
        logger.info(f"OAuth2認証確認: {user_email}")
        return True  # Mock: 常に認証済みとして扱う

    async def _book_meeting_room_for_event(self, request: CalendarEventRequest) -> CalendarEventResponse:
        """イベント用会議室予約"""
        criteria = MeetingRoomSearchCriteria(
            start_time=request.start_time,
            end_time=request.end_time,
            capacity=len(request.participants),
            location_preference=None
        )

        available_rooms = await self._search_available_meeting_rooms(criteria)

        if available_rooms:
            best_room = max(available_rooms, key=lambda r: r.availability_score)
            return await self._execute_room_booking(best_room, criteria)
        else:
            return CalendarEventResponse(
                success=False,
                error_message="利用可能な会議室が見つかりませんでした"
            )

    async def _search_available_meeting_rooms(self, criteria: MeetingRoomSearchCriteria) -> List[MeetingRoomOption]:
        """利用可能会議室検索"""
        available_rooms = []

        for room_id, room_info in self.meeting_rooms.items():
            if room_info["capacity"] >= criteria.capacity:
                # Mock可用性チェック
                availability_score = await self._calculate_room_availability_score(
                    room_id, criteria
                )

                if availability_score > 0:
                    room_option = MeetingRoomOption(
                        room_id=room_id,
                        name=room_info["name"],
                        capacity=room_info["capacity"],
                        location=room_info["location"],
                        equipment=room_info["equipment"],
                        availability_score=availability_score,
                        booking_url=room_info["booking_url"]
                    )
                    available_rooms.append(room_option)

        return available_rooms

    async def _calculate_room_availability_score(self, room_id: str, criteria: MeetingRoomSearchCriteria) -> float:
        """会議室可用性スコア計算（Mock）"""
        # 実際の実装では、予約システムAPIから空き状況を取得
        base_score = 0.8  # Mock: 基本的に利用可能

        # 時間帯による調整
        hour = criteria.start_time.hour
        if 9 <= hour <= 17:  # 営業時間内
            time_bonus = 0.2
        else:
            time_bonus = -0.3

        # 収容人数による調整
        room_capacity = self.meeting_rooms[room_id]["capacity"]
        participant_count = criteria.capacity

        if participant_count <= room_capacity * 0.7:  # 適切なサイズ
            capacity_bonus = 0.1
        elif participant_count > room_capacity:  # 収容不可
            return 0.0
        else:
            capacity_bonus = 0.0

        final_score = base_score + time_bonus + capacity_bonus
        return max(0.0, min(1.0, final_score))

    async def _execute_room_booking(self, room: MeetingRoomOption, criteria: MeetingRoomSearchCriteria) -> CalendarEventResponse:
        """会議室予約実行（Mock）"""
        # 実際の実装では、会議室予約システムAPIを呼び出し
        logger.info(f"会議室予約実行: {room.name}")

        # Mock成功レスポンス
        booking_id = f"booking_{room.room_id}_{int(criteria.start_time.timestamp())}"

        return CalendarEventResponse(
            success=True,
            meeting_room_booking_id=booking_id,
            booking_confirmation_url=room.booking_url
        )

    async def _create_google_calendar_event(self, request: CalendarEventRequest, room_booking: Optional[CalendarEventResponse]) -> CalendarEventResponse:
        """Google Calendarイベント作成（Mock）"""
        logger.info(f"Google Calendarイベント作成: {request.title}")

        # Mock Google Calendar API呼び出し
        event_data = {
            "summary": request.title,
            "description": request.description,
            "start": {
                "dateTime": request.start_time.isoformat(),
                "timeZone": "Asia/Tokyo"
            },
            "end": {
                "dateTime": request.end_time.isoformat(),
                "timeZone": "Asia/Tokyo"
            },
            "attendees": [{"email": p.email} for p in request.participants if p.email],
            "organizer": {"email": request.organizer_email}
        }

        if request.venue:
            event_data["location"] = f"{request.venue.name}, {request.venue.address}"
        elif room_booking and room_booking.success:
            room_name = next((r["name"] for r in self.meeting_rooms.values()
                             if room_booking.meeting_room_booking_id and r["name"] in room_booking.meeting_room_booking_id),
                            "会議室")
            event_data["location"] = room_name

        # Mock成功レスポンス
        google_event_id = f"google_event_{int(request.start_time.timestamp())}"

        return CalendarEventResponse(
            success=True,
            google_event_id=google_event_id
        )

    async def _save_calendar_entry(self, request: CalendarEventRequest, calendar_result: CalendarEventResponse, room_booking: Optional[CalendarEventResponse]) -> CalendarEntry:
        """カレンダーエントリ保存"""
        entry_type = CalendarEntryType.MEETING if request.meeting_room_required else CalendarEntryType.EVENT

        calendar_entry = CalendarEntry(
            entry_id=f"cal_entry_{int(request.start_time.timestamp())}",
            event_id=request.event_id,
            google_event_id=calendar_result.google_event_id,
            entry_type=entry_type,
            title=request.title,
            start_time=request.start_time,
            end_time=request.end_time,
            organizer_email=request.organizer_email,
            participant_emails=[p.email for p in request.participants if p.email],
            venue_id=request.venue.venue_id if request.venue else None,
            room_booking_id=room_booking.meeting_room_booking_id if room_booking and room_booking.success else None,
            room_booking_status=RoomBookingStatus.CONFIRMED if room_booking and room_booking.success else RoomBookingStatus.NOT_REQUIRED,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        # 実際の実装では、リポジトリを使用してFirestoreに保存
        logger.info(f"カレンダーエントリ保存: {calendar_entry.entry_id}")

        return calendar_entry

    async def _send_japanese_notifications(self, request: CalendarEventRequest, calendar_entry: CalendarEntry):
        """日本語通知送信"""
        logger.info(f"日本語通知送信: {request.title}")

        # 招待状作成
        invitation_text = self._create_japanese_invitation({
            "title": request.title,
            "start_time": request.start_time,
            "end_time": request.end_time,
            "venue": request.venue,
            "description": request.description
        })

        # Mock通知送信
        for participant in request.participants:
            if participant.email:
                logger.info(f"招待状送信: {participant.email}")

    def _create_japanese_invitation(self, event_info: Dict[str, Any]) -> str:
        """日本語招待状作成"""
        invitation_template = """
{title}のご案内

【日時】{date} {start_time}〜{end_time}
【場所】{location}
【内容】{description}

ご参加をお待ちしております。

※このメールは自動送信されています。
"""

        start_time = event_info["start_time"]
        end_time = event_info["end_time"]
        venue = event_info.get("venue")

        location = "未定"
        if venue:
            location = f"{venue.name}\n{venue.address}"

        return invitation_template.format(
            title=event_info["title"],
            date=start_time.strftime("%Y年%m月%d日（%a）"),
            start_time=start_time.strftime("%H:%M"),
            end_time=end_time.strftime("%H:%M"),
            location=location,
            description=event_info.get("description", "詳細は別途ご連絡いたします。")
        )

    def _setup_event_reminders(self, event_info: Dict[str, Any]) -> List[int]:
        """イベントリマインダー設定"""
        # 標準的な日本のビジネス慣行に基づくリマインダー
        return [1440, 60, 15]  # 1日前、1時間前、15分前

    async def _send_mock_notifications(self, event_info: Dict[str, Any], invitation_text: str, reminders: List[int]):
        """Mock通知送信"""
        logger.info("Mock通知送信実行")
        # 実際の実装では、メールサービスAPIを使用

    def _get_location_text(self, venue: Optional[Venue], room_booking: Optional[CalendarEventResponse]) -> str:
        """場所テキスト生成"""
        if venue:
            return f"{venue.name}（{venue.address}）"
        elif room_booking and room_booking.success:
            return "社内会議室"
        else:
            return "場所未定"

    def _generate_oauth_url(self, user_email: str) -> str:
        """OAuth2認証URL生成（Mock）"""
        # 実際の実装では、Google OAuth2.0ライブラリを使用
        return f"https://accounts.google.com/oauth/authorize?client_id={self.oauth_config['client_id']}&scope={'%20'.join(self.oauth_config['scopes'])}&response_type=code&redirect_uri={self.oauth_config['redirect_uri']}&state={user_email}"

    def _create_error_response(self, error_message: str, conversation_id: str) -> AgentMessage:
        """エラーレスポンス作成"""
        return AgentMessage(
            sender_id=self.agent_id,
            recipient_id="coordination_agent",
            message_type=MessageType.TASK_FAILED,
            conversation_id=conversation_id,
            payload={
                "success": False,
                "error": error_message
            }
        )