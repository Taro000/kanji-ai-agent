"""
調整エージェント (Coordination Agent)

全体のワークフロー調整とエージェント間通信のオーケストレーションを担当します。
ADKイベントバスを使用して他のエージェントとの協調を実現します。
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

from pydantic import BaseModel, Field

from ..models import (
    Event, EventStatus, CoordinationSession, CoordinationPhase,
    AgentInstance, AgentStatus as ModelAgentStatus
)
from ..models.repository import BaseRepository, CoordinationSessionRepository
from .base_agent import (
    BaseAgent, AgentMessage, AgentCapability, AgentStatus,
    MessageType, MessagePriority
)

logger = logging.getLogger(__name__)


class WorkflowDecision(BaseModel):
    """ワークフロー決定"""
    decision_id: str = Field(default_factory=lambda: str(uuid4()))
    phase: CoordinationPhase = Field(..., description="対象フェーズ")
    decision_type: str = Field(..., description="決定タイプ")
    options: List[Dict[str, Any]] = Field(default_factory=list, description="選択肢")
    selected_option: Optional[Dict[str, Any]] = Field(None, description="選択された選択肢")
    reasoning: str = Field(..., description="決定理由")
    confidence_score: float = Field(..., description="確信度（0.0-1.0）")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class CoordinationAgent(BaseAgent):
    """調整エージェント - ワークフロー全体の管理とエージェント調整"""

    def __init__(
        self,
        event_id: str,
        session_id: str,
        session_repository: Optional[CoordinationSessionRepository] = None
    ):
        """
        調整エージェントを初期化

        Args:
            event_id: 関連するイベントID
            session_id: 関連するセッションID
            session_repository: セッションリポジトリ
        """
        capabilities = [
            AgentCapability(
                capability_name="workflow_orchestration",
                description="ワークフロー全体の調整とオーケストレーション",
                input_types=["phase_transition_request", "agent_status_update"],
                output_types=["phase_transition_command", "agent_coordination_message"],
                dependencies=[],
                is_async=True,
                estimated_duration_ms=500
            ),
            AgentCapability(
                capability_name="agent_coordination",
                description="他エージェントとの調整と依存関係管理",
                input_types=["agent_registration", "agent_completion_report"],
                output_types=["agent_start_command", "agent_stop_command"],
                dependencies=["workflow_orchestration"],
                is_async=True,
                estimated_duration_ms=200
            ),
            AgentCapability(
                capability_name="decision_making",
                description="ワークフロー決定と中間確認の調整",
                input_types=["decision_request", "user_confirmation"],
                output_types=["decision_response", "confirmation_request"],
                dependencies=["workflow_orchestration"],
                is_async=True,
                estimated_duration_ms=1000
            ),
            AgentCapability(
                capability_name="error_recovery",
                description="エラー処理と復旧戦略の実行",
                input_types=["error_report", "agent_failure"],
                output_types=["recovery_command", "fallback_strategy"],
                dependencies=["workflow_orchestration", "agent_coordination"],
                is_async=True,
                estimated_duration_ms=2000
            )
        ]

        super().__init__(
            agent_id=f"coordination_agent_{event_id}",
            name="調整エージェント",
            description="イベント調整ワークフローの全体調整とエージェント間協調を管理",
            capabilities=capabilities,
            event_id=event_id,
            session_id=session_id
        )

        # リポジトリ
        self.session_repository = session_repository or CoordinationSessionRepository(
            collection_name="coordination_sessions",
            model_class=CoordinationSession
        )

        # 状態管理
        self.coordination_session: Optional[CoordinationSession] = None
        self.managed_agents: Dict[str, AgentInstance] = {}
        self.workflow_decisions: List[WorkflowDecision] = []

        # エージェント依存関係マップ
        self.agent_dependencies = {
            "participant_agent": [],  # 依存なし
            "scheduling_agent": ["participant_agent"],
            "venue_agent": ["scheduling_agent"],
            "calendar_agent": ["scheduling_agent", "venue_agent"]
        }

        # フェーズ遷移ルール
        self.phase_transitions = {
            CoordinationPhase.INITIALIZATION: CoordinationPhase.PARTICIPANT_COLLECTION,
            CoordinationPhase.PARTICIPANT_COLLECTION: CoordinationPhase.SCHEDULE_COORDINATION,
            CoordinationPhase.SCHEDULE_COORDINATION: CoordinationPhase.VENUE_COORDINATION,
            CoordinationPhase.VENUE_COORDINATION: CoordinationPhase.CALENDAR_INTEGRATION,
            CoordinationPhase.CALENDAR_INTEGRATION: CoordinationPhase.FINAL_CONFIRMATION,
            CoordinationPhase.FINAL_CONFIRMATION: CoordinationPhase.ANNOUNCEMENT,
            CoordinationPhase.ANNOUNCEMENT: CoordinationPhase.COMPLETED
        }

    async def _initialize_impl(self) -> None:
        """調整エージェント固有の初期化"""
        try:
            # セッションをロードまたは作成
            self.coordination_session = await self.session_repository.get_by_id(self.session_id)
            if not self.coordination_session:
                logger.info(f"新しい調整セッションを作成: {self.session_id}")
                self.coordination_session = CoordinationSession(
                    session_id=self.session_id,
                    event_id=self.event_id,
                    thread_ts=f"{int(datetime.utcnow().timestamp())}.000000"  # 仮のthread_ts
                )
                await self.session_repository.create(self.coordination_session)

            # メッセージハンドラー登録
            self.register_handler(MessageType.COMMAND, self._handle_command)
            self.register_handler(MessageType.QUERY, self._handle_query)
            self.register_handler(MessageType.RESPONSE, self._handle_response)
            self.register_handler(MessageType.EVENT, self._handle_event)

            # エラーハンドラー登録
            self.register_error_handler(self._handle_coordination_error)

            logger.info(f"調整エージェント初期化完了: {self.agent_id}")

        except Exception as e:
            logger.error(f"調整エージェント初期化エラー: {e}")
            raise

    async def _start_impl(self) -> None:
        """調整エージェント開始処理"""
        try:
            # 初期フェーズに設定
            if self.coordination_session.current_phase == CoordinationPhase.INITIALIZATION:
                await self._transition_to_phase(CoordinationPhase.PARTICIPANT_COLLECTION)

            # 定期的なハートビート開始
            await self._schedule_heartbeat()

            logger.info(f"調整エージェント開始: フェーズ={self.coordination_session.current_phase}")

        except Exception as e:
            logger.error(f"調整エージェント開始エラー: {e}")
            raise

    async def _stop_impl(self) -> None:
        """調整エージェント停止処理"""
        try:
            # 管理中のエージェントを停止
            for agent_name in list(self.managed_agents.keys()):
                await self._stop_agent(agent_name)

            # セッション状態を更新
            if self.coordination_session:
                self.coordination_session.current_phase = CoordinationPhase.COMPLETED
                await self.session_repository.update(self.coordination_session)

            logger.info(f"調整エージェント停止完了: {self.agent_id}")

        except Exception as e:
            logger.error(f"調整エージェント停止エラー: {e}")
            raise

    # メッセージハンドラー

    async def _handle_command(self, message: AgentMessage) -> Optional[AgentMessage]:
        """コマンドメッセージの処理"""
        command = message.payload.get("command")
        logger.info(f"コマンド受信: {command}")

        try:
            if command == "start_agent":
                agent_name = message.payload.get("agent_name")
                return await self._handle_start_agent_command(agent_name, message)

            elif command == "stop_agent":
                agent_name = message.payload.get("agent_name")
                return await self._handle_stop_agent_command(agent_name, message)

            elif command == "transition_phase":
                target_phase = message.payload.get("target_phase")
                return await self._handle_phase_transition_command(target_phase, message)

            elif command == "register_agent":
                return await self._handle_agent_registration(message)

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
            if query_type == "status":
                return await self._handle_status_query(message)

            elif query_type == "current_phase":
                return message.create_response(
                    sender_id=self.agent_id,
                    payload={
                        "current_phase": self.coordination_session.current_phase,
                        "phase_duration": self.coordination_session.get_phase_duration()
                    }
                )

            elif query_type == "agent_status":
                agent_name = message.payload.get("agent_name")
                return await self._handle_agent_status_query(agent_name, message)

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

    async def _handle_response(self, message: AgentMessage) -> Optional[AgentMessage]:
        """レスポンスメッセージの処理"""
        logger.debug(f"レスポンス受信: {message.sender_id}")

        # 対応する要求を特定して処理
        correlation_id = message.correlation_id
        if correlation_id:
            await self._process_agent_response(message)

        return None

    async def _handle_event(self, message: AgentMessage) -> Optional[AgentMessage]:
        """イベントメッセージの処理"""
        event_type = message.payload.get("event_type")
        logger.info(f"イベント受信: {event_type}")

        try:
            if event_type == "agent_completed":
                return await self._handle_agent_completion(message)

            elif event_type == "agent_failed":
                return await self._handle_agent_failure(message)

            elif event_type == "user_confirmation":
                return await self._handle_user_confirmation(message)

            elif event_type == "phase_ready":
                return await self._handle_phase_ready(message)

            else:
                logger.debug(f"未処理イベントタイプ: {event_type}")

        except Exception as e:
            logger.error(f"イベント処理エラー: {e}")

        return None

    # エージェント管理

    async def _handle_agent_registration(self, message: AgentMessage) -> AgentMessage:
        """エージェント登録処理"""
        agent_name = message.payload.get("agent_name")
        agent_capabilities = message.payload.get("capabilities", [])

        logger.info(f"エージェント登録: {agent_name}")

        # エージェントインスタンスを作成
        agent_instance = AgentInstance(
            agent_name=agent_name,
            status=ModelAgentStatus.IDLE
        )

        # セッションに追加
        self.coordination_session.active_agents.append(agent_instance)
        self.managed_agents[agent_name] = agent_instance

        # セッション更新
        await self.session_repository.update(self.coordination_session)

        return message.create_response(
            sender_id=self.agent_id,
            payload={
                "status": "registered",
                "agent_id": agent_instance.agent_id,
                "assigned_tasks": await self._get_assigned_tasks(agent_name)
            }
        )

    async def _start_agent(self, agent_name: str, task: Optional[str] = None) -> bool:
        """エージェントを開始"""
        if agent_name not in self.managed_agents:
            logger.error(f"未登録のエージェント: {agent_name}")
            return False

        agent = self.managed_agents[agent_name]

        # 依存関係チェック
        dependencies = self.agent_dependencies.get(agent_name, [])
        for dep in dependencies:
            if dep not in self.managed_agents:
                logger.warning(f"依存関係未満足: {agent_name} requires {dep}")
                return False

            dep_agent = self.managed_agents[dep]
            if dep_agent.status != ModelAgentStatus.COMPLETED:
                logger.info(f"依存関係待機: {agent_name} waiting for {dep}")
                agent.status = ModelAgentStatus.WAITING
                await self.session_repository.update(self.coordination_session)
                return False

        # エージェント開始
        if self.coordination_session.start_agent(agent_name, task):
            await self.session_repository.update(self.coordination_session)

            # 開始コマンドを送信
            start_message = AgentMessage(
                sender_id=self.agent_id,
                recipient_id=f"{agent_name}_{self.event_id}",
                message_type=MessageType.COMMAND,
                subject=f"エージェント開始: {agent_name}",
                payload={
                    "command": "start",
                    "task": task,
                    "event_id": self.event_id,
                    "session_id": self.session_id
                }
            )
            await self.send_message(start_message)

            logger.info(f"エージェント開始: {agent_name}")
            return True

        return False

    async def _stop_agent(self, agent_name: str) -> bool:
        """エージェントを停止"""
        if agent_name not in self.managed_agents:
            return False

        # 停止コマンドを送信
        stop_message = AgentMessage(
            sender_id=self.agent_id,
            recipient_id=f"{agent_name}_{self.event_id}",
            message_type=MessageType.COMMAND,
            subject=f"エージェント停止: {agent_name}",
            payload={"command": "stop"}
        )
        await self.send_message(stop_message)

        logger.info(f"エージェント停止: {agent_name}")
        return True

    # フェーズ管理

    async def _transition_to_phase(self, target_phase: CoordinationPhase) -> bool:
        """フェーズ遷移実行"""
        if not self.coordination_session.transition_to_phase(target_phase):
            logger.warning(f"無効なフェーズ遷移: {self.coordination_session.current_phase} -> {target_phase}")
            return False

        await self.session_repository.update(self.coordination_session)

        # フェーズ遷移イベントをブロードキャスト
        phase_message = AgentMessage(
            sender_id=self.agent_id,
            message_type=MessageType.EVENT,
            subject=f"フェーズ遷移: {target_phase}",
            payload={
                "event_type": "phase_transition",
                "new_phase": target_phase,
                "previous_phase": self.coordination_session.previous_phase,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        await self.send_message(phase_message)

        # フェーズに応じたエージェント開始
        await self._start_phase_agents(target_phase)

        logger.info(f"フェーズ遷移完了: {target_phase}")
        return True

    async def _start_phase_agents(self, phase: CoordinationPhase) -> None:
        """フェーズに応じたエージェントを開始"""
        if phase == CoordinationPhase.PARTICIPANT_COLLECTION:
            await self._start_agent("participant_agent", "参加者収集")

        elif phase == CoordinationPhase.SCHEDULE_COORDINATION:
            await self._start_agent("scheduling_agent", "スケジュール調整")

        elif phase == CoordinationPhase.VENUE_COORDINATION:
            await self._start_agent("venue_agent", "会場検索・予約")

        elif phase == CoordinationPhase.CALENDAR_INTEGRATION:
            await self._start_agent("calendar_agent", "カレンダー統合")

    # 決定管理

    async def _make_workflow_decision(
        self,
        decision_type: str,
        options: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> WorkflowDecision:
        """ワークフロー決定を実行"""
        # 単純な決定ロジック（実際にはより複雑なアルゴリズムを使用）
        selected_option = options[0] if options else None
        confidence = 0.8  # 基本的な信頼度

        decision = WorkflowDecision(
            phase=self.coordination_session.current_phase,
            decision_type=decision_type,
            options=options,
            selected_option=selected_option,
            reasoning="基本的な選択アルゴリズムによる決定",
            confidence_score=confidence
        )

        self.workflow_decisions.append(decision)
        logger.info(f"ワークフロー決定: {decision_type} -> {selected_option}")

        return decision

    # ユーティリティメソッド

    async def _get_assigned_tasks(self, agent_name: str) -> List[str]:
        """エージェントに割り当てられたタスクを取得"""
        task_assignments = {
            "participant_agent": ["参加者収集", "確認状況管理", "リマインダー送信"],
            "scheduling_agent": ["時間調整", "スケジュール最適化", "競合解決"],
            "venue_agent": ["会場検索", "予約手続き", "代替案提示"],
            "calendar_agent": ["カレンダー作成", "招待送信", "会議室予約"]
        }
        return task_assignments.get(agent_name, [])

    async def _schedule_heartbeat(self) -> None:
        """定期ハートビート設定"""
        # 実装は簡略化 - 実際にはスケジューラーを使用
        await self.send_heartbeat()

    async def _handle_coordination_error(self, error: Exception) -> None:
        """調整エラーハンドリング"""
        logger.error(f"調整エラー: {error}")

        # エラー復旧戦略を実行
        await self._execute_error_recovery(error)

    async def _execute_error_recovery(self, error: Exception) -> None:
        """エラー復旧戦略実行"""
        error_type = type(error).__name__

        if "timeout" in error_type.lower():
            # タイムアウトエラーの場合はリトライ
            logger.info("タイムアウトエラー復旧: リトライを実行")

        elif "connection" in error_type.lower():
            # 接続エラーの場合は再接続
            logger.info("接続エラー復旧: 再接続を試行")

        else:
            # その他のエラーは手動介入が必要
            logger.warning("手動介入が必要なエラー")

    # その他のハンドラー（簡略化）

    async def _handle_start_agent_command(self, agent_name: str, message: AgentMessage) -> AgentMessage:
        task = message.payload.get("task")
        success = await self._start_agent(agent_name, task)
        return message.create_response(
            sender_id=self.agent_id,
            payload={"status": "success" if success else "failed"}
        )

    async def _handle_stop_agent_command(self, agent_name: str, message: AgentMessage) -> AgentMessage:
        success = await self._stop_agent(agent_name)
        return message.create_response(
            sender_id=self.agent_id,
            payload={"status": "success" if success else "failed"}
        )

    async def _handle_phase_transition_command(self, target_phase: str, message: AgentMessage) -> AgentMessage:
        try:
            phase = CoordinationPhase(target_phase)
            success = await self._transition_to_phase(phase)
            return message.create_response(
                sender_id=self.agent_id,
                payload={"status": "success" if success else "failed"}
            )
        except ValueError:
            return message.create_response(
                sender_id=self.agent_id,
                payload={"status": "error", "message": f"無効なフェーズ: {target_phase}"}
            )

    async def _handle_status_query(self, message: AgentMessage) -> AgentMessage:
        return message.create_response(
            sender_id=self.agent_id,
            payload=self.coordination_session.get_status_summary()
        )

    async def _handle_agent_status_query(self, agent_name: str, message: AgentMessage) -> AgentMessage:
        agent = self.managed_agents.get(agent_name)
        if agent:
            return message.create_response(
                sender_id=self.agent_id,
                payload=agent.dict()
            )
        else:
            return message.create_response(
                sender_id=self.agent_id,
                payload={"status": "error", "message": f"エージェントが見つかりません: {agent_name}"}
            )

    async def _process_agent_response(self, message: AgentMessage) -> None:
        """エージェントレスポンスの処理"""
        # 実装簡略化
        logger.debug(f"エージェントレスポンス処理: {message.sender_id}")

    async def _handle_agent_completion(self, message: AgentMessage) -> None:
        """エージェント完了処理"""
        agent_name = message.payload.get("agent_name")
        if agent_name and self.coordination_session.complete_agent(agent_name, message.payload.get("result")):
            await self.session_repository.update(self.coordination_session)

            # 次のフェーズに進む条件をチェック
            await self._check_phase_completion()

    async def _handle_agent_failure(self, message: AgentMessage) -> None:
        """エージェント失敗処理"""
        agent_name = message.payload.get("agent_name")
        error_message = message.payload.get("error_message", "不明なエラー")

        if agent_name and self.coordination_session.fail_agent(agent_name, error_message):
            await self.session_repository.update(self.coordination_session)

    async def _handle_user_confirmation(self, message: AgentMessage) -> None:
        """ユーザー確認処理"""
        # 実装簡略化
        logger.info("ユーザー確認受信")

    async def _handle_phase_ready(self, message: AgentMessage) -> None:
        """フェーズ準備完了処理"""
        # 実装簡略化
        logger.info("フェーズ準備完了")

    async def _check_phase_completion(self) -> None:
        """フェーズ完了条件チェック"""
        current_phase = self.coordination_session.current_phase

        # 簡単な完了条件チェック
        if current_phase in self.phase_transitions:
            next_phase = self.phase_transitions[current_phase]
            await self._transition_to_phase(next_phase)