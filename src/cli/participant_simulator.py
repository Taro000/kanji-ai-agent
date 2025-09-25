"""
Participant Simulator CLI - 参加者レスポンス シミュレーション
"""

import asyncio
import json
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, track
from rich.prompt import Prompt, Confirm
import logging

# プロジェクト内インポート
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from src.models.participant import Participant, ParticipationStatus, AvailabilityWindow
from src.integrations.slack_handler import SlackEventHandler, SlackMessageSender, DMWorkflowState

console = Console()
app = typer.Typer(help="Participant Simulator CLI - 参加者シミュレーションツール")

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ParticipantPersonality(typer.Enum):
    """参加者性格タイプ"""
    ENTHUSIASTIC = "enthusiastic"    # 積極的
    CAUTIOUS = "cautious"            # 慎重
    BUSY = "busy"                    # 多忙
    FLEXIBLE = "flexible"            # 柔軟
    DIFFICULT = "difficult"          # 難しい


class JapaneseResponsePatterns:
    """日本語応答パターン"""

    def __init__(self):
        self.positive_responses = {
            ParticipantPersonality.ENTHUSIASTIC: [
                "はい！ぜひ参加させていただきます！",
                "楽しそうですね！参加します！",
                "いいですね〜！参加したいです！",
                "参加します！よろしくお願いします！"
            ],
            ParticipantPersonality.FLEXIBLE: [
                "はい、参加します。",
                "大丈夫です、参加できます。",
                "参加させていただきます。",
                "はい、お時間空いてます。"
            ],
            ParticipantPersonality.CAUTIOUS: [
                "詳細を確認してから参加させていただきます。",
                "スケジュール調整して参加します。",
                "参加方向で検討します。",
                "都合がつけば参加します。"
            ]
        }

        self.negative_responses = {
            ParticipantPersonality.BUSY: [
                "申し訳ございません、その日は予定があります。",
                "すみません、都合がつきません。",
                "残念ですが参加できません。",
                "先約があるため参加できません。"
            ],
            ParticipantPersonality.DIFFICULT: [
                "うーん、ちょっと厳しいかもしれません。",
                "その日は微妙です...",
                "別の日だったら考えます。",
                "時間を変更できませんか？"
            ]
        }

        self.schedule_preferences = [
            "18:00以降でお願いします",
            "19:00頃が希望です",
            "金曜日の夜が良いです",
            "週末はいかがでしょうか？",
            "平日の夕方以降であれば",
            "お昼の時間帯でも大丈夫です",
            "遅い時間でも構いません"
        ]

        self.venue_preferences = [
            "居酒屋が良いです",
            "イタリアンはいかがですか？",
            "駅近くが希望です",
            "個室があると嬉しいです",
            "予算3000円程度で",
            "飲み放題がある所が良いです",
            "静かな場所が良いです"
        ]


