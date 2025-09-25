"""
Google Calendar API統合のコントラクトテスト。

このテストは、Google Calendar APIとの統合が正しく動作し、
イベントの作成、更新、削除、参加者の招待が適切に処理されることを検証します。

参照: specs/002-slack-bot-ai/contracts/google_calendar.yaml
"""

from typing import Any, Dict, List
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time

# NOTE: これらのインポートは実装が存在するまで失敗します（TDD）
# これはTDDアプローチに期待される必要な動作です
try:
    from src.integrations.google_calendar import GoogleCalendarClient
    from src.models.event import CalendarEvent, EventParticipant
except ImportError:
    # TDD段階では期待される - テストは最初に失敗する必要があります
    pytest.skip("実装がまだ利用できません", allow_module_level=True)


class TestGoogleCalendarAPI:
    """Google Calendar APIコントラクトテスト。"""

    @pytest.fixture
    def calendar_client(self) -> GoogleCalendarClient:
        """テスト用Calendar APIクライアント。"""
        return GoogleCalendarClient(
            credentials_path="/mock/credentials.json",
            calendar_id="primary"
        )

    @pytest.fixture
    def event_data(self) -> Dict[str, Any]:
        """有効なイベントデータ。"""
        return {
            "summary": "チームランチ",
            "description": "月次チームランチミーティング",
            "start_time": datetime(2024, 3, 15, 12, 0),
            "end_time": datetime(2024, 3, 15, 13, 30),
            "location": "カフェテリア A",
            "attendees": [
                {"email": "user1@example.com", "display_name": "田中太郎"},
                {"email": "user2@example.com", "display_name": "佐藤花子"}
            ],
            "timezone": "Asia/Tokyo"
        }

    @pytest.fixture
    def japanese_event_data(self) -> Dict[str, Any]:
        """日本語イベントデータ。"""
        return {
            "summary": "勉強会：Python基礎",
            "description": "初心者向けPython勉強会です。\n\n議題：\n- 基本構文\n- データ型\n- 関数",
            "start_time": datetime(2024, 3, 20, 14, 0),
            "end_time": datetime(2024, 3, 20, 16, 0),
            "location": "会議室B",
            "attendees": [
                {"email": "developer1@example.com", "display_name": "山田一郎"},
                {"email": "developer2@example.com", "display_name": "鈴木二郎"}
            ],
            "timezone": "Asia/Tokyo"
        }

    @pytest.fixture
    def mock_calendar_service(self):
        """モックされたCalendar APIサービス。"""
        with patch('googleapiclient.discovery.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service
            yield mock_service

    @freeze_time("2024-03-10 10:00:00")
    def test_create_event_success(
        self,
        calendar_client: GoogleCalendarClient,
        event_data: Dict[str, Any],
        mock_calendar_service: Mock
    ) -> None:
        """イベント作成の成功テスト。"""
        # モックレスポンス設定
        mock_calendar_service.events().insert().execute.return_value = {
            "id": "event123",
            "htmlLink": "https://calendar.google.com/event?eid=event123",
            "summary": event_data["summary"],
            "start": {"dateTime": "2024-03-15T12:00:00+09:00"},
            "end": {"dateTime": "2024-03-15T13:30:00+09:00"},
            "status": "confirmed"
        }

        # イベント作成実行
        result = calendar_client.create_event(
            summary=event_data["summary"],
            description=event_data["description"],
            start_time=event_data["start_time"],
            end_time=event_data["end_time"],
            location=event_data["location"],
            attendees=event_data["attendees"],
            timezone=event_data["timezone"]
        )

        # 結果検証
        assert result["id"] == "event123"
        assert result["status"] == "confirmed"
        assert "htmlLink" in result

        # API呼び出し検証
        mock_calendar_service.events().insert.assert_called_once()
        call_args = mock_calendar_service.events().insert.call_args
        assert call_args[1]["calendarId"] == "primary"
        assert call_args[1]["body"]["summary"] == event_data["summary"]

    def test_create_japanese_event_encoding(
        self,
        calendar_client: GoogleCalendarClient,
        japanese_event_data: Dict[str, Any],
        mock_calendar_service: Mock
    ) -> None:
        """日本語イベントの文字エンコーディングテスト。"""
        mock_calendar_service.events().insert().execute.return_value = {
            "id": "jp_event123",
            "summary": japanese_event_data["summary"],
            "description": japanese_event_data["description"],
            "status": "confirmed"
        }

        result = calendar_client.create_event(
            summary=japanese_event_data["summary"],
            description=japanese_event_data["description"],
            start_time=japanese_event_data["start_time"],
            end_time=japanese_event_data["end_time"],
            location=japanese_event_data["location"],
            attendees=japanese_event_data["attendees"],
            timezone=japanese_event_data["timezone"]
        )

        # 日本語文字が正しく処理されているか確認
        assert result["summary"] == "勉強会：Python基礎"

        call_args = mock_calendar_service.events().insert.call_args
        body = call_args[1]["body"]
        assert "勉強会" in body["summary"]
        assert "議題" in body["description"]

    def test_update_event_success(
        self,
        calendar_client: GoogleCalendarClient,
        mock_calendar_service: Mock
    ) -> None:
        """イベント更新の成功テスト。"""
        event_id = "event123"
        updated_data = {
            "summary": "チームランチ（更新版）",
            "start_time": datetime(2024, 3, 15, 12, 30),
            "end_time": datetime(2024, 3, 15, 14, 0)
        }

        mock_calendar_service.events().update().execute.return_value = {
            "id": event_id,
            "summary": updated_data["summary"],
            "status": "confirmed"
        }

        result = calendar_client.update_event(
            event_id=event_id,
            summary=updated_data["summary"],
            start_time=updated_data["start_time"],
            end_time=updated_data["end_time"]
        )

        assert result["id"] == event_id
        assert result["summary"] == updated_data["summary"]

        mock_calendar_service.events().update.assert_called_once()

    def test_delete_event_success(
        self,
        calendar_client: GoogleCalendarClient,
        mock_calendar_service: Mock
    ) -> None:
        """イベント削除の成功テスト。"""
        event_id = "event123"

        mock_calendar_service.events().delete().execute.return_value = None

        result = calendar_client.delete_event(event_id)

        assert result is True
        mock_calendar_service.events().delete.assert_called_once_with(
            calendarId="primary",
            eventId=event_id
        )

    def test_get_event_success(
        self,
        calendar_client: GoogleCalendarClient,
        mock_calendar_service: Mock
    ) -> None:
        """イベント取得の成功テスト。"""
        event_id = "event123"

        mock_calendar_service.events().get().execute.return_value = {
            "id": event_id,
            "summary": "チームランチ",
            "start": {"dateTime": "2024-03-15T12:00:00+09:00"},
            "end": {"dateTime": "2024-03-15T13:30:00+09:00"},
            "status": "confirmed",
            "attendees": [
                {"email": "user1@example.com", "responseStatus": "accepted"},
                {"email": "user2@example.com", "responseStatus": "needsAction"}
            ]
        }

        result = calendar_client.get_event(event_id)

        assert result["id"] == event_id
        assert result["summary"] == "チームランチ"
        assert len(result["attendees"]) == 2

        mock_calendar_service.events().get.assert_called_once_with(
            calendarId="primary",
            eventId=event_id
        )

    def test_list_events_with_time_range(
        self,
        calendar_client: GoogleCalendarClient,
        mock_calendar_service: Mock
    ) -> None:
        """時間範囲指定でのイベント一覧取得テスト。"""
        start_date = datetime(2024, 3, 1)
        end_date = datetime(2024, 3, 31)

        mock_calendar_service.events().list().execute.return_value = {
            "items": [
                {
                    "id": "event1",
                    "summary": "イベント1",
                    "start": {"dateTime": "2024-03-15T12:00:00+09:00"}
                },
                {
                    "id": "event2",
                    "summary": "イベント2",
                    "start": {"dateTime": "2024-03-20T14:00:00+09:00"}
                }
            ]
        }

        result = calendar_client.list_events(
            start_date=start_date,
            end_date=end_date
        )

        assert len(result["items"]) == 2
        assert result["items"][0]["id"] == "event1"

        mock_calendar_service.events().list.assert_called_once()
        call_args = mock_calendar_service.events().list.call_args
        assert "timeMin" in call_args[1]
        assert "timeMax" in call_args[1]

    def test_add_attendees_to_event(
        self,
        calendar_client: GoogleCalendarClient,
        mock_calendar_service: Mock
    ) -> None:
        """イベントへの参加者追加テスト。"""
        event_id = "event123"
        new_attendees = [
            {"email": "user3@example.com", "display_name": "高橋三郎"},
            {"email": "user4@example.com", "display_name": "中村四郎"}
        ]

        # 既存イベント取得のモック
        mock_calendar_service.events().get().execute.return_value = {
            "id": event_id,
            "summary": "チームランチ",
            "attendees": [
                {"email": "user1@example.com", "responseStatus": "accepted"}
            ]
        }

        # 更新のモック
        mock_calendar_service.events().update().execute.return_value = {
            "id": event_id,
            "attendees": [
                {"email": "user1@example.com", "responseStatus": "accepted"},
                {"email": "user3@example.com", "responseStatus": "needsAction"},
                {"email": "user4@example.com", "responseStatus": "needsAction"}
            ]
        }

        result = calendar_client.add_attendees(event_id, new_attendees)

        assert len(result["attendees"]) == 3

        # get と update の両方が呼ばれることを確認
        mock_calendar_service.events().get.assert_called_once()
        mock_calendar_service.events().update.assert_called_once()

    def test_remove_attendees_from_event(
        self,
        calendar_client: GoogleCalendarClient,
        mock_calendar_service: Mock
    ) -> None:
        """イベントからの参加者削除テスト。"""
        event_id = "event123"
        remove_emails = ["user2@example.com"]

        # 既存イベント取得のモック
        mock_calendar_service.events().get().execute.return_value = {
            "id": event_id,
            "attendees": [
                {"email": "user1@example.com", "responseStatus": "accepted"},
                {"email": "user2@example.com", "responseStatus": "declined"}
            ]
        }

        # 更新のモック
        mock_calendar_service.events().update().execute.return_value = {
            "id": event_id,
            "attendees": [
                {"email": "user1@example.com", "responseStatus": "accepted"}
            ]
        }

        result = calendar_client.remove_attendees(event_id, remove_emails)

        assert len(result["attendees"]) == 1
        assert result["attendees"][0]["email"] == "user1@example.com"

    def test_api_error_handling(
        self,
        calendar_client: GoogleCalendarClient,
        mock_calendar_service: Mock
    ) -> None:
        """API エラーハンドリングテスト。"""
        from googleapiclient.errors import HttpError

        # 404エラーのモック
        mock_calendar_service.events().get().execute.side_effect = HttpError(
            resp=Mock(status=404),
            content=b'{"error": {"code": 404, "message": "Not Found"}}'
        )

        with pytest.raises(Exception) as exc_info:
            calendar_client.get_event("nonexistent_event")

        assert "404" in str(exc_info.value) or "Not Found" in str(exc_info.value)

    def test_rate_limiting_handling(
        self,
        calendar_client: GoogleCalendarClient,
        mock_calendar_service: Mock
    ) -> None:
        """レート制限ハンドリングテスト。"""
        from googleapiclient.errors import HttpError

        # 429エラー（Too Many Requests）のモック
        mock_calendar_service.events().list().execute.side_effect = HttpError(
            resp=Mock(status=429),
            content=b'{"error": {"code": 429, "message": "Rate Limit Exceeded"}}'
        )

        with pytest.raises(Exception) as exc_info:
            calendar_client.list_events()

        assert "429" in str(exc_info.value) or "Rate Limit" in str(exc_info.value)

    def test_timezone_handling(
        self,
        calendar_client: GoogleCalendarClient,
        mock_calendar_service: Mock
    ) -> None:
        """タイムゾーン処理テスト。"""
        event_data = {
            "summary": "グローバルミーティング",
            "start_time": datetime(2024, 3, 15, 9, 0),  # JST
            "end_time": datetime(2024, 3, 15, 10, 0),
            "timezone": "Asia/Tokyo"
        }

        mock_calendar_service.events().insert().execute.return_value = {
            "id": "tz_event123",
            "start": {"dateTime": "2024-03-15T09:00:00+09:00", "timeZone": "Asia/Tokyo"},
            "end": {"dateTime": "2024-03-15T10:00:00+09:00", "timeZone": "Asia/Tokyo"}
        }

        result = calendar_client.create_event(
            summary=event_data["summary"],
            start_time=event_data["start_time"],
            end_time=event_data["end_time"],
            timezone=event_data["timezone"]
        )

        call_args = mock_calendar_service.events().insert.call_args
        body = call_args[1]["body"]

        # タイムゾーン情報が正しく設定されているか確認
        assert body["start"]["timeZone"] == "Asia/Tokyo"
        assert body["end"]["timeZone"] == "Asia/Tokyo"

    def test_recurring_event_creation(
        self,
        calendar_client: GoogleCalendarClient,
        mock_calendar_service: Mock
    ) -> None:
        """繰り返しイベント作成テスト。"""
        recurrence_rule = "RRULE:FREQ=WEEKLY;BYDAY=FR;COUNT=4"

        mock_calendar_service.events().insert().execute.return_value = {
            "id": "recurring_event123",
            "summary": "毎週金曜日ランチ",
            "recurrence": [recurrence_rule],
            "status": "confirmed"
        }

        result = calendar_client.create_recurring_event(
            summary="毎週金曜日ランチ",
            start_time=datetime(2024, 3, 15, 12, 0),
            end_time=datetime(2024, 3, 15, 13, 0),
            recurrence_rule=recurrence_rule
        )

        assert result["id"] == "recurring_event123"
        assert recurrence_rule in result["recurrence"]

        call_args = mock_calendar_service.events().insert.call_args
        assert call_args[1]["body"]["recurrence"] == [recurrence_rule]

    def test_event_conflict_detection(
        self,
        calendar_client: GoogleCalendarClient,
        mock_calendar_service: Mock
    ) -> None:
        """イベント競合検出テスト。"""
        target_start = datetime(2024, 3, 15, 12, 0)
        target_end = datetime(2024, 3, 15, 13, 0)

        # 競合するイベントがある場合のモック
        mock_calendar_service.events().list().execute.return_value = {
            "items": [
                {
                    "id": "conflicting_event",
                    "summary": "既存ミーティング",
                    "start": {"dateTime": "2024-03-15T12:30:00+09:00"},
                    "end": {"dateTime": "2024-03-15T13:30:00+09:00"}
                }
            ]
        }

        conflicts = calendar_client.check_conflicts(
            start_time=target_start,
            end_time=target_end,
            attendee_emails=["user1@example.com"]
        )

        assert len(conflicts) > 0
        assert conflicts[0]["id"] == "conflicting_event"

    def test_calendar_permissions(
        self,
        calendar_client: GoogleCalendarClient,
        mock_calendar_service: Mock
    ) -> None:
        """カレンダー権限テスト。"""
        from googleapiclient.errors import HttpError

        # 403エラー（権限不足）のモック
        mock_calendar_service.events().insert().execute.side_effect = HttpError(
            resp=Mock(status=403),
            content=b'{"error": {"code": 403, "message": "Forbidden"}}'
        )

        with pytest.raises(Exception) as exc_info:
            calendar_client.create_event(
                summary="権限テストイベント",
                start_time=datetime(2024, 3, 15, 12, 0),
                end_time=datetime(2024, 3, 15, 13, 0)
            )

        assert "403" in str(exc_info.value) or "Forbidden" in str(exc_info.value)

    def test_event_data_validation(
        self,
        calendar_client: GoogleCalendarClient
    ) -> None:
        """イベントデータ検証テスト。"""
        # 無効なデータパターン
        invalid_cases = [
            # 終了時刻が開始時刻より前
            {
                "summary": "無効イベント",
                "start_time": datetime(2024, 3, 15, 14, 0),
                "end_time": datetime(2024, 3, 15, 12, 0)
            },
            # 空のサマリー
            {
                "summary": "",
                "start_time": datetime(2024, 3, 15, 12, 0),
                "end_time": datetime(2024, 3, 15, 13, 0)
            },
            # 無効なメールアドレス
            {
                "summary": "テストイベント",
                "start_time": datetime(2024, 3, 15, 12, 0),
                "end_time": datetime(2024, 3, 15, 13, 0),
                "attendees": [{"email": "invalid-email", "display_name": "無効ユーザー"}]
            }
        ]

        for invalid_data in invalid_cases:
            with pytest.raises((ValueError, Exception)):
                calendar_client.create_event(**invalid_data)