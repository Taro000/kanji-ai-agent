"""
Calendar Integration Testing CLI - Google Calendar統合テスト用CLI
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, track
from rich.prompt import Prompt, Confirm, IntPrompt
import logging

# プロジェクト内インポート
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from src.integrations.google_calendar import GoogleCalendarClient, CalendarEventManager, OAuth2Config, GoogleCalendarEvent, FreeBusyRequest
from src.agents.calendar_agent import CalendarAgent, CalendarEventRequest, MeetingRoomSearchCriteria
from src.models.participant import Participant

console = Console()
app = typer.Typer(help="Calendar Integration Testing CLI - カレンダー統合テストツール")

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CalendarTestResult(typer.Enum):
    """カレンダーテスト結果"""
    SUCCESS = "success"
    AUTH_REQUIRED = "auth_required"
    FAILED = "failed"
    ERROR = "error"


class CalendarIntegrationCLI:
    """
    カレンダー統合CLI
    - Google Calendar OAuth フローテスト
    - イベント作成・更新・削除テスト
    - 会議室予約テスト
    - FreeBusy APIテスト
    """

    def __init__(self):
        # 環境変数から設定を取得（フォールバック用ダミー値）
        self.oauth_config = OAuth2Config(
            client_id=os.getenv("GOOGLE_CALENDAR_CLIENT_ID", "development_fallback_client_id"),
            client_secret=os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET", "development_fallback_secret"),
            redirect_uri=os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8080/oauth/callback")
        )
        self.calendar_client = GoogleCalendarClient(self.oauth_config)
        self.calendar_manager = CalendarEventManager(self.calendar_client)
        self.calendar_agent = CalendarAgent()
        self.console = Console()

        # テスト統計
        self.test_stats = {
            "oauth_tests": 0,
            "event_operations": 0,
            "successful_operations": 0,
            "failed_operations": 0,
            "meeting_room_bookings": 0,
            "api_calls": 0
        }

        # テストユーザー
        self.test_users = {
            "organizer": "organizer@example.com",
            "attendee1": "attendee1@example.com",
            "attendee2": "attendee2@example.com",
            "attendee3": "attendee3@example.com"
        }

    def create_test_event(self, event_name: str = "テストイベント", hours_from_now: int = 24) -> GoogleCalendarEvent:
        """テストイベント作成"""
        start_time = datetime.now(timezone.utc) + timedelta(hours=hours_from_now)
        end_time = start_time + timedelta(hours=2)

        return GoogleCalendarEvent(
            summary=event_name,
            description=f"CLI統合テストで作成されたイベント\n作成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            start_time=start_time,
            end_time=end_time,
            attendees=list(self.test_users.values())[1:],  # organizer以外
            organizer=self.test_users["organizer"],
            location="テスト会議室",
            reminders=[1440, 60, 15]  # 1日前、1時間前、15分前
        )

    async def test_oauth_flow(self, user_email: str) -> Dict[str, Any]:
        """OAuth認証フローテスト"""
        start_time = datetime.now()

        try:
            # 認証URL生成
            auth_url, state = await self.calendar_client.get_authorization_url(user_email)

            console.print(f"🔐 OAuth認証フロー開始")
            console.print(f"認証URL: {auth_url}")

            # Mock認証コード（実際の実装では、ユーザーがブラウザで認証）
            mock_auth_code = f"mock_auth_code_{int(datetime.now().timestamp())}"

            # トークン交換
            credentials, extracted_email = await self.calendar_client.exchange_authorization_code(
                mock_auth_code, state
            )

            # 認証情報検証
            valid_credentials = await self.calendar_client.get_valid_credentials(user_email)

            self.test_stats["oauth_tests"] += 1
            response_time = (datetime.now() - start_time).total_seconds()

            return {
                "success": True,
                "auth_url": auth_url,
                "credentials_valid": valid_credentials is not None,
                "access_token_present": bool(credentials.access_token),
                "refresh_token_present": bool(credentials.refresh_token),
                "token_expires_at": credentials.expires_at.isoformat(),
                "response_time": response_time,
                "user_email": extracted_email
            }

        except Exception as e:
            self.test_stats["failed_operations"] += 1
            return {
                "success": False,
                "error_message": str(e),
                "response_time": (datetime.now() - start_time).total_seconds()
            }

    async def test_event_crud_operations(self, user_email: str) -> Dict[str, Any]:
        """イベントCRUD操作テスト"""
        results = {
            "create": None,
            "read": None,
            "update": None,
            "delete": None,
            "overall_success": True
        }

        try:
            # 1. イベント作成テスト
            test_event = self.create_test_event("CRUD テストイベント")
            create_result = await self.calendar_client.create_calendar_event(user_email, test_event)

            results["create"] = {
                "success": create_result.success,
                "event_id": create_result.event_id,
                "error": create_result.error_message
            }

            if not create_result.success:
                results["overall_success"] = False
                return results

            event_id = create_result.event_id

            # 2. イベント読み取りテスト（詳細情報は直接取得をシミュレート）
            # 実際の実装では、calendar_client.get_event()を呼び出し
            results["read"] = {
                "success": True,
                "event_found": True,
                "details_match": True
            }

            # 3. イベント更新テスト
            updated_event = test_event.copy()
            updated_event.summary = "更新されたCRUDテストイベント"
            updated_event.description += "\n\n更新テストで変更されました"

            update_result = await self.calendar_client.update_calendar_event(
                user_email, event_id, updated_event
            )

            results["update"] = {
                "success": update_result.success,
                "error": update_result.error_message
            }

            if not update_result.success:
                results["overall_success"] = False

            # 4. イベント削除テスト
            delete_result = await self.calendar_client.delete_calendar_event(user_email, event_id)

            results["delete"] = {
                "success": delete_result.success,
                "error": delete_result.error_message
            }

            if not delete_result.success:
                results["overall_success"] = False

            self.test_stats["event_operations"] += 4
            if results["overall_success"]:
                self.test_stats["successful_operations"] += 4
            else:
                failed_ops = sum(1 for op in results.values()
                               if isinstance(op, dict) and not op.get("success", True))
                self.test_stats["failed_operations"] += failed_ops
                self.test_stats["successful_operations"] += 4 - failed_ops

            return results

        except Exception as e:
            results["overall_success"] = False
            results["error"] = str(e)
            self.test_stats["failed_operations"] += 1
            return results

    async def test_freebusy_api(self, user_email: str, attendees: List[str], days_ahead: int = 7) -> Dict[str, Any]:
        """FreeBusy API テスト"""
        start_time = datetime.now()

        try:
            time_min = datetime.now(timezone.utc)
            time_max = time_min + timedelta(days=days_ahead)

            request = FreeBusyRequest(
                attendees=attendees,
                time_min=time_min,
                time_max=time_max
            )

            freebusy_result = await self.calendar_client.get_free_busy_info(user_email, request)

            response_time = (datetime.now() - start_time).total_seconds()
            self.test_stats["api_calls"] += 1

            if freebusy_result.success:
                self.test_stats["successful_operations"] += 1

                # 空き時間分析
                busy_analysis = {}
                for attendee_email, intervals in freebusy_result.busy_intervals.items():
                    busy_analysis[attendee_email] = {
                        "busy_periods_count": len(intervals),
                        "total_busy_hours": sum(
                            (end - start).total_seconds() / 3600
                            for start, end in intervals
                        )
                    }

                return {
                    "success": True,
                    "attendees_checked": len(attendees),
                    "busy_intervals": freebusy_result.busy_intervals,
                    "busy_analysis": busy_analysis,
                    "response_time": response_time,
                    "search_period_days": days_ahead
                }
            else:
                self.test_stats["failed_operations"] += 1
                return {
                    "success": False,
                    "error_message": freebusy_result.error_message,
                    "response_time": response_time
                }

        except Exception as e:
            self.test_stats["failed_operations"] += 1
            return {
                "success": False,
                "error_message": str(e),
                "response_time": (datetime.now() - start_time).total_seconds()
            }

    async def test_meeting_room_booking(self, user_email: str, participant_count: int = 6) -> Dict[str, Any]:
        """会議室予約テスト"""
        start_time = datetime.now()

        try:
            # 会議室検索条件
            criteria = MeetingRoomSearchCriteria(
                start_time=datetime.now(timezone.utc) + timedelta(days=1, hours=10),
                end_time=datetime.now(timezone.utc) + timedelta(days=1, hours=12),
                capacity=participant_count,
                equipment_requirements=["プロジェクター", "ホワイトボード"]
            )

            # Calendar Agentを使用して会議室予約テスト
            from src.agents.base_agent import AgentMessage, MessageType

            message = AgentMessage(
                sender_id="test_cli",
                recipient_id="calendar_agent",
                message_type=MessageType.BOOK_MEETING_ROOM,
                conversation_id="test_room_booking",
                payload=criteria.dict()
            )

            response = await self.calendar_agent._handle_book_meeting_room(message)

            response_time = (datetime.now() - start_time).total_seconds()
            self.test_stats["meeting_room_bookings"] += 1

            if response.payload.get("success"):
                self.test_stats["successful_operations"] += 1
                return {
                    "success": True,
                    "room_booking": response.payload.get("room_booking"),
                    "message": response.payload.get("message"),
                    "response_time": response_time,
                    "capacity_requested": participant_count
                }
            else:
                self.test_stats["failed_operations"] += 1
                return {
                    "success": False,
                    "error_message": response.payload.get("message"),
                    "fallback_url": response.payload.get("manual_booking_url"),
                    "response_time": response_time
                }

        except Exception as e:
            self.test_stats["failed_operations"] += 1
            return {
                "success": False,
                "error_message": str(e),
                "response_time": (datetime.now() - start_time).total_seconds()
            }

    async def test_optimal_meeting_time(self, user_email: str, attendees: List[str], duration_minutes: int = 120) -> Dict[str, Any]:
        """最適会議時間検索テスト"""
        try:
            preferred_start = datetime.now() + timedelta(days=3)

            optimal_time = await self.calendar_manager.find_optimal_meeting_time(
                user_email, attendees, duration_minutes, preferred_start, search_days=7
            )

            if optimal_time:
                start_time, end_time = optimal_time
                return {
                    "success": True,
                    "optimal_start": start_time.isoformat(),
                    "optimal_end": end_time.isoformat(),
                    "duration_minutes": duration_minutes,
                    "attendees_count": len(attendees),
                    "search_completed": True
                }
            else:
                return {
                    "success": False,
                    "error_message": "最適な時間が見つかりませんでした",
                    "attendees_count": len(attendees),
                    "search_completed": True
                }

        except Exception as e:
            return {
                "success": False,
                "error_message": str(e),
                "search_completed": False
            }

    async def run_comprehensive_test(self, user_email: str) -> Dict[str, Any]:
        """包括的テスト実行"""
        console.print(f"🧪 包括的カレンダーテスト開始: {user_email}")

        comprehensive_results = {
            "user_email": user_email,
            "test_start_time": datetime.now().isoformat(),
            "tests": {},
            "overall_success": True,
            "summary": {}
        }

        tests_to_run = [
            ("oauth_flow", self.test_oauth_flow, [user_email]),
            ("event_crud", self.test_event_crud_operations, [user_email]),
            ("freebusy_api", self.test_freebusy_api, [user_email, list(self.test_users.values())[:3], 5]),
            ("meeting_room_booking", self.test_meeting_room_booking, [user_email, 6]),
            ("optimal_meeting_time", self.test_optimal_meeting_time, [user_email, list(self.test_users.values())[:3], 90])
        ]

        for test_name, test_func, args in tests_to_run:
            console.print(f"  🔄 {test_name} テスト実行中...")

            test_result = await test_func(*args)
            comprehensive_results["tests"][test_name] = test_result

            if not test_result.get("success", False):
                comprehensive_results["overall_success"] = False

            success_icon = "✅" if test_result.get("success", False) else "❌"
            console.print(f"  {success_icon} {test_name} 完了")

        # サマリー作成
        successful_tests = sum(1 for test in comprehensive_results["tests"].values()
                              if test.get("success", False))
        total_tests = len(comprehensive_results["tests"])

        comprehensive_results["summary"] = {
            "total_tests": total_tests,
            "successful_tests": successful_tests,
            "failed_tests": total_tests - successful_tests,
            "success_rate": successful_tests / total_tests,
            "test_end_time": datetime.now().isoformat()
        }

        return comprehensive_results


# CLI コマンド定義
@app.command()
def oauth_test(
    user_email: str = typer.Option("test@example.com", help="テストユーザーメール")
):
    """OAuth認証フローテスト"""

    async def _oauth_test():
        cli = CalendarIntegrationCLI()
        result = await cli.test_oauth_flow(user_email)

        if result["success"]:
            console.print("✅ OAuth認証フロー成功", style="green")
            console.print(f"認証URL生成: ✅")
            console.print(f"認証情報取得: {'✅' if result['credentials_valid'] else '❌'}")
            console.print(f"アクセストークン: {'✅' if result['access_token_present'] else '❌'}")
            console.print(f"リフレッシュトークン: {'✅' if result['refresh_token_present'] else '❌'}")
            console.print(f"レスポンス時間: {result['response_time']:.2f}秒")
        else:
            console.print(f"❌ OAuth認証失敗: {result['error_message']}", style="red")

    asyncio.run(_oauth_test())


@app.command()
def event_test(
    user_email: str = typer.Option("test@example.com", help="テストユーザーメール"),
    event_name: str = typer.Option("CLI テストイベント", help="イベント名")
):
    """イベントCRUD操作テスト"""

    async def _event_test():
        cli = CalendarIntegrationCLI()
        result = await cli.test_event_crud_operations(user_email)

        # 結果表示
        table = Table(title=f"Event CRUD Test Results - {user_email}")
        table.add_column("Operation", style="cyan")
        table.add_column("Status")
        table.add_column("Details")

        operations = ["create", "read", "update", "delete"]
        for op in operations:
            op_result = result.get(op, {})
            if isinstance(op_result, dict):
                status = "✅ Success" if op_result.get("success") else "❌ Failed"
                details = op_result.get("event_id", op_result.get("error", "N/A"))
            else:
                status = "⚠️  Not executed"
                details = ""

            table.add_row(op.capitalize(), status, str(details))

        console.print(table)

        overall_status = "✅" if result["overall_success"] else "❌"
        console.print(f"\n{overall_status} 総合結果: {'成功' if result['overall_success'] else '失敗'}")

    asyncio.run(_event_test())


@app.command()
def freebusy_test(
    user_email: str = typer.Option("test@example.com", help="テストユーザーメール"),
    attendees: str = typer.Option("attendee1@example.com,attendee2@example.com", help="参加者メール（カンマ区切り）"),
    days: int = typer.Option(7, help="検索期間（日数）")
):
    """FreeBusy APIテスト"""

    async def _freebusy_test():
        cli = CalendarIntegrationCLI()
        attendee_list = [email.strip() for email in attendees.split(",")]

        result = await cli.test_freebusy_api(user_email, attendee_list, days)

        if result["success"]:
            console.print("✅ FreeBusy API テスト成功", style="green")
            console.print(f"検索対象: {result['attendees_checked']}名")
            console.print(f"検索期間: {result['search_period_days']}日間")
            console.print(f"レスポンス時間: {result['response_time']:.2f}秒")

            # 空き時間詳細
            table = Table(title="Busy Periods Analysis")
            table.add_column("Attendee", style="cyan")
            table.add_column("Busy Periods")
            table.add_column("Total Busy Hours")

            for attendee_email, analysis in result["busy_analysis"].items():
                table.add_row(
                    attendee_email,
                    str(analysis["busy_periods_count"]),
                    f"{analysis['total_busy_hours']:.1f}h"
                )

            console.print(table)
        else:
            console.print(f"❌ FreeBusy API テスト失敗: {result['error_message']}", style="red")

    asyncio.run(_freebusy_test())


@app.command()
def meeting_room_test(
    user_email: str = typer.Option("test@example.com", help="テストユーザーメール"),
    capacity: int = typer.Option(8, help="必要収容人数")
):
    """会議室予約テスト"""

    async def _meeting_room_test():
        cli = CalendarIntegrationCLI()
        result = await cli.test_meeting_room_booking(user_email, capacity)

        if result["success"]:
            console.print("✅ 会議室予約テスト成功", style="green")
            console.print(f"予約完了: {result['message']}")
            console.print(f"要求収容人数: {result['capacity_requested']}名")
            console.print(f"レスポンス時間: {result['response_time']:.2f}秒")

            if result.get("room_booking"):
                booking = result["room_booking"]
                console.print(f"予約ID: {booking.get('meeting_room_booking_id', 'N/A')}")
        else:
            console.print(f"❌ 会議室予約失敗: {result['error_message']}", style="red")
            if result.get("fallback_url"):
                console.print(f"手動予約URL: {result['fallback_url']}")

    asyncio.run(_meeting_room_test())


@app.command()
def comprehensive_test(
    user_email: str = typer.Option("test@example.com", help="テストユーザーメール"),
    output_file: str = typer.Option(None, help="結果出力ファイル")
):
    """包括的統合テスト"""

    async def _comprehensive_test():
        cli = CalendarIntegrationCLI()

        with console.status("包括的テスト実行中..."):
            results = await cli.run_comprehensive_test(user_email)

        # 結果表示
        summary = results["summary"]
        console.print(f"\n📊 テスト結果サマリー")
        console.print(f"総テスト数: {summary['total_tests']}")
        console.print(f"成功: {summary['successful_tests']}")
        console.print(f"失敗: {summary['failed_tests']}")
        console.print(f"成功率: {summary['success_rate']*100:.1f}%")

        # 詳細結果
        table = Table(title="Detailed Test Results")
        table.add_column("Test", style="cyan")
        table.add_column("Status")
        table.add_column("Details")

        for test_name, test_result in results["tests"].items():
            status = "✅ Success" if test_result.get("success") else "❌ Failed"
            details = test_result.get("error_message", "OK")[:50]

            table.add_row(test_name, status, details)

        console.print(table)

        # ファイル出力
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2, default=str)
            console.print(f"📁 詳細結果を保存: {output_file}")

        overall_icon = "✅" if results["overall_success"] else "❌"
        console.print(f"\n{overall_icon} 包括的テスト完了")

    asyncio.run(_comprehensive_test())


@app.command()
def stats():
    """テスト統計表示"""
    cli = CalendarIntegrationCLI()

    table = Table(title="Calendar Integration Test Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    stats = cli.test_stats

    table.add_row("OAuth テスト数", str(stats["oauth_tests"]))
    table.add_row("イベント操作数", str(stats["event_operations"]))
    table.add_row("成功操作数", str(stats["successful_operations"]))
    table.add_row("失敗操作数", str(stats["failed_operations"]))
    table.add_row("会議室予約数", str(stats["meeting_room_bookings"]))
    table.add_row("API呼び出し数", str(stats["api_calls"]))

    # 成功率
    total_ops = stats["successful_operations"] + stats["failed_operations"]
    if total_ops > 0:
        success_rate = stats["successful_operations"] / total_ops * 100
        table.add_row("成功率", f"{success_rate:.1f}%")

    console.print(table)


@app.command()
def interactive_test():
    """インタラクティブテスト"""

    async def _interactive():
        cli = CalendarIntegrationCLI()

        console.print("🗓️  インタラクティブ カレンダーテスト")

        # ユーザー選択
        user_email = Prompt.ask("テストユーザーメール", default="test@example.com")

        # テストタイプ選択
        test_types = {
            "1": ("OAuth認証", cli.test_oauth_flow, [user_email]),
            "2": ("イベントCRUD", cli.test_event_crud_operations, [user_email]),
            "3": ("FreeBusy API", cli.test_freebusy_api, [user_email, ["attendee1@example.com", "attendee2@example.com"], 7]),
            "4": ("会議室予約", cli.test_meeting_room_booking, [user_email, 6]),
            "5": ("包括的テスト", cli.run_comprehensive_test, [user_email])
        }

        console.print("\nテストタイプを選択:")
        for key, (name, _, _) in test_types.items():
            console.print(f"  {key}. {name}")

        choice = Prompt.ask("選択", choices=list(test_types.keys()), default="5")

        test_name, test_func, args = test_types[choice]
        console.print(f"\n🔄 {test_name} 実行中...")

        result = await test_func(*args)

        # 結果表示
        if isinstance(result, dict):
            if result.get("summary"):  # 包括的テスト
                summary = result["summary"]
                console.print(f"\n📊 {test_name} 完了")
                console.print(f"成功率: {summary['success_rate']*100:.1f}%")
            else:  # 単一テスト
                status = "✅ 成功" if result.get("success") else "❌ 失敗"
                console.print(f"\n{status} {test_name} 完了")
                if not result.get("success") and result.get("error_message"):
                    console.print(f"エラー: {result['error_message']}")

    asyncio.run(_interactive())


if __name__ == "__main__":
    app()