class ParticipantSimulatorCLI:
    """
    参加者シミュレーターCLI
    - 参加者応答パターンシミュレーション
    - 日本語自然言語理解テスト
    - バルク参加者生成
    """

    def __init__(self):
        self.participants: List[Participant] = []
        self.response_patterns = JapaneseResponsePatterns()
        self.slack_handler = SlackEventHandler("mock_token", "mock_secret")
        self.console = Console()
        self.simulation_stats = {
            "total_responses": 0,
            "positive_responses": 0,
            "negative_responses": 0,
            "pattern_matches": 0
        }

    def generate_mock_participants(self, count: int = 10) -> List[Participant]:
        """Mock参加者生成"""
        participants = []
        personalities = list(ParticipantPersonality)

        for i in range(count):
            personality = random.choice(personalities)

            participant = Participant(
                participant_id=f"sim_user_{i:03d}",
                name=f"シミュユーザー{i+1}",
                email=f"sim.user{i}@example.com",
                slack_user_id=f"U{2000+i:04d}",
                status=ParticipationStatus.INVITED,
                availability_windows=[
                    AvailabilityWindow(
                        start_time=datetime.now() + timedelta(days=random.randint(1, 7), hours=random.randint(17, 20)),
                        end_time=datetime.now() + timedelta(days=random.randint(1, 7), hours=random.randint(21, 23)),
                        preference_score=random.uniform(0.3, 1.0)
                    ) for _ in range(random.randint(2, 5))
                ],
                dietary_restrictions=random.choice([[], ["ベジタリアン"], ["アレルギー:そば"], ["お酒飲めません"]]),
                notes=f"性格タイプ: {personality.value}"
            )

            participants.append(participant)

        return participants

    def simulate_response_to_invitation(self, participant: Participant, event_info: Dict[str, Any]) -> Tuple[str, ParticipationStatus]:
        """招待への応答シミュレーション"""
        # 性格タイプ判定
        personality_str = participant.notes.split(": ")[1] if ": " in participant.notes else "flexible"
        personality = ParticipantPersonality(personality_str)

        # 応答決定
        response_chance = {
            ParticipantPersonality.ENTHUSIASTIC: 0.9,
            ParticipantPersonality.FLEXIBLE: 0.75,
            ParticipantPersonality.CAUTIOUS: 0.6,
            ParticipantPersonality.BUSY: 0.3,
            ParticipantPersonality.DIFFICULT: 0.4
        }

        will_participate = random.random() < response_chance[personality]

        # 応答文生成
        if will_participate:
            response_text = random.choice(self.response_patterns.positive_responses.get(
                personality, self.response_patterns.positive_responses[ParticipantPersonality.FLEXIBLE]
            ))
            status = ParticipationStatus.CONFIRMED
        else:
            response_text = random.choice(self.response_patterns.negative_responses.get(
                personality, self.response_patterns.negative_responses[ParticipantPersonality.BUSY]
            ))
            status = ParticipationStatus.DECLINED

        # 追加コメント（50%の確率）
        if random.random() < 0.5:
            if will_participate and event_info.get("event_type") == "dining":
                additional_comment = random.choice(self.response_patterns.venue_preferences)
                response_text += f"\n\n{additional_comment}"
            elif will_participate:
                additional_comment = random.choice(self.response_patterns.schedule_preferences)
                response_text += f"\n\n{additional_comment}"

        return response_text, status

    def simulate_dm_conversation(self, participant: Participant, workflow_steps: List[str]) -> List[Dict[str, Any]]:
        """DM会話シミュレーション"""
        conversation = []
        personality_str = participant.notes.split(": ")[1] if ": " in participant.notes else "flexible"
        personality = ParticipantPersonality(personality_str)

        for step in workflow_steps:
            if step == "event_type_confirmation":
                responses = {
                    ParticipantPersonality.ENTHUSIASTIC: ["はい！楽しそうです！", "ぜひやりましょう！"],
                    ParticipantPersonality.FLEXIBLE: ["はい、大丈夫です", "いいですね"],
                    ParticipantPersonality.CAUTIOUS: ["詳細を教えてください", "どのような感じでしょうか？"],
                    ParticipantPersonality.BUSY: ["時間次第です", "短時間であれば..."],
                    ParticipantPersonality.DIFFICULT: ["うーん、どうでしょう", "他の案はありますか？"]
                }
                response = random.choice(responses.get(personality, responses[ParticipantPersonality.FLEXIBLE]))

            elif step == "schedule_preference":
                base_response = random.choice(self.response_patterns.schedule_preferences)
                if personality == ParticipantPersonality.DIFFICULT:
                    response = f"{base_response}\n\nでも、他の選択肢もありますか？"
                elif personality == ParticipantPersonality.BUSY:
                    response = f"{base_response}\n\n短時間でお願いします。"
                else:
                    response = base_response

            elif step == "venue_preference":
                base_response = random.choice(self.response_patterns.venue_preferences)
                if personality == ParticipantPersonality.CAUTIOUS:
                    response = f"{base_response}\n\n事前に予約は取れますか？"
                else:
                    response = base_response

            else:
                response = "はい、わかりました。"

            conversation.append({
                "step": step,
                "user_response": response,
                "timestamp": datetime.now().isoformat(),
                "personality": personality.value
            })

        return conversation

    async def test_response_pattern_recognition(self, test_responses: List[str]) -> Dict[str, Any]:
        """応答パターン認識テスト"""
        results = {
            "total_tests": len(test_responses),
            "successful_recognitions": 0,
            "pattern_analysis": [],
            "accuracy": 0.0
        }

        for i, response_text in enumerate(test_responses):
            # SlackEventDataの模擬作成
            from src.integrations.slack_handler import SlackEventData

            mock_event = SlackEventData(
                event_type="message",
                user_id=f"test_user_{i}",
                channel_id="D1234567",
                text=response_text,
                timestamp=str(int(datetime.now().timestamp())),
                team_id="T1234567"
            )

            # パターン認識テスト
            try:
                # 参加意思検出
                is_positive = any(pattern in response_text for pattern in [
                    "はい", "参加", "大丈夫", "いい", "ok", "します"
                ])
                is_negative = any(pattern in response_text for pattern in [
                    "いいえ", "無理", "だめ", "できません", "すみません", "申し訳"
                ])

                recognition_success = is_positive or is_negative
                if recognition_success:
                    results["successful_recognitions"] += 1

                results["pattern_analysis"].append({
                    "response": response_text,
                    "detected_positive": is_positive,
                    "detected_negative": is_negative,
                    "recognition_success": recognition_success
                })

            except Exception as e:
                logger.error(f"パターン認識エラー: {str(e)}")
                results["pattern_analysis"].append({
                    "response": response_text,
                    "error": str(e),
                    "recognition_success": False
                })

        results["accuracy"] = results["successful_recognizations"] / results["total_tests"]
        return results

    def analyze_response_diversity(self, responses: List[str]) -> Dict[str, Any]:
        """応答多様性分析"""
        # 単語頻度分析
        word_count = {}
        total_words = 0

        for response in responses:
            words = response.replace("。", "").replace("、", "").replace("！", "").split()
            for word in words:
                word_count[word] = word_count.get(word, 0) + 1
                total_words += 1

        # 多様性指標計算
        unique_words = len(word_count)
        avg_words_per_response = total_words / len(responses)

        # 頻出単語
        common_words = sorted(word_count.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "total_responses": len(responses),
            "unique_words": unique_words,
            "total_words": total_words,
            "avg_words_per_response": avg_words_per_response,
            "diversity_ratio": unique_words / total_words if total_words > 0 else 0,
            "common_words": common_words
        }


