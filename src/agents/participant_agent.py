"""
参加者エージェント (Participant Agent)

参加者とのダイレクトメッセージワークフロー管理、確認状況の追跡、
リマインダー送信を担当します。
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Pattern
from uuid import uuid4
import re

from pydantic import BaseModel, Field

from ..models import (
    Participant, ParticipationStatus, TimeSlot, Event, EventType
)
from ..models.repository import ParticipantRepository, EventRepository
from .base_agent import (
    BaseAgent, AgentMessage, AgentCapability, AgentStatus,
    MessageType, MessagePriority
)

logger = logging.getLogger(__name__)


class ParticipantResponse(BaseModel):
    """参加者回答分析結果"""
    user_id: str = Field(..., description="ユーザーID")
    response_type: str = Field(..., description="回答タイプ")
    participation_status: ParticipationStatus = Field(..., description="参加ステータス")
    time_slots: List[TimeSlot] = Field(default_factory=list, description="提案された時間スロット")
    dietary_restrictions: Optional[str] = Field(None, description="食事制限")
    additional_info: Dict[str, Any] = Field(default_factory=dict, description="追加情報")
    confidence_score: float = Field(..., description="分析の信頼度")


class MessageTemplate(BaseModel):
    """メッセージテンプレート"""
    template_id: str = Field(..., description="テンプレートID")
    event_type: EventType = Field(..., description="対象イベントタイプ")
    message_type: str = Field(..., description="メッセージタイプ")
    template: str = Field(..., description="メッセージテンプレート")
    variables: List[str] = Field(default_factory=list, description="テンプレート変数")


class ParticipantAgent(BaseAgent):
    """参加者エージェント - DMワークフローと参加者管理"""

    def __init__(
        self,
        event_id: str,
        session_id: str,
        participant_repository: Optional[ParticipantRepository] = None,
        event_repository: Optional[EventRepository] = None
    ):
        """
        参加者エージェントを初期化

        Args:
            event_id: 関連するイベントID
            session_id: 関連するセッションID
            participant_repository: 参加者リポジトリ
            event_repository: イベントリポジトリ
        """
        capabilities = [
            AgentCapability(
                capability_name="participant_collection",
                description="参加者の収集と初期確認",
                input_types=["event_details", "user_mentions"],
                output_types=["participant_list", "dm_sent_confirmations"],
                dependencies=[],
                is_async=True,
                estimated_duration_ms=2000
            ),
            AgentCapability(
                capability_name="dm_workflow_management",
                description="ダイレクトメッセージでの参加者とのやり取り管理",
                input_types=["slack_dm_message", "user_response"],
                output_types=["participant_status_update", "follow_up_message"],
                dependencies=["participant_collection"],
                is_async=True,
                estimated_duration_ms=500
            ),
            AgentCapability(
                capability_name="response_analysis",
                description="参加者回答の自然言語解析",
                input_types=["japanese_text", "slack_message"],
                output_types=["structured_response", "participation_status"],
                dependencies=[],
                is_async=True,
                estimated_duration_ms=800
            ),
            AgentCapability(
                capability_name="reminder_management",
                description="リマインダーの送信と追跡",
                input_types=["participant_status", "time_schedule"],
                output_types=["reminder_sent", "escalation_required"],
                dependencies=["participant_collection"],
                is_async=True,
                estimated_duration_ms=300
            )
        ]

        super().__init__(
            agent_id=f"participant_agent_{event_id}",
            name="参加者エージェント",
            description="参加者とのDMワークフロー管理と確認状況の追跡",
            capabilities=capabilities,
            event_id=event_id,
            session_id=session_id
        )

        # リポジトリ
        self.participant_repository = participant_repository or ParticipantRepository(
            collection_name="participants",
            model_class=Participant
        )
        self.event_repository = event_repository or EventRepository(
            collection_name="events",
            model_class=Event
        )

        # 状態管理
        self.current_event: Optional[Event] = None
        self.participants: Dict[str, Participant] = {}
        self.pending_confirmations: Dict[str, str] = {}  # user_id -> message_ts

        # 日本語応答パターン
        self.response_patterns = self._initialize_response_patterns()

        # メッセージテンプレート
        self.message_templates = self._initialize_message_templates()

    def _initialize_response_patterns(self) -> Dict[str, List[Pattern]]:
        """日本語応答パターンを初期化"""
        return {
            "confirmation": [
                re.compile(r"参加します?", re.IGNORECASE),
                re.compile(r"はい", re.IGNORECASE),
                re.compile(r"ok", re.IGNORECASE),
                re.compile(r"大丈夫", re.IGNORECASE),
                re.compile(r"ぜひ", re.IGNORECASE),
                re.compile(r"よろしく", re.IGNORECASE)
            ],
            "decline": [
                re.compile(r"参加できません", re.IGNORECASE),
                re.compile(r"無理", re.IGNORECASE),
                re.compile(r"都合が悪い", re.IGNORECASE),
                re.compile(r"不参加", re.IGNORECASE),
                re.compile(r"すみません", re.IGNORECASE),
                re.compile(r"申し訳", re.IGNORECASE)
            ],
            "time_suggestion": [
                re.compile(r"(\d{1,2})時", re.IGNORECASE),
                re.compile(r"(月|火|水|木|金|土|日)曜日", re.IGNORECASE),
                re.compile(r"午前|午後", re.IGNORECASE),
                re.compile(r"朝|昼|夜", re.IGNORECASE),
                re.compile(r"来週|今週|再来週", re.IGNORECASE)
            ],
            "dietary_restrictions": [
                re.compile(r"アレルギー", re.IGNORECASE),
                re.compile(r"食べられない", re.IGNORECASE),
                re.compile(r"ベジタリアン", re.IGNORECASE),
                re.compile(r"ハラル", re.IGNORECASE),
                re.compile(r"制限", re.IGNORECASE)
            ]
        }

    def _initialize_message_templates(self) -> Dict[str, MessageTemplate]:
        """メッセージテンプレートを初期化"""
        return {
            "initial_invitation": MessageTemplate(
                template_id="initial_invitation",
                event_type=EventType.DINING,
                message_type="invitation",
                template="""こんにちは！{organizer_name}さんが{event_title}を企画しています。

