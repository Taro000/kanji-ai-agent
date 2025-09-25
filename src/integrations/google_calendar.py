"""
Google Calendar API OAuth統合
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
from pydantic import BaseModel, Field
import logging
from urllib.parse import urlencode
import base64
import secrets

logger = logging.getLogger(__name__)


class OAuth2Config(BaseModel):
    """OAuth2設定"""
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: List[str] = Field(default_factory=lambda: [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events"
    ])
    auth_uri: str = "https://accounts.google.com/o/oauth2/v2/auth"
    token_uri: str = "https://oauth2.googleapis.com/token"


class OAuth2Credentials(BaseModel):
    """OAuth2認証情報"""
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: datetime
    scope: List[str]
    token_type: str = "Bearer"


class GoogleCalendarEvent(BaseModel):
    """Google Calendarイベント"""
    event_id: Optional[str] = None
    summary: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None
    attendees: List[str] = Field(default_factory=list)
    organizer: str
    timezone: str = "Asia/Tokyo"
    reminders: List[int] = Field(default_factory=lambda: [1440, 60, 15])  # 分単位
    visibility: str = "default"
    status: str = "confirmed"


class CalendarEventResponse(BaseModel):
    """イベント作成レスポンス"""
    success: bool
    event_id: Optional[str] = None
    html_link: Optional[str] = None
    error_message: Optional[str] = None
    retry_after: Optional[int] = None


class FreeBusyRequest(BaseModel):
    """空き時間検索リクエスト"""
    attendees: List[str]
    time_min: datetime
    time_max: datetime
    timezone: str = "Asia/Tokyo"


class FreeBusyResponse(BaseModel):
    """空き時間検索レスポンス"""
    success: bool
    busy_intervals: Dict[str, List[Tuple[datetime, datetime]]]
    error_message: Optional[str] = None


class GoogleCalendarClient:
    """
    Google Calendar API OAuth統合クライアント
    - OAuth2.0フロー管理
    - アクセストークン管理・リフレッシュ
    - イベントCRUD操作
    - 空き時間検索
    - レート制限対応
    """

    def __init__(self, oauth_config: OAuth2Config):
        self.config = oauth_config

        # レート制限設定（Google Calendar API制限に基づく）
        self.rate_limits = {
            "requests_per_second": 10,
            "requests_per_day": 1000000,
            "burst_capacity": 100
        }

        # リクエスト履歴（レート制限用）
        self.request_history: List[datetime] = []

        # Mock認証情報ストレージ
        self.credential_storage: Dict[str, OAuth2Credentials] = {}

    async def get_authorization_url(self, user_email: str, state: Optional[str] = None) -> Tuple[str, str]:
        """OAuth2認証URL生成"""
        if not state:
            state = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()

        auth_params = {
            "client_id": self.config.client_id,
            "response_type": "code",
            "scope": " ".join(self.config.scopes),
            "redirect_uri": self.config.redirect_uri,
            "state": f"{state}:{user_email}",
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true"
        }

        auth_url = f"{self.config.auth_uri}?{urlencode(auth_params)}"
        logger.info(f"OAuth2認証URL生成: {user_email}")

        return auth_url, state

    async def exchange_authorization_code(self, code: str, state: str) -> Tuple[OAuth2Credentials, str]:
        """認証コードをアクセストークンに交換"""
        # stateからuser_email抽出
        _, user_email = state.split(":", 1)

        # Mock token exchange
        access_token = f"mock_access_token_{secrets.token_hex(16)}"
        refresh_token = f"mock_refresh_token_{secrets.token_hex(16)}"

        credentials = OAuth2Credentials(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scope=self.config.scopes,
            token_type="Bearer"
        )

        # 認証情報保存
        self.credential_storage[user_email] = credentials

        logger.info(f"OAuth2トークン交換完了: {user_email}")
        return credentials, user_email

    async def refresh_access_token(self, user_email: str) -> Optional[OAuth2Credentials]:
        """アクセストークンリフレッシュ"""
        credentials = self.credential_storage.get(user_email)
        if not credentials or not credentials.refresh_token:
            logger.warning(f"リフレッシュトークンなし: {user_email}")
            return None

        # Mock token refresh
        new_access_token = f"mock_refreshed_token_{secrets.token_hex(16)}"

        new_credentials = OAuth2Credentials(
            access_token=new_access_token,
            refresh_token=credentials.refresh_token,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scope=credentials.scope,
            token_type="Bearer"
        )

        self.credential_storage[user_email] = new_credentials

        logger.info(f"アクセストークンリフレッシュ: {user_email}")
        return new_credentials

    async def get_valid_credentials(self, user_email: str) -> Optional[OAuth2Credentials]:
        """有効な認証情報取得（自動リフレッシュ付き）"""
        credentials = self.credential_storage.get(user_email)
        if not credentials:
            return None

        # トークン有効期限チェック
        if datetime.now(timezone.utc) >= credentials.expires_at:
            logger.info(f"トークン期限切れ、リフレッシュ実行: {user_email}")
            return await self.refresh_access_token(user_email)

        return credentials

    async def create_calendar_event(self, user_email: str, event: GoogleCalendarEvent) -> CalendarEventResponse:
        """カレンダーイベント作成"""
        # レート制限チェック
        if not await self._check_rate_limit():
            return CalendarEventResponse(
                success=False,
                error_message="レート制限に達しました。しばらく待ってから再試行してください。",
                retry_after=60
            )

        # 認証情報取得
        credentials = await self.get_valid_credentials(user_email)
        if not credentials:
            return CalendarEventResponse(
                success=False,
                error_message="認証が必要です。OAuth2フローを完了してください。"
            )

        try:
            # Google Calendar API呼び出し（Mock）
            event_data = await self._build_calendar_event_data(event)
            response = await self._call_calendar_api(
                "POST",
                "events",
                credentials.access_token,
                data=event_data
            )

            if response.get("success"):
                return CalendarEventResponse(
                    success=True,
                    event_id=response.get("id"),
                    html_link=response.get("htmlLink")
                )
            else:
                return CalendarEventResponse(
                    success=False,
                    error_message=response.get("error", "イベント作成に失敗しました")
                )

        except Exception as e:
            logger.error(f"カレンダーイベント作成エラー: {str(e)}")
            return CalendarEventResponse(
                success=False,
                error_message=f"予期しないエラー: {str(e)}"
            )

    async def update_calendar_event(self, user_email: str, event_id: str, event: GoogleCalendarEvent) -> CalendarEventResponse:
        """カレンダーイベント更新"""
        if not await self._check_rate_limit():
            return CalendarEventResponse(
                success=False,
                error_message="レート制限に達しました。",
                retry_after=60
            )

        credentials = await self.get_valid_credentials(user_email)
        if not credentials:
            return CalendarEventResponse(
                success=False,
                error_message="認証が必要です。"
            )

        try:
            event_data = await self._build_calendar_event_data(event)
            response = await self._call_calendar_api(
                "PUT",
                f"events/{event_id}",
                credentials.access_token,
                data=event_data
            )

            if response.get("success"):
                return CalendarEventResponse(
                    success=True,
                    event_id=response.get("id"),
                    html_link=response.get("htmlLink")
                )
            else:
                return CalendarEventResponse(
                    success=False,
                    error_message=response.get("error", "イベント更新に失敗しました")
                )

        except Exception as e:
            logger.error(f"カレンダーイベント更新エラー: {str(e)}")
            return CalendarEventResponse(
                success=False,
                error_message=f"予期しないエラー: {str(e)}"
            )

    async def delete_calendar_event(self, user_email: str, event_id: str) -> CalendarEventResponse:
        """カレンダーイベント削除"""
        if not await self._check_rate_limit():
            return CalendarEventResponse(
                success=False,
                error_message="レート制限に達しました。",
                retry_after=60
            )

        credentials = await self.get_valid_credentials(user_email)
        if not credentials:
            return CalendarEventResponse(
                success=False,
                error_message="認証が必要です。"
            )

        try:
            response = await self._call_calendar_api(
                "DELETE",
                f"events/{event_id}",
                credentials.access_token
            )

            return CalendarEventResponse(success=True)

        except Exception as e:
            logger.error(f"カレンダーイベント削除エラー: {str(e)}")
            return CalendarEventResponse(
                success=False,
                error_message=f"削除エラー: {str(e)}"
            )

    async def get_free_busy_info(self, user_email: str, request: FreeBusyRequest) -> FreeBusyResponse:
        """空き時間情報取得"""
        if not await self._check_rate_limit():
            return FreeBusyResponse(
                success=False,
                busy_intervals={},
                error_message="レート制限に達しました。"
            )

        credentials = await self.get_valid_credentials(user_email)
        if not credentials:
            return FreeBusyResponse(
                success=False,
                busy_intervals={},
                error_message="認証が必要です。"
            )

        try:
            # Google Calendar FreeBusy API呼び出し（Mock）
            freebusy_data = {
                "timeMin": request.time_min.isoformat(),
                "timeMax": request.time_max.isoformat(),
                "timeZone": request.timezone,
                "items": [{"id": email} for email in request.attendees]
            }

            response = await self._call_calendar_api(
                "POST",
                "freebusy",
                credentials.access_token,
                data=freebusy_data
            )

            if response.get("success"):
                busy_intervals = self._parse_freebusy_response(response)
                return FreeBusyResponse(
                    success=True,
                    busy_intervals=busy_intervals
                )
            else:
                return FreeBusyResponse(
                    success=False,
                    busy_intervals={},
                    error_message="空き時間情報の取得に失敗しました"
                )

        except Exception as e:
            logger.error(f"FreeBusy情報取得エラー: {str(e)}")
            return FreeBusyResponse(
                success=False,
                busy_intervals={},
                error_message=f"予期しないエラー: {str(e)}"
            )

    async def _build_calendar_event_data(self, event: GoogleCalendarEvent) -> Dict[str, Any]:
        """Google Calendar API用イベントデータ構築"""
        event_data = {
            "summary": event.summary,
            "start": {
                "dateTime": event.start_time.isoformat(),
                "timeZone": event.timezone
            },
            "end": {
                "dateTime": event.end_time.isoformat(),
                "timeZone": event.timezone
            },
            "attendees": [{"email": email} for email in event.attendees],
            "organizer": {"email": event.organizer},
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": minutes}
                    for minutes in event.reminders
                ] + [
                    {"method": "popup", "minutes": 15}
                ]
            },
            "visibility": event.visibility,
            "status": event.status
        }

        if event.description:
            event_data["description"] = event.description

        if event.location:
            event_data["location"] = event.location

        return event_data

    async def _call_calendar_api(self, method: str, endpoint: str, access_token: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Google Calendar API呼び出し（Mock）"""
        logger.info(f"Google Calendar API呼び出し: {method} {endpoint}")

        # レート制限記録
        self.request_history.append(datetime.now())

        # Mock API レスポンス
        if method == "POST" and endpoint == "events":
            return {
                "success": True,
                "id": f"mock_event_{secrets.token_hex(8)}",
                "htmlLink": f"https://calendar.google.com/event?eid={secrets.token_hex(16)}"
            }
        elif method == "PUT" and endpoint.startswith("events/"):
            return {
                "success": True,
                "id": endpoint.split("/")[1],
                "htmlLink": f"https://calendar.google.com/event?eid={secrets.token_hex(16)}"
            }
        elif method == "DELETE" and endpoint.startswith("events/"):
            return {"success": True}
        elif method == "POST" and endpoint == "freebusy":
            return {
                "success": True,
                "calendars": {
                    email: {
                        "busy": [
                            {
                                "start": (datetime.now() + timedelta(hours=2)).isoformat(),
                                "end": (datetime.now() + timedelta(hours=3)).isoformat()
                            }
                        ]
                    }
                    for email in data.get("items", [])
                }
            }
        else:
            return {"success": False, "error": "不明なAPIエンドポイント"}

    def _parse_freebusy_response(self, response: Dict[str, Any]) -> Dict[str, List[Tuple[datetime, datetime]]]:
        """FreeBusyレスポンス解析"""
        busy_intervals = {}

        calendars = response.get("calendars", {})
        for email, calendar_data in calendars.items():
            intervals = []
            for busy_period in calendar_data.get("busy", []):
                start = datetime.fromisoformat(busy_period["start"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(busy_period["end"].replace("Z", "+00:00"))
                intervals.append((start, end))

            busy_intervals[email] = intervals

        return busy_intervals

    async def _check_rate_limit(self) -> bool:
        """レート制限チェック"""
        now = datetime.now()

        # 古い履歴削除（1秒以上前）
        self.request_history = [
            ts for ts in self.request_history
            if (now - ts).total_seconds() < 1
        ]

        # 1秒あたりのリクエスト制限チェック
        if len(self.request_history) >= self.rate_limits["requests_per_second"]:
            logger.warning("レート制限に達しました")
            return False

        return True


class CalendarEventManager:
    """
    カレンダーイベント管理クラス
    - 高レベルイベント操作
    - バッチ処理対応
    - エラー処理とリトライ
    """

    def __init__(self, calendar_client: GoogleCalendarClient):
        self.client = calendar_client

    async def create_event_with_retry(self, user_email: str, event: GoogleCalendarEvent, max_retries: int = 3) -> CalendarEventResponse:
        """リトライ付きイベント作成"""
        last_error = None

        for attempt in range(max_retries):
            try:
                result = await self.client.create_calendar_event(user_email, event)

                if result.success:
                    return result

                if result.retry_after:
                    logger.info(f"レート制限によりリトライ待機: {result.retry_after}秒")
                    await asyncio.sleep(result.retry_after)

                last_error = result.error_message

            except Exception as e:
                last_error = str(e)
                logger.warning(f"イベント作成試行 {attempt + 1} 失敗: {last_error}")

                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # 指数バックオフ

        return CalendarEventResponse(
            success=False,
            error_message=f"リトライ回数超過: {last_error}"
        )

    async def batch_create_events(self, user_email: str, events: List[GoogleCalendarEvent]) -> List[CalendarEventResponse]:
        """バッチイベント作成"""
        results = []

        # 並行処理でイベント作成（レート制限考慮で制限付き）
        semaphore = asyncio.Semaphore(5)  # 最大5並行

        async def create_with_semaphore(event: GoogleCalendarEvent):
            async with semaphore:
                return await self.create_event_with_retry(user_email, event)

        tasks = [create_with_semaphore(event) for event in events]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 例外処理
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                processed_results.append(CalendarEventResponse(
                    success=False,
                    error_message=str(result)
                ))
            else:
                processed_results.append(result)

        return processed_results

    async def find_optimal_meeting_time(self, user_email: str, attendees: List[str], duration_minutes: int, preferred_start: datetime, search_days: int = 7) -> Optional[Tuple[datetime, datetime]]:
        """最適会議時間検索"""
        # 検索期間設定
        search_start = preferred_start.replace(hour=9, minute=0, second=0, microsecond=0)  # 9:00から開始
        search_end = search_start + timedelta(days=search_days)

        # 空き時間情報取得
        freebusy_request = FreeBusyRequest(
            attendees=attendees,
            time_min=search_start,
            time_max=search_end
        )

        freebusy_response = await self.client.get_free_busy_info(user_email, freebusy_request)

        if not freebusy_response.success:
            logger.warning(f"空き時間情報取得失敗: {freebusy_response.error_message}")
            return None

        # 最適時間スロット検索
        return self._find_best_time_slot(
            freebusy_response.busy_intervals,
            search_start,
            search_end,
            duration_minutes
        )

    def _find_best_time_slot(self, busy_intervals: Dict[str, List[Tuple[datetime, datetime]]], search_start: datetime, search_end: datetime, duration_minutes: int) -> Optional[Tuple[datetime, datetime]]:
        """最適時間スロット検索"""
        slot_duration = timedelta(minutes=duration_minutes)

        # 営業時間内での30分刻みスロット生成
        current_time = search_start
        while current_time + slot_duration <= search_end:
            # 営業時間チェック（9:00-18:00）
            if current_time.hour < 9 or current_time.hour >= 18:
                current_time += timedelta(minutes=30)
                continue

            # 全員空いているかチェック
            is_free_for_all = True
            proposed_end = current_time + slot_duration

            for attendee_email, intervals in busy_intervals.items():
                for busy_start, busy_end in intervals:
                    # 重複チェック
                    if (current_time < busy_end and proposed_end > busy_start):
                        is_free_for_all = False
                        break

                if not is_free_for_all:
                    break

            if is_free_for_all:
                return (current_time, proposed_end)

            current_time += timedelta(minutes=30)

        return None