# CLI コマンド定義
@app.command()
def generate_participants(
    count: int = typer.Option(10, help="生成する参加者数"),
    output_file: str = typer.Option("participants.json", help="出力ファイル")
):
    """参加者データ生成"""
    simulator = ParticipantSimulatorCLI()
    participants = simulator.generate_mock_participants(count)

    # JSON出力用にシリアライズ
    participants_data = []
    for p in participants:
        participant_dict = p.dict()
        participant_dict['created_at'] = participant_dict['created_at'].isoformat()
        participant_dict['updated_at'] = participant_dict['updated_at'].isoformat()

        # AvailabilityWindow を辞書に変換
        availability_windows = []
        for window in participant_dict['availability_windows']:
            window_dict = {
                'start_time': window['start_time'].isoformat(),
                'end_time': window['end_time'].isoformat(),
                'preference_score': window['preference_score']
            }
            availability_windows.append(window_dict)
        participant_dict['availability_windows'] = availability_windows

        participants_data.append(participant_dict)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(participants_data, f, ensure_ascii=False, indent=2)

    console.print(f"✅ {count}人の参加者データを生成: {output_file}", style="green")

    # 性格分布表示
    personality_count = {}
    for p in participants:
        personality = p.notes.split(": ")[1] if ": " in p.notes else "unknown"
        personality_count[personality] = personality_count.get(personality, 0) + 1

    table = Table(title="Personality Distribution")
    table.add_column("Personality", style="cyan")
    table.add_column("Count", style="green")

    for personality, count in personality_count.items():
        table.add_row(personality, str(count))

    console.print(table)


@app.command()
def simulate_invitation_responses(
    participants_file: str = typer.Argument(..., help="参加者データファイル"),
    event_type: str = typer.Option("dining", help="イベントタイプ"),
    output_file: str = typer.Option("responses.json", help="応答結果ファイル")
):
    """招待応答シミュレーション"""
    simulator = ParticipantSimulatorCLI()

    # 参加者データ読み込み
    with open(participants_file, 'r', encoding='utf-8') as f:
        participants_data = json.load(f)

    participants = []
    for data in participants_data:
        # datetime変換
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['updated_at'] = datetime.fromisoformat(data['updated_at'])

        # AvailabilityWindow変換
        availability_windows = []
        for window_data in data['availability_windows']:
            window = AvailabilityWindow(
                start_time=datetime.fromisoformat(window_data['start_time']),
                end_time=datetime.fromisoformat(window_data['end_time']),
                preference_score=window_data['preference_score']
            )
            availability_windows.append(window)
        data['availability_windows'] = availability_windows

        participant = Participant(**data)
        participants.append(participant)

    # イベント情報
    event_info = {
        "event_type": event_type,
        "title": "テストイベント",
        "description": "シミュレーション用のテストイベントです"
    }

    # 応答シミュレーション実行
    responses = []
    with Progress() as progress:
        task = progress.add_task("招待応答シミュレーション実行中...", total=len(participants))

        for participant in participants:
            response_text, status = simulator.simulate_response_to_invitation(participant, event_info)

            response_data = {
                "participant_id": participant.participant_id,
                "participant_name": participant.name,
                "response_text": response_text,
                "participation_status": status.value,
                "personality": participant.notes.split(": ")[1] if ": " in participant.notes else "unknown",
                "timestamp": datetime.now().isoformat()
            }

            responses.append(response_data)
            progress.advance(task)

    # 結果保存
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(responses, f, ensure_ascii=False, indent=2)

    # 統計表示
    positive_count = sum(1 for r in responses if r["participation_status"] == "confirmed")
    negative_count = len(responses) - positive_count

    console.print(f"\n📊 シミュレーション結果")
    console.print(f"総参加者: {len(responses)}")
    console.print(f"参加確定: {positive_count} ({positive_count/len(responses)*100:.1f}%)")
    console.print(f"参加辞退: {negative_count} ({negative_count/len(responses)*100:.1f}%)")

    # 性格別統計
    personality_stats = {}
    for response in responses:
        personality = response["personality"]
        if personality not in personality_stats:
            personality_stats[personality] = {"confirmed": 0, "declined": 0}

        if response["participation_status"] == "confirmed":
            personality_stats[personality]["confirmed"] += 1
        else:
            personality_stats[personality]["declined"] += 1

    table = Table(title="Personality-based Response Statistics")
    table.add_column("Personality", style="cyan")
    table.add_column("Confirmed", style="green")
    table.add_column("Declined", style="red")
    table.add_column("Rate", style="yellow")

    for personality, stats in personality_stats.items():
        total = stats["confirmed"] + stats["declined"]
        rate = stats["confirmed"] / total if total > 0 else 0
        table.add_row(
            personality,
            str(stats["confirmed"]),
            str(stats["declined"]),
            f"{rate*100:.1f}%"
        )

    console.print(table)

    console.print(f"✅ 応答データを保存: {output_file}", style="green")