📅 日程: {proposed_dates}
🍴 内容: {event_description}
👥 参加予定: {current_participants}

参加いただけますでしょうか？
以下のような形でお返事ください：

・参加します / 参加できません
・都合の良い日時があれば教えてください
・食事制限やアレルギーがあれば教えてください

よろしくお願いします！""",
                variables=["organizer_name", "event_title", "proposed_dates", "event_description", "current_participants"]
            ),
            "reminder": MessageTemplate(
                template_id="reminder",
                event_type=EventType.DINING,
                message_type="reminder",
                template="""お疲れ様です！

先日お送りした{event_title}の件、いかがでしょうか？

まだお返事をいただけていないので、改めてご連絡させていただきました。
参加可否について教えていただけると助かります。

・参加します
・参加できません
・検討中です

お忙しい中恐れ入りますが、よろしくお願いします。""",
                variables=["event_title"]
            ),
            "confirmation": MessageTemplate(
                template_id="confirmation",
                event_type=EventType.DINING,
                message_type="confirmation",
                template="""ありがとうございます！

{response_summary}として承りました。

{additional_info}

引き続き調整を進めさせていただきます。
詳細が決まりましたら改めてご連絡いたします！""",
                variables=["response_summary", "additional_info"]
            )
        }

    async def _initialize_impl(self) -> None:
        """参加者エージェント固有の初期化"""
        try:
            # イベント情報をロード
            self.current_event = await self.event_repository.get_by_id(self.event_id)
            if not self.current_event:
                raise ValueError(f"イベントが見つかりません: {self.event_id}")

            # 既存の参加者をロード
            existing_participants = await self.participant_repository.find_by_field(
                "event_id", self.event_id
            )
            for participant in existing_participants:
                self.participants[participant.slack_user_id] = participant

            # メッセージハンドラー登録
            self.register_handler(MessageType.COMMAND, self._handle_command)
            self.register_handler(MessageType.EVENT, self._handle_event)

            logger.info(f"参加者エージェント初期化完了: {len(self.participants)}人の参加者")

        except Exception as e:
            logger.error(f"参加者エージェント初期化エラー: {e}")
            raise

    async def _start_impl(self) -> None:
        """参加者エージェント開始処理"""
        try:
            # 初期参加者招待を開始
            await self._send_initial_invitations()

            # リマインダースケジュールを設定
            await self._schedule_reminders()

            logger.info(f"参加者エージェント開始: {self.agent_id}")

        except Exception as e:
            logger.error(f"参加者エージェント開始エラー: {e}")
            raise

    async def _stop_impl(self) -> None:
        """参加者エージェント停止処理"""
        try:
            # 未完了の確認をクリーンアップ
            await self._cleanup_pending_confirmations()

            # 完了報告を送信
            await self._send_completion_report()

            logger.info(f"参加者エージェント停止完了: {self.agent_id}")

        except Exception as e:
            logger.error(f"参加者エージェント停止エラー: {e}")
            raise

    # メッセージハンドラー

    async def _handle_command(self, message: AgentMessage) -> Optional[AgentMessage]:
        """コマンドメッセージの処理"""
        command = message.payload.get("command")
        logger.info(f"コマンド受信: {command}")

        try:
            if command == "add_participant":
                user_id = message.payload.get("user_id")
                return await self._handle_add_participant(user_id, message)

            elif command == "send_reminder":
                user_id = message.payload.get("user_id")
                return await self._handle_send_reminder(user_id, message)

            elif command == "get_participants_status":
                return await self._handle_get_participants_status(message)

            elif command == "process_dm_response":
                return await self._handle_process_dm_response(message)

            else:
                logger.warning(f"未知のコマンド: {command}")
                return message.create_response(
                    sender_id=self.agent_id,
                    payload={"status": "error", "message": f"未知のコマンド: {command}"}
                )

        except Exception as e:
            logger.error(f"コマンド処理エラー: {e}")
            return message.create_response(
                sender_id=self.agent_id,
                payload={"status": "error", "message": str(e)}
            )

    async def _handle_event(self, message: AgentMessage) -> Optional[AgentMessage]:
        """イベントメッセージの処理"""
        event_type = message.payload.get("event_type")
        logger.debug(f"イベント受信: {event_type}")

        try:
            if event_type == "slack_dm_received":
                return await self._handle_slack_dm_received(message)

            elif event_type == "participant_mentioned":
                return await self._handle_participant_mentioned(message)

            elif event_type == "timeout_check":
                return await self._handle_timeout_check(message)

            else:
                logger.debug(f"未処理イベントタイプ: {event_type}")

        except Exception as e:
            logger.error(f"イベント処理エラー: {e}")

        return None

    # 参加者管理

    async def _add_participant(self, user_id: str, display_name: Optional[str] = None) -> Participant:
        """参加者を追加"""
        if user_id in self.participants:
            return self.participants[user_id]

        participant = Participant(
            event_id=self.event_id,
            slack_user_id=user_id,
            display_name=display_name
        )

        # データベースに保存
        await self.participant_repository.create(participant)

        # メモリに追加
        self.participants[user_id] = participant

        logger.info(f"参加者追加: {user_id}")
        return participant

    async def _send_initial_invitations(self) -> None:
        """初期招待メッセージを送信"""
        for user_id, participant in self.participants.items():
            if participant.participation_status == ParticipationStatus.PENDING:
                await self._send_invitation_dm(participant)

    async def _send_invitation_dm(self, participant: Participant) -> None:
        """招待DMを送信"""
        template = self.message_templates["initial_invitation"]

        # テンプレート変数を準備
        variables = {
            "organizer_name": "主催者",  # 実際はイベントから取得
            "event_title": self.current_event.generate_title(),
            "proposed_dates": self._format_proposed_dates(),
            "event_description": self.current_event.purpose,
            "current_participants": f"{len(self.participants)}人が招待されています"
        }

        message_text = template.template.format(**variables)

        # Slack DM送信メッセージを作成
        dm_message = AgentMessage(
            sender_id=self.agent_id,
            message_type=MessageType.COMMAND,
            subject="DM送信要求",
            payload={
                "command": "send_dm",
                "user_id": participant.slack_user_id,
                "message": message_text,
                "message_type": "invitation"
            }
        )

        await self.send_message(dm_message)

        # 送信記録を更新
        participant.last_contacted_at = datetime.utcnow()
        await self.participant_repository.update(participant)

        logger.info(f"招待DM送信: {participant.slack_user_id}")

    async def _send_reminder(self, participant: Participant) -> None:
        """リマインダーを送信"""
        if not participant.needs_reminder():
            return

        template = self.message_templates["reminder"]
        variables = {
            "event_title": self.current_event.generate_title()
        }

        message_text = template.template.format(**variables)

        # Slack DM送信メッセージを作成
        dm_message = AgentMessage(
            sender_id=self.agent_id,
            message_type=MessageType.COMMAND,
            subject="リマインダー送信要求",
            payload={
                "command": "send_dm",
                "user_id": participant.slack_user_id,
                "message": message_text,
                "message_type": "reminder"
            }
        )

        await self.send_message(dm_message)

        # リマインダー記録を更新
        participant.send_reminder()
        await self.participant_repository.update(participant)

        logger.info(f"リマインダー送信: {participant.slack_user_id}")

    # 応答解析

    async def _analyze_participant_response(self, user_id: str, message_text: str) -> ParticipantResponse:
        """参加者の応答を解析"""
        # 基本的な感情分析
        participation_status = self._detect_participation_status(message_text)

        # 時間提案の抽出
        time_slots = self._extract_time_suggestions(message_text)

        # 食事制限の抽出
        dietary_restrictions = self._extract_dietary_restrictions(message_text)

        response = ParticipantResponse(
            user_id=user_id,
            response_type="text_analysis",
            participation_status=participation_status,
            time_slots=time_slots,
            dietary_restrictions=dietary_restrictions,
            confidence_score=0.8  # 基本的な信頼度
        )

        logger.info(f"応答解析完了: {user_id} -> {participation_status}")
        return response

    def _detect_participation_status(self, text: str) -> ParticipationStatus:
        """参加ステータスを検出"""
        # 確認パターンをチェック
        for pattern in self.response_patterns["confirmation"]:
            if pattern.search(text):
                return ParticipationStatus.CONFIRMED

        # 辞退パターンをチェック
        for pattern in self.response_patterns["decline"]:
            if pattern.search(text):
                return ParticipationStatus.DECLINED

        return ParticipationStatus.PENDING

    def _extract_time_suggestions(self, text: str) -> List[TimeSlot]:
        """時間提案を抽出"""
        time_slots = []

        # 簡単な時間抽出（実際にはより複雑な解析が必要）
        time_patterns = self.response_patterns["time_suggestion"]

        for pattern in time_patterns:
            matches = pattern.findall(text)
            if matches:
                # 基本的な時間スロットを作成（実装簡略化）
                start_time = datetime.utcnow() + timedelta(days=7)  # 来週
                end_time = start_time + timedelta(hours=2)

                time_slot = TimeSlot(
                    start_time=start_time,
                    end_time=end_time,
                    preference_level=2,
                    note=f"テキストから抽出: {', '.join(matches)}"
                )
                time_slots.append(time_slot)
                break

        return time_slots

    def _extract_dietary_restrictions(self, text: str) -> Optional[str]:
        """食事制限を抽出"""
        for pattern in self.response_patterns["dietary_restrictions"]:
            match = pattern.search(text)
            if match:
                # マッチした周辺のテキストを抽出
                start = max(0, match.start() - 20)
                end = min(len(text), match.end() + 20)
                return text[start:end].strip()

        return None

    # ユーティリティメソッド

    def _format_proposed_dates(self) -> str:
        """提案日程をフォーマット"""
        # 実装簡略化
        return "来週中で調整中"

    async def _schedule_reminders(self) -> None:
        """リマインダーをスケジュール"""
        # 実装簡略化 - 実際にはスケジューラーを使用
        logger.info("リマインダースケジュール設定")

    async def _cleanup_pending_confirmations(self) -> None:
        """未完了確認のクリーンアップ"""
        self.pending_confirmations.clear()

    async def _send_completion_report(self) -> None:
        """完了報告を送信"""
        completion_report = {
            "total_participants": len(self.participants),
            "confirmed_participants": len([p for p in self.participants.values()
                                         if p.participation_status == ParticipationStatus.CONFIRMED]),
            "declined_participants": len([p for p in self.participants.values()
                                        if p.participation_status == ParticipationStatus.DECLINED]),
            "pending_participants": len([p for p in self.participants.values()
                                       if p.participation_status == ParticipationStatus.PENDING])
        }

        completion_message = AgentMessage(
            sender_id=self.agent_id,
            message_type=MessageType.EVENT,
            subject="参加者エージェント完了報告",
            payload={
                "event_type": "agent_completed",
                "agent_name": "participant_agent",
                "result": completion_report
            }
        )

        await self.send_message(completion_message)

    # 具体的なハンドラー（簡略化）

    async def _handle_add_participant(self, user_id: str, message: AgentMessage) -> AgentMessage:
        display_name = message.payload.get("display_name")
        participant = await self._add_participant(user_id, display_name)

        return message.create_response(
            sender_id=self.agent_id,
            payload={
                "status": "success",
                "participant_id": participant.participant_id
            }
        )

    async def _handle_send_reminder(self, user_id: str, message: AgentMessage) -> AgentMessage:
        participant = self.participants.get(user_id)
        if participant:
            await self._send_reminder(participant)
            return message.create_response(
                sender_id=self.agent_id,
                payload={"status": "success", "message": "リマインダー送信完了"}
            )
        else:
            return message.create_response(
                sender_id=self.agent_id,
                payload={"status": "error", "message": "参加者が見つかりません"}
            )

    async def _handle_get_participants_status(self, message: AgentMessage) -> AgentMessage:
        status_summary = {
            user_id: {
                "status": participant.participation_status,
                "last_contacted": participant.last_contacted_at.isoformat() if participant.last_contacted_at else None,
                "reminder_count": participant.reminder_count
            }
            for user_id, participant in self.participants.items()
        }

        return message.create_response(
            sender_id=self.agent_id,
            payload={"participants_status": status_summary}
        )

    async def _handle_process_dm_response(self, message: AgentMessage) -> AgentMessage:
        user_id = message.payload.get("user_id")
        response_text = message.payload.get("text", "")

        if user_id not in self.participants:
            return message.create_response(
                sender_id=self.agent_id,
                payload={"status": "error", "message": "参加者が見つかりません"}
            )

        # 応答を解析
        analysis = await self._analyze_participant_response(user_id, response_text)

        # 参加者情報を更新
        participant = self.participants[user_id]

        if analysis.participation_status == ParticipationStatus.CONFIRMED:
            participant.confirm_participation(response_text)
        elif analysis.participation_status == ParticipationStatus.DECLINED:
            participant.decline_participation(response_text)

        # 時間スロットを追加
        for time_slot in analysis.time_slots:
            participant.add_time_slot(time_slot)

        # 食事制限を更新
        if analysis.dietary_restrictions:
            participant.dietary_restrictions = analysis.dietary_restrictions

        # データベース更新
        await self.participant_repository.update(participant)

        # 確認メッセージを送信
        await self._send_confirmation_message(participant, analysis)

        return message.create_response(
            sender_id=self.agent_id,
            payload={
                "status": "success",
                "analysis": analysis.dict()
            }
        )

    async def _handle_slack_dm_received(self, message: AgentMessage) -> None:
        """Slack DM受信の処理"""
        user_id = message.payload.get("user_id")
        text = message.payload.get("text", "")

        if user_id in self.participants:
            # DM応答処理メッセージを作成
            process_message = AgentMessage(
                sender_id=self.agent_id,
                message_type=MessageType.COMMAND,
                subject="DM応答処理",
                payload={
                    "command": "process_dm_response",
                    "user_id": user_id,
                    "text": text
                }
            )
            await self.handle_message(process_message)

    async def _handle_participant_mentioned(self, message: AgentMessage) -> None:
        """参加者メンション処理"""
        mentioned_users = message.payload.get("mentioned_users", [])

        for user_info in mentioned_users:
            user_id = user_info.get("user_id")
            display_name = user_info.get("display_name")

            if user_id not in self.participants:
                await self._add_participant(user_id, display_name)

    async def _handle_timeout_check(self, message: AgentMessage) -> None:
        """タイムアウトチェック処理"""
        current_time = datetime.utcnow()

        for participant in self.participants.values():
            if participant.needs_reminder():
                await self._send_reminder(participant)

    async def _send_confirmation_message(self, participant: Participant, analysis: ParticipantResponse) -> None:
        """確認メッセージを送信"""
        template = self.message_templates["confirmation"]

        if analysis.participation_status == ParticipationStatus.CONFIRMED:
            response_summary = "ご参加"
        elif analysis.participation_status == ParticipationStatus.DECLINED:
            response_summary = "ご不参加"
        else:
            response_summary = "ご検討中"

        additional_info = ""
        if analysis.dietary_restrictions:
            additional_info += f"食事制限: {analysis.dietary_restrictions}\n"
        if analysis.time_slots:
            additional_info += "ご都合の良い時間帯も承りました。\n"

        variables = {
            "response_summary": response_summary,
            "additional_info": additional_info.strip()
        }

        message_text = template.template.format(**variables)

        # 確認DM送信
        dm_message = AgentMessage(
            sender_id=self.agent_id,
            message_type=MessageType.COMMAND,
            subject="確認DM送信要求",
            payload={
                "command": "send_dm",
                "user_id": participant.slack_user_id,
                "message": message_text,
                "message_type": "confirmation"
            }
        )

        await self.send_message(dm_message)