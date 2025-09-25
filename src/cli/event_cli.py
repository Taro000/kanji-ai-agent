"""
Event Coordination CLI - イベント作成・管理テスト用CLI
"""

import asyncio
import json
import yaml
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
import logging

# プロジェクト内インポート
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from src.agents.coordination_agent import CoordinationAgent
from src.agents.participant_agent import ParticipantAgent
from src.agents.scheduling_agent import SchedulingAgent
from src.agents.venue_agent import VenueAgent
from src.agents.calendar_agent import CalendarAgent
from src.models.event import Event, EventType, EventStatus
from src.models.participant import Participant, ParticipationStatus
from src.integrations.firestore_client import FirestoreClient, FirestoreConfig

console = Console()
app = typer.Typer(help="Event Coordination CLI - イベント管理テストツール")

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EventCoordinationCLI:
    """
    イベント調整CLI
    - イベント作成・管理
    - エージェント間連携テスト
    - ワークフロー実行・モニタリング
    """

    def __init__(self):
        self.agents = {}
        self.firestore_client = None
        self.test_session_id = None
        self.console = Console()

    async def initialize_agents(self):
        """エージェント初期化"""
        try:
            # Firestore初期化
            config = FirestoreConfig(
                project_id="test-project",
                emulator_host="localhost:8080"  # 開発環境用
            )
            self.firestore_client = FirestoreClient(config)
            await self.firestore_client.connect()

            # エージェント初期化
            self.agents = {
                'coordination': CoordinationAgent(),
                'participant': ParticipantAgent(),
                'scheduling': SchedulingAgent(),
                'venue': VenueAgent(),
                'calendar': CalendarAgent()
            }

            console.print("✅ エージェント初期化完了", style="green")

        except Exception as e:
            console.print(f"❌ 初期化エラー: {str(e)}", style="red")
            raise

    def create_mock_event(self, event_type: str, title: str, participant_count: int = 5) -> Event:
        """Mockイベント作成"""
        event_id = f"test_event_{int(datetime.now().timestamp())}"

        # 参加者リスト生成
        participants = []
        for i in range(participant_count):
            participant = Participant(
                participant_id=f"user_{i}",
                name=f"テストユーザー{i+1}",
                email=f"user{i}@example.com",
                slack_user_id=f"U{1000+i}",
                status=ParticipationStatus.INVITED
            )
            participants.append(participant)

        event = Event(
            event_id=event_id,
            title=title,
            event_type=EventType(event_type),
            organizer_id="organizer_test",
            participants=participants,
            status=EventStatus.PLANNING,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        return event

    async def run_event_workflow(self, event: Event) -> Dict[str, Any]:
        """イベントワークフロー実行"""
        results = {
            "event_id": event.event_id,
            "phases": {},
            "success": True,
            "errors": []
        }

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:

                # Phase 1: 参加者確認
                task = progress.add_task("参加者確認フェーズ実行中...", total=None)
                participant_result = await self._run_participant_phase(event)
                results["phases"]["participant"] = participant_result
                progress.remove_task(task)

                if not participant_result["success"]:
                    results["success"] = False
                    results["errors"].extend(participant_result.get("errors", []))
                    return results

                # Phase 2: スケジュール調整
                task = progress.add_task("スケジュール調整フェーズ実行中...", total=None)
                scheduling_result = await self._run_scheduling_phase(event)
                results["phases"]["scheduling"] = scheduling_result
                progress.remove_task(task)

                # Phase 3: 会場検索
                task = progress.add_task("会場検索フェーズ実行中...", total=None)
                venue_result = await self._run_venue_phase(event)
                results["phases"]["venue"] = venue_result
                progress.remove_task(task)

                # Phase 4: カレンダー統合
                task = progress.add_task("カレンダー統合フェーズ実行中...", total=None)
                calendar_result = await self._run_calendar_phase(event)
                results["phases"]["calendar"] = calendar_result
                progress.remove_task(task)

        except Exception as e:
            results["success"] = False
            results["errors"].append(str(e))
            logger.error(f"ワークフロー実行エラー: {str(e)}")

        return results

    async def _run_participant_phase(self, event: Event) -> Dict[str, Any]:
        """参加者確認フェーズ"""
        try:
            # Mock参加者確認
            confirmed_count = 0
            for participant in event.participants:
                # 80%の確率で参加確認
                import random
                if random.random() < 0.8:
                    participant.status = ParticipationStatus.CONFIRMED
                    confirmed_count += 1
                else:
                    participant.status = ParticipationStatus.DECLINED

            return {
                "success": True,
                "confirmed_participants": confirmed_count,
                "total_participants": len(event.participants),
                "confirmation_rate": confirmed_count / len(event.participants)
            }

        except Exception as e:
            return {
                "success": False,
                "errors": [str(e)]
            }

    async def _run_scheduling_phase(self, event: Event) -> Dict[str, Any]:
        """スケジュール調整フェーズ"""
        try:
            # Mock時間候補生成
            schedule_options = [
                {
                    "start_time": datetime.now() + timedelta(days=7, hours=18),
                    "end_time": datetime.now() + timedelta(days=7, hours=20),
                    "suitability_score": 0.85
                },
                {
                    "start_time": datetime.now() + timedelta(days=8, hours=19),
                    "end_time": datetime.now() + timedelta(days=8, hours=21),
                    "suitability_score": 0.75
                }
            ]

            # 最適候補選択
            best_option = max(schedule_options, key=lambda x: x["suitability_score"])

            return {
                "success": True,
                "schedule_options": schedule_options,
                "selected_schedule": best_option,
                "optimization_score": best_option["suitability_score"]
            }

        except Exception as e:
            return {
                "success": False,
                "errors": [str(e)]
            }

    async def _run_venue_phase(self, event: Event) -> Dict[str, Any]:
        """会場検索フェーズ"""
        try:
            # Mock会場検索結果
            venue_options = [
                {
                    "name": "居酒屋 さくら",
                    "address": "東京都渋谷区渋谷1-1-1",
                    "rating": 4.2,
                    "price_range": "3000-4000円",
                    "match_score": 0.88
                },
                {
                    "name": "イタリアン ベラビスタ",
                    "address": "東京都渋谷区渋谷1-2-3",
                    "rating": 4.5,
                    "price_range": "4000-5000円",
                    "match_score": 0.82
                }
            ]

            best_venue = max(venue_options, key=lambda x: x["match_score"])

            return {
                "success": True,
                "venue_options": venue_options,
                "selected_venue": best_venue,
                "search_apis_used": ["Google Places", "ぐるなび"]
            }

        except Exception as e:
            return {
                "success": False,
                "errors": [str(e)]
            }

    async def _run_calendar_phase(self, event: Event) -> Dict[str, Any]:
        """カレンダー統合フェーズ"""
        try:
            # Mock カレンダー作成
            calendar_event = {
                "google_event_id": f"google_event_{int(datetime.now().timestamp())}",
                "calendar_url": "https://calendar.google.com/event?eid=mock_event_id",
                "invitations_sent": len(event.participants),
                "reminders_set": ["1日前", "1時間前", "15分前"]
            }

            return {
                "success": True,
                "calendar_event": calendar_event,
                "oauth_required": False
            }

        except Exception as e:
            return {
                "success": False,
                "errors": [str(e)]
            }


# CLI コマンド定義
@app.command()
def init():
    """CLI環境初期化"""
    cli = EventCoordinationCLI()

    async def _init():
        await cli.initialize_agents()

    asyncio.run(_init())


@app.command()
def create_event(
    event_type: str = typer.Argument(..., help="イベントタイプ (dining/meeting/study)"),
    title: str = typer.Option("テストイベント", help="イベントタイトル"),
    participants: int = typer.Option(5, help="参加者数"),
    output_file: Optional[str] = typer.Option(None, help="結果出力ファイル")
):
    """イベント作成・実行"""

    async def _create_event():
        cli = EventCoordinationCLI()
        await cli.initialize_agents()

        # イベント作成
        event = cli.create_mock_event(event_type, title, participants)

        console.print(Panel.fit(
            f"🎉 イベント作成\n\n"
            f"ID: {event.event_id}\n"
            f"タイトル: {event.title}\n"
            f"タイプ: {event.event_type.value}\n"
            f"参加者数: {len(event.participants)}",
            title="Event Created"
        ))

        # ワークフロー実行
        with console.status("イベントワークフロー実行中..."):
            results = await cli.run_event_workflow(event)

        # 結果表示
        _display_results(results)

        # ファイル出力
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2, default=str)
            console.print(f"📁 結果を {output_file} に保存しました", style="green")

    asyncio.run(_create_event())


