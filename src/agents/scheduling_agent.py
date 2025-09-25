"""
スケジュール調整エージェント (Scheduling Agent)

参加者の時間スロット解析と最適化、イベントタイプ別スケジュール提案、
競合解決を担当します。
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from pydantic import BaseModel, Field

from ..models import (
    Event, EventType, EventStatus, Participant, ParticipationStatus,
    TimeSlot, CoordinationSession
)
from ..models.repository import ParticipantRepository, EventRepository, CoordinationSessionRepository
from .base_agent import (
    BaseAgent, AgentMessage, AgentCapability, AgentStatus,
    MessageType, MessagePriority
)

logger = logging.getLogger(__name__)


class ScheduleOption(BaseModel):
    """スケジュール選択肢"""
    option_id: str = Field(default_factory=lambda: str(uuid4()))
    start_time: datetime = Field(..., description="開始時刻")
    end_time: datetime = Field(..., description="終了時刻")
    available_participants: List[str] = Field(default_factory=list, description="参加可能な参加者ID")
    unavailable_participants: List[str] = Field(default_factory=list, description="参加不可能な参加者ID")
    preference_score: float = Field(..., description="希望度スコア（0.0-1.0）")
    conflict_score: float = Field(..., description="競合スコア（0.0-1.0、低いほど良い）")
    total_score: float = Field(..., description="総合スコア（0.0-1.0）")
    reasoning: str = Field(..., description="選択理由")

    def calculate_attendance_rate(self) -> float:
        """参加率を計算"""
        total = len(self.available_participants) + len(self.unavailable_participants)
        if total == 0:
            return 0.0
        return len(self.available_participants) / total


class TimeSlotAnalysis(BaseModel):
    """時間スロット解析結果"""
    time_slot: TimeSlot = Field(..., description="時間スロット")
    participants_available: List[str] = Field(default_factory=list, description="参加可能者")
    participants_unavailable: List[str] = Field(default_factory=list, description="参加不可能者")
    preference_weights: Dict[str, float] = Field(default_factory=dict, description="参加者の希望度重み")
    conflict_details: List[str] = Field(default_factory=list, description="競合詳細")

    def get_availability_score(self) -> float:
        """可用性スコアを計算"""
        total = len(self.participants_available) + len(self.participants_unavailable)
        if total == 0:
            return 0.0
        return len(self.participants_available) / total


class SchedulingAgent(BaseAgent):
    """スケジュール調整エージェント - 時間最適化と日程調整"""

    def __init__(
        self,
        event_id: str,
        session_id: str,
        participant_repository: Optional[ParticipantRepository] = None,
        event_repository: Optional[EventRepository] = None,
        session_repository: Optional[CoordinationSessionRepository] = None
    ):
        """
        スケジュール調整エージェントを初期化

        Args:
            event_id: 関連するイベントID
            session_id: 関連するセッションID
            participant_repository: 参加者リポジトリ
            event_repository: イベントリポジトリ
            session_repository: セッションリポジトリ
        """
        capabilities = [
            AgentCapability(
                capability_name="time_slot_analysis",
                description="参加者の時間スロット解析と重複検出",
                input_types=["participant_time_slots", "event_type"],
                output_types=["time_availability_matrix", "conflict_report"],
                dependencies=[],
                is_async=True,
                estimated_duration_ms=1000
            ),
            AgentCapability(
                capability_name="schedule_optimization",
                description="最適なスケジュールの選択と提案",
                input_types=["time_availability_matrix", "event_constraints"],
                output_types=["schedule_options", "recommended_schedule"],
                dependencies=["time_slot_analysis"],
                is_async=True,
                estimated_duration_ms=1500
            ),
            AgentCapability(
                capability_name="conflict_resolution",
                description="スケジュール競合の解決戦略",
                input_types=["schedule_conflicts", "participant_priorities"],
                output_types=["resolution_strategies", "alternative_schedules"],
                dependencies=["schedule_optimization"],
                is_async=True,
                estimated_duration_ms=2000
            ),
            AgentCapability(
                capability_name="event_type_adaptation",
                description="イベントタイプに応じた時間帯推奨",
                input_types=["event_type", "participant_preferences"],
                output_types=["time_recommendations", "duration_suggestions"],
                dependencies=[],
                is_async=True,
                estimated_duration_ms=500
            )
        ]

        super().__init__(
            agent_id=f"scheduling_agent_{event_id}",
            name="スケジュール調整エージェント",
            description="参加者の時間調整と最適スケジュール提案",
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
        self.session_repository = session_repository or CoordinationSessionRepository(
            collection_name="coordination_sessions",
            model_class=CoordinationSession
        )

        # 状態管理
        self.current_event: Optional[Event] = None
        self.participants: Dict[str, Participant] = {}
        self.schedule_options: List[ScheduleOption] = []
        self.selected_schedule: Optional[ScheduleOption] = None

        # イベントタイプ別の推奨設定
        self.event_type_preferences = {
            EventType.DINING: {
                "preferred_hours": [12, 13, 18, 19, 20],  # ランチ・ディナータイム
                "duration_minutes": 90,
                "avoid_early_morning": True,
                "avoid_late_night": True
            },
            EventType.STUDY: {
                "preferred_hours": [10, 11, 14, 15, 16],  # 集中しやすい時間帯
                "duration_minutes": 120,
                "avoid_early_morning": False,
                "avoid_late_night": True
            },
            EventType.MEETING: {
                "preferred_hours": [9, 10, 11, 14, 15, 16],  # ビジネスタイム
                "duration_minutes": 60,
                "avoid_early_morning": False,
                "avoid_late_night": True
            }
        }

    async def _initialize_impl(self) -> None:
        """スケジュール調整エージェント固有の初期化"""
        try:
            # イベント情報をロード
            self.current_event = await self.event_repository.get_by_id(self.event_id)
            if not self.current_event:
                raise ValueError(f"イベントが見つかりません: {self.event_id}")

            # 確認済み参加者をロード
            all_participants = await self.participant_repository.find_by_field(
                "event_id", self.event_id
            )

            for participant in all_participants:
                if participant.participation_status == ParticipationStatus.CONFIRMED:
                    self.participants[participant.slack_user_id] = participant

            # メッセージハンドラー登録
            self.register_handler(MessageType.COMMAND, self._handle_command)
            self.register_handler(MessageType.QUERY, self._handle_query)
            self.register_handler(MessageType.EVENT, self._handle_event)

            logger.info(f"スケジュール調整エージェント初期化完了: {len(self.participants)}人の確認済み参加者")

        except Exception as e:
            logger.error(f"スケジュール調整エージェント初期化エラー: {e}")
            raise

    async def _start_impl(self) -> None:
        """スケジュール調整エージェント開始処理"""
        try:
            # 時間スロット解析を開始
            await self._analyze_time_slots()

            # スケジュール最適化を実行
            await self._optimize_schedule()

            # 最適スケジュールを選択
            await self._select_best_schedule()

            logger.info(f"スケジュール調整エージェント開始: {self.agent_id}")

        except Exception as e:
            logger.error(f"スケジュール調整エージェント開始エラー: {e}")
            raise

    async def _stop_impl(self) -> None:
        """スケジュール調整エージェント停止処理"""
        try:
            # 最終結果をイベントに保存
            if self.selected_schedule and self.current_event:
                self.current_event.scheduled_datetime = self.selected_schedule.start_time
                self.current_event.duration_minutes = int(
                    (self.selected_schedule.end_time - self.selected_schedule.start_time).total_seconds() / 60
                )
                await self.event_repository.update(self.current_event)

            # 完了報告を送信
            await self._send_completion_report()

            logger.info(f"スケジュール調整エージェント停止完了: {self.agent_id}")

        except Exception as e:
            logger.error(f"スケジュール調整エージェント停止エラー: {e}")
            raise

    # メッセージハンドラー

    async def _handle_command(self, message: AgentMessage) -> Optional[AgentMessage]:
        """コマンドメッセージの処理"""
        command = message.payload.get("command")
        logger.info(f"コマンド受信: {command}")

        try:
            if command == "analyze_time_slots":
                return await self._handle_analyze_time_slots_command(message)

            elif command == "optimize_schedule":
                return await self._handle_optimize_schedule_command(message)

            elif command == "select_schedule":
                schedule_option_id = message.payload.get("option_id")
                return await self._handle_select_schedule_command(schedule_option_id, message)

            elif command == "get_schedule_options":
                return await self._handle_get_schedule_options_command(message)

            elif command == "resolve_conflicts":
                return await self._handle_resolve_conflicts_command(message)

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

    async def _handle_query(self, message: AgentMessage) -> Optional[AgentMessage]:
        """クエリメッセージの処理"""
        query_type = message.payload.get("query_type")
        logger.debug(f"クエリ受信: {query_type}")

        try:
            if query_type == "current_schedule":
                return await self._handle_current_schedule_query(message)

            elif query_type == "schedule_options":
                return await self._handle_schedule_options_query(message)

            elif query_type == "participant_availability":
                return await self._handle_participant_availability_query(message)

            elif query_type == "conflict_analysis":
                return await self._handle_conflict_analysis_query(message)

            else:
                logger.warning(f"未知のクエリタイプ: {query_type}")
                return message.create_response(
                    sender_id=self.agent_id,
                    payload={"status": "error", "message": f"未知のクエリタイプ: {query_type}"}
                )

        except Exception as e:
            logger.error(f"クエリ処理エラー: {e}")
            return message.create_response(
                sender_id=self.agent_id,
                payload={"status": "error", "message": str(e)}
            )

    async def _handle_event(self, message: AgentMessage) -> Optional[AgentMessage]:
        """イベントメッセージの処理"""
        event_type = message.payload.get("event_type")
        logger.debug(f"イベント受信: {event_type}")

        try:
            if event_type == "participant_updated":
                return await self._handle_participant_updated(message)

            elif event_type == "schedule_conflict_detected":
                return await self._handle_schedule_conflict_detected(message)

            else:
                logger.debug(f"未処理イベントタイプ: {event_type}")

        except Exception as e:
            logger.error(f"イベント処理エラー: {e}")

        return None

    # 時間スロット解析

    async def _analyze_time_slots(self) -> List[TimeSlotAnalysis]:
        """参加者の時間スロットを解析"""
        logger.info("時間スロット解析開始")

        all_time_slots: List[TimeSlotAnalysis] = []

        # 各参加者の時間スロットを収集
        participant_time_slots = {}
        for user_id, participant in self.participants.items():
            participant_time_slots[user_id] = participant.available_time_slots

        # 重複する時間帯を見つける
        potential_slots = self._generate_potential_time_slots()

        for slot in potential_slots:
            analysis = await self._analyze_single_time_slot(slot, participant_time_slots)
            all_time_slots.append(analysis)

        logger.info(f"時間スロット解析完了: {len(all_time_slots)}個のスロットを解析")
        return all_time_slots

    def _generate_potential_time_slots(self) -> List[TimeSlot]:
        """潜在的な時間スロットを生成"""
        potential_slots = []
        event_preferences = self.event_type_preferences.get(
            self.current_event.event_type,
            self.event_type_preferences[EventType.MEETING]
        )

        # 次の2週間で候補を生成
        start_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=14)

        current_date = start_date + timedelta(days=1)  # 明日から開始

        while current_date <= end_date:
            # 土日をスキップ（イベントタイプによって調整可能）
            if current_date.weekday() >= 5:  # 土日
                current_date += timedelta(days=1)
                continue

            # 推奨時間帯で候補を生成
            for hour in event_preferences["preferred_hours"]:
                slot_start = current_date.replace(hour=hour, minute=0)
                slot_end = slot_start + timedelta(minutes=event_preferences["duration_minutes"])

                potential_slot = TimeSlot(
                    start_time=slot_start,
                    end_time=slot_end,
                    preference_level=2  # デフォルト中程度
                )
                potential_slots.append(potential_slot)

            current_date += timedelta(days=1)

        return potential_slots

    async def _analyze_single_time_slot(
        self,
        time_slot: TimeSlot,
        participant_time_slots: Dict[str, List[TimeSlot]]
    ) -> TimeSlotAnalysis:
        """単一時間スロットの解析"""
        available_participants = []
        unavailable_participants = []
        preference_weights = {}
        conflict_details = []

        for user_id, user_slots in participant_time_slots.items():
            is_available = False
            max_preference = 0

            for user_slot in user_slots:
                if self._slots_overlap(time_slot, user_slot):
                    is_available = True
                    max_preference = max(max_preference, user_slot.preference_level)

                    # 部分的な重複をチェック
                    if not self._slot_fully_contains(user_slot, time_slot):
                        conflict_details.append(
                            f"{user_id}: 部分的な重複 ({user_slot.start_time} - {user_slot.end_time})"
                        )

            if is_available:
                available_participants.append(user_id)
                preference_weights[user_id] = max_preference / 3.0  # 正規化
            else:
                unavailable_participants.append(user_id)

        return TimeSlotAnalysis(
            time_slot=time_slot,
            participants_available=available_participants,
            participants_unavailable=unavailable_participants,
            preference_weights=preference_weights,
            conflict_details=conflict_details
        )

    def _slots_overlap(self, slot1: TimeSlot, slot2: TimeSlot) -> bool:
        """時間スロットが重複するかチェック"""
        return not (slot1.end_time <= slot2.start_time or slot2.end_time <= slot1.start_time)

    def _slot_fully_contains(self, container: TimeSlot, contained: TimeSlot) -> bool:
        """containedがcontainerに完全に含まれるかチェック"""
        return container.start_time <= contained.start_time and contained.end_time <= container.end_time

    # スケジュール最適化

    async def _optimize_schedule(self) -> List[ScheduleOption]:
        """スケジュール最適化を実行"""
        logger.info("スケジュール最適化開始")

        time_analyses = await self._analyze_time_slots()
        schedule_options = []

        for analysis in time_analyses:
            if len(analysis.participants_available) >= 2:  # 最小2人の参加者が必要
                option = await self._create_schedule_option(analysis)
                schedule_options.append(option)

        # スコア順でソート
        schedule_options.sort(key=lambda x: x.total_score, reverse=True)

        # 上位5つまでに制限
        self.schedule_options = schedule_options[:5]

        logger.info(f"スケジュール最適化完了: {len(self.schedule_options)}個の候補を生成")
        return self.schedule_options

    async def _create_schedule_option(self, analysis: TimeSlotAnalysis) -> ScheduleOption:
        """時間スロット解析からスケジュール選択肢を作成"""
        # 希望度スコアを計算
        preference_score = self._calculate_preference_score(analysis)

        # 競合スコアを計算
        conflict_score = self._calculate_conflict_score(analysis)

        # 参加率ボーナス
        attendance_rate = analysis.get_availability_score()

        # イベントタイプ適合性
        type_fitness = self._calculate_event_type_fitness(analysis.time_slot)

        # 総合スコア計算
        total_score = (
            preference_score * 0.3 +
            (1.0 - conflict_score) * 0.2 +
            attendance_rate * 0.3 +
            type_fitness * 0.2
        )

        reasoning = self._generate_schedule_reasoning(
            analysis, preference_score, conflict_score, attendance_rate, type_fitness
        )

        return ScheduleOption(
            start_time=analysis.time_slot.start_time,
            end_time=analysis.time_slot.end_time,
            available_participants=analysis.participants_available,
            unavailable_participants=analysis.participants_unavailable,
            preference_score=preference_score,
            conflict_score=conflict_score,
            total_score=total_score,
            reasoning=reasoning
        )

    def _calculate_preference_score(self, analysis: TimeSlotAnalysis) -> float:
        """希望度スコアを計算"""
        if not analysis.preference_weights:
            return 0.0

        total_weight = sum(analysis.preference_weights.values())
        max_possible = len(analysis.preference_weights) * 1.0  # 最大希望度は1.0

        return total_weight / max_possible if max_possible > 0 else 0.0

    def _calculate_conflict_score(self, analysis: TimeSlotAnalysis) -> float:
        """競合スコアを計算（0.0が最良、1.0が最悪）"""
        if not analysis.conflict_details:
            return 0.0

        # 競合の数と重要度に基づいてスコア計算
        conflict_count = len(analysis.conflict_details)
        total_participants = len(analysis.participants_available) + len(analysis.participants_unavailable)

        if total_participants == 0:
            return 1.0

        return min(conflict_count / total_participants, 1.0)

    def _calculate_event_type_fitness(self, time_slot: TimeSlot) -> float:
        """イベントタイプ適合性を計算"""
        event_preferences = self.event_type_preferences.get(
            self.current_event.event_type,
            self.event_type_preferences[EventType.MEETING]
        )

        hour = time_slot.start_time.hour
        preferred_hours = event_preferences["preferred_hours"]

        if hour in preferred_hours:
            return 1.0
        else:
            # 最も近い推奨時間からの距離に基づいてスコア計算
            min_distance = min(abs(hour - pref_hour) for pref_hour in preferred_hours)
            return max(0.0, 1.0 - (min_distance / 12.0))  # 12時間で正規化

    def _generate_schedule_reasoning(
        self,
        analysis: TimeSlotAnalysis,
        preference_score: float,
        conflict_score: float,
        attendance_rate: float,
        type_fitness: float
    ) -> str:
        """スケジュール選択理由を生成"""
        reasons = []

        if attendance_rate >= 0.8:
            reasons.append(f"参加率が高い（{attendance_rate:.0%}）")
        elif attendance_rate >= 0.6:
            reasons.append(f"参加率が適切（{attendance_rate:.0%}）")
        else:
            reasons.append(f"参加率が低い（{attendance_rate:.0%}）")

        if preference_score >= 0.7:
            reasons.append("参加者の希望度が高い")
        elif preference_score >= 0.4:
            reasons.append("参加者の希望度が中程度")
        else:
            reasons.append("参加者の希望度が低い")

        if conflict_score <= 0.2:
            reasons.append("競合が少ない")
        elif conflict_score <= 0.5:
            reasons.append("軽微な競合あり")
        else:
            reasons.append("競合が多い")

        if type_fitness >= 0.8:
            event_type_name = {
                EventType.DINING: "食事会",
                EventType.STUDY: "勉強会",
                EventType.MEETING: "会議"
            }.get(self.current_event.event_type, "イベント")
            reasons.append(f"{event_type_name}に適した時間帯")

        return "、".join(reasons)

    # スケジュール選択

    async def _select_best_schedule(self) -> Optional[ScheduleOption]:
        """最適なスケジュールを選択"""
        if not self.schedule_options:
            logger.warning("選択可能なスケジュールオプションがありません")
            return None

        # 自動選択：最高スコアのオプション
        best_option = self.schedule_options[0]
        self.selected_schedule = best_option

        logger.info(f"最適スケジュール選択: {best_option.start_time} - {best_option.end_time}")
        logger.info(f"選択理由: {best_option.reasoning}")

        # 選択結果を通知
        await self._notify_schedule_selection()

        return best_option

    async def _notify_schedule_selection(self) -> None:
        """スケジュール選択結果を通知"""
        if not self.selected_schedule:
            return

        notification_message = AgentMessage(
            sender_id=self.agent_id,
            message_type=MessageType.EVENT,
            subject="スケジュール決定通知",
            payload={
                "event_type": "schedule_selected",
                "schedule": {
                    "start_time": self.selected_schedule.start_time.isoformat(),
                    "end_time": self.selected_schedule.end_time.isoformat(),
                    "participants": self.selected_schedule.available_participants,
                    "total_score": self.selected_schedule.total_score,
                    "reasoning": self.selected_schedule.reasoning
                }
            }
        )

        await self.send_message(notification_message)

    # 完了報告

    async def _send_completion_report(self) -> None:
        """完了報告を送信"""
        report = {
            "total_participants": len(self.participants),
            "schedule_options_generated": len(self.schedule_options),
            "selected_schedule": self.selected_schedule.dict() if self.selected_schedule else None,
            "analysis_completed": True
        }

        completion_message = AgentMessage(
            sender_id=self.agent_id,
            message_type=MessageType.EVENT,
            subject="スケジュール調整エージェント完了報告",
            payload={
                "event_type": "agent_completed",
                "agent_name": "scheduling_agent",
                "result": report
            }
        )

        await self.send_message(completion_message)

    # 具体的なハンドラー（簡略化）

    async def _handle_analyze_time_slots_command(self, message: AgentMessage) -> AgentMessage:
        analyses = await self._analyze_time_slots()
        return message.create_response(
            sender_id=self.agent_id,
            payload={
                "status": "success",
                "analysis_count": len(analyses),
                "message": "時間スロット解析完了"
            }
        )

    async def _handle_optimize_schedule_command(self, message: AgentMessage) -> AgentMessage:
        options = await self._optimize_schedule()
        return message.create_response(
            sender_id=self.agent_id,
            payload={
                "status": "success",
                "options_count": len(options),
                "top_option": options[0].dict() if options else None
            }
        )

    async def _handle_select_schedule_command(self, option_id: str, message: AgentMessage) -> AgentMessage:
        # 指定されたオプションを選択
        selected_option = None
        for option in self.schedule_options:
            if option.option_id == option_id:
                selected_option = option
                break

        if selected_option:
            self.selected_schedule = selected_option
            await self._notify_schedule_selection()
            return message.create_response(
                sender_id=self.agent_id,
                payload={"status": "success", "selected_schedule": selected_option.dict()}
            )
        else:
            return message.create_response(
                sender_id=self.agent_id,
                payload={"status": "error", "message": "指定されたオプションが見つかりません"}
            )

    async def _handle_get_schedule_options_command(self, message: AgentMessage) -> AgentMessage:
        return message.create_response(
            sender_id=self.agent_id,
            payload={
                "status": "success",
                "options": [option.dict() for option in self.schedule_options]
            }
        )

    async def _handle_resolve_conflicts_command(self, message: AgentMessage) -> AgentMessage:
        # 簡単な競合解決策を提案
        alternative_options = await self._generate_alternative_schedules()
        return message.create_response(
            sender_id=self.agent_id,
            payload={
                "status": "success",
                "alternative_options": [opt.dict() for opt in alternative_options]
            }
        )

    async def _generate_alternative_schedules(self) -> List[ScheduleOption]:
        """代替スケジュールを生成"""
        # 実装簡略化 - 既存のオプションの下位候補を返す
        return self.schedule_options[1:3] if len(self.schedule_options) > 1 else []

    # その他のクエリハンドラー

    async def _handle_current_schedule_query(self, message: AgentMessage) -> AgentMessage:
        if self.selected_schedule:
            return message.create_response(
                sender_id=self.agent_id,
                payload={
                    "current_schedule": self.selected_schedule.dict(),
                    "status": "selected"
                }
            )
        else:
            return message.create_response(
                sender_id=self.agent_id,
                payload={"status": "no_schedule_selected"}
            )

    async def _handle_schedule_options_query(self, message: AgentMessage) -> AgentMessage:
        return message.create_response(
            sender_id=self.agent_id,
            payload={
                "options": [option.dict() for option in self.schedule_options],
                "total_count": len(self.schedule_options)
            }
        )

    async def _handle_participant_availability_query(self, message: AgentMessage) -> AgentMessage:
        availability_summary = {}
        for user_id, participant in self.participants.items():
            availability_summary[user_id] = {
                "total_slots": len(participant.available_time_slots),
                "has_availability": len(participant.available_time_slots) > 0
            }

        return message.create_response(
            sender_id=self.agent_id,
            payload={"participant_availability": availability_summary}
        )

    async def _handle_conflict_analysis_query(self, message: AgentMessage) -> AgentMessage:
        conflicts = []
        for option in self.schedule_options:
            if option.conflict_score > 0.3:  # 高い競合スコア
                conflicts.append({
                    "option_id": option.option_id,
                    "time": f"{option.start_time} - {option.end_time}",
                    "conflict_score": option.conflict_score,
                    "affected_participants": option.unavailable_participants
                })

        return message.create_response(
            sender_id=self.agent_id,
            payload={"conflicts": conflicts, "total_conflicts": len(conflicts)}
        )

    # イベントハンドラー

    async def _handle_participant_updated(self, message: AgentMessage) -> None:
        """参加者更新イベントの処理"""
        user_id = message.payload.get("user_id")
        if user_id:
            # 参加者情報を再ロード
            participant = await self.participant_repository.find_by_field("slack_user_id", user_id)
            if participant and participant[0].participation_status == ParticipationStatus.CONFIRMED:
                self.participants[user_id] = participant[0]
                logger.info(f"参加者情報更新: {user_id}")

    async def _handle_schedule_conflict_detected(self, message: AgentMessage) -> None:
        """スケジュール競合検出イベントの処理"""
        conflict_details = message.payload.get("conflict_details", {})
        logger.warning(f"スケジュール競合検出: {conflict_details}")

        # 代替案を生成
        alternatives = await self._generate_alternative_schedules()
        if alternatives:
            logger.info(f"代替スケジュール生成: {len(alternatives)}個の候補")

            # 代替案通知
            alternative_message = AgentMessage(
                sender_id=self.agent_id,
                message_type=MessageType.EVENT,
                subject="代替スケジュール提案",
                payload={
                    "event_type": "alternative_schedules_available",
                    "alternatives": [alt.dict() for alt in alternatives]
                }
            )
            await self.send_message(alternative_message)