@app.command()
def test_response_recognition(
    test_file: str = typer.Option(None, help="テスト応答ファイル"),
    interactive: bool = typer.Option(False, help="インタラクティブテスト")
):
    """応答パターン認識テスト"""
    simulator = ParticipantSimulatorCLI()

    if interactive:
        # インタラクティブモード
        test_responses = []
        console.print("📝 応答パターン認識テスト（Ctrl+Cで終了）")

        try:
            while True:
                response = Prompt.ask("テスト応答を入力してください")
                if response.strip():
                    test_responses.append(response)
                    console.print(f"✅ 追加: {response}")

                if not Confirm.ask("続けますか？", default=True):
                    break

        except KeyboardInterrupt:
            console.print("\n⚡ テスト終了")

    else:
        # ファイルからテスト応答読み込み
        if test_file and Path(test_file).exists():
            with open(test_file, 'r', encoding='utf-8') as f:
                test_data = json.load(f)
                test_responses = [item["response_text"] for item in test_data]
        else:
            # デフォルトテスト応答
            test_responses = [
                "はい！ぜひ参加させていただきます！",
                "申し訳ございません、その日は予定があります。",
                "うーん、ちょっと厳しいかもしれません。",
                "大丈夫です、参加できます。",
                "すみません、都合がつきません。",
                "詳細を確認してから参加させていただきます。",
                "18:00以降でお願いします",
                "居酒屋が良いです",
                "個室があると嬉しいです"
            ]

    # パターン認識テスト実行
    async def _test():
        results = await simulator.test_response_pattern_recognition(test_responses)
        return results

    results = asyncio.run(_test())

    # 結果表示
    console.print(f"\n🔍 パターン認識テスト結果")
    console.print(f"総テスト数: {results['total_tests']}")
    console.print(f"成功認識数: {results['successful_recognitions']}")
    console.print(f"認識精度: {results['accuracy']*100:.1f}%")

    # 詳細結果表示
    table = Table(title="Recognition Details")
    table.add_column("Response", style="cyan", max_width=40)
    table.add_column("Positive", style="green")
    table.add_column("Negative", style="red")
    table.add_column("Success", style="yellow")

    for analysis in results["pattern_analysis"]:
        success_icon = "✅" if analysis.get("recognition_success") else "❌"
        table.add_row(
            analysis["response"][:40] + "..." if len(analysis["response"]) > 40 else analysis["response"],
            "✅" if analysis.get("detected_positive") else "",
            "✅" if analysis.get("detected_negative") else "",
            success_icon
        )

    console.print(table)


@app.command()
def analyze_diversity(
    responses_file: str = typer.Argument(..., help="応答データファイル")
):
    """応答多様性分析"""
    simulator = ParticipantSimulatorCLI()

    with open(responses_file, 'r', encoding='utf-8') as f:
        responses_data = json.load(f)

    response_texts = [item["response_text"] for item in responses_data]
    analysis = simulator.analyze_response_diversity(response_texts)

    console.print(f"\n📈 応答多様性分析")
    console.print(f"総応答数: {analysis['total_responses']}")
    console.print(f"ユニーク単語数: {analysis['unique_words']}")
    console.print(f"総単語数: {analysis['total_words']}")
    console.print(f"応答あたり平均単語数: {analysis['avg_words_per_response']:.1f}")
    console.print(f"多様性比率: {analysis['diversity_ratio']:.3f}")

    # 頻出単語表示
    table = Table(title="Most Common Words")
    table.add_column("Word", style="cyan")
    table.add_column("Frequency", style="green")

    for word, freq in analysis["common_words"]:
        table.add_row(word, str(freq))

    console.print(table)


if __name__ == "__main__":
    app()