@app.command()
def batch_test(
    config_file: str = typer.Argument(..., help="テスト設定ファイル (YAML)"),
    output_dir: str = typer.Option("./test_results", help="結果出力ディレクトリ")
):
    """バッチテスト実行"""

    async def _batch_test():
        # 設定ファイル読み込み
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        cli = EventCoordinationCLI()
        await cli.initialize_agents()

        # 出力ディレクトリ作成
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # テストケース実行
        all_results = []

        for test_case in config.get('test_cases', []):
            console.print(f"\n🧪 テストケース: {test_case.get('name', 'Unnamed')}")

            event = cli.create_mock_event(
                test_case['event_type'],
                test_case.get('title', 'Batch Test Event'),
                test_case.get('participant_count', 5)
            )

            results = await cli.run_event_workflow(event)
            results['test_case_name'] = test_case.get('name')
            all_results.append(results)

            # 個別結果保存
            output_file = Path(output_dir) / f"{test_case.get('name', 'test')}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2, default=str)

        # 統合結果表示・保存
        _display_batch_summary(all_results)

        summary_file = Path(output_dir) / "batch_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)

        console.print(f"📊 バッチテスト完了。結果: {output_dir}/", style="green")

    asyncio.run(_batch_test())


@app.command()
def status():
    """システム状態確認"""

    async def _status():
        cli = EventCoordinationCLI()
        await cli.initialize_agents()

        table = Table(title="System Status")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Details")

        # エージェント状態
        for name, agent in cli.agents.items():
            table.add_row(
                f"{name.capitalize()} Agent",
                "✅ Active",
                f"ID: {agent.agent_id}"
            )

        # Firestore状態
        if cli.firestore_client:
            stats = cli.firestore_client.get_stats()
            table.add_row(
                "Firestore",
                "✅ Connected",
                f"Reads: {stats['reads']}, Writes: {stats['writes']}"
            )

        console.print(table)

    asyncio.run(_status())


def _display_results(results: Dict[str, Any]):
    """結果表示"""
    # 成功/失敗ステータス
    status_style = "green" if results["success"] else "red"
    status_icon = "✅" if results["success"] else "❌"

    console.print(f"\n{status_icon} ワークフロー完了", style=status_style)

    # フェーズ別結果
    table = Table(title="Phase Results")
    table.add_column("Phase", style="cyan")
    table.add_column("Status")
    table.add_column("Details")

    for phase_name, phase_result in results["phases"].items():
        status = "✅ Success" if phase_result.get("success") else "❌ Failed"

        details = ""
        if phase_name == "participant":
            details = f"{phase_result.get('confirmed_participants', 0)}/{phase_result.get('total_participants', 0)} 確認"
        elif phase_name == "scheduling":
            details = f"適合度: {phase_result.get('optimization_score', 0):.2f}"
        elif phase_name == "venue":
            details = f"{len(phase_result.get('venue_options', []))} 件候補"
        elif phase_name == "calendar":
            details = f"{phase_result.get('invitations_sent', 0)} 件招待送信"

        table.add_row(phase_name.capitalize(), status, details)

    console.print(table)

    # エラー表示
    if results.get("errors"):
        console.print("\n❌ エラー:", style="red")
        for error in results["errors"]:
            console.print(f"  • {error}", style="red")


def _display_batch_summary(all_results: List[Dict[str, Any]]):
    """バッチテスト要約表示"""
    total_tests = len(all_results)
    successful_tests = sum(1 for r in all_results if r["success"])

    console.print(f"\n📊 バッチテスト要約")
    console.print(f"総テスト数: {total_tests}")
    console.print(f"成功: {successful_tests}")
    console.print(f"失敗: {total_tests - successful_tests}")
    console.print(f"成功率: {successful_tests/total_tests*100:.1f}%")

    # 詳細テーブル
    table = Table(title="Test Case Results")
    table.add_column("Test Case", style="cyan")
    table.add_column("Status")
    table.add_column("Phases")

    for result in all_results:
        test_name = result.get('test_case_name', 'Unnamed')
        status = "✅" if result["success"] else "❌"

        phase_status = []
        for phase, phase_result in result["phases"].items():
            phase_icon = "✅" if phase_result.get("success") else "❌"
            phase_status.append(f"{phase_icon} {phase}")

        table.add_row(test_name, status, " | ".join(phase_status))

    console.print(table)


if __name__ == "__main__":
    app()