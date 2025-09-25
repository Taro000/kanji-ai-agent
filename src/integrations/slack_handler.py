"""
Slack Bolt SDK Event Handler - Slackイベント処理統合
"""

import asyncio
import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)


class SlackEventData(BaseModel):
    """Slackイベントデータ"""
    event_type: str
    user_id: str
    channel_id: str
    thread_ts: Optional[str] = None
    text: str
    timestamp: str
    team_id: str


class SlackMessage(BaseModel):
    """Slack送信メッセージ"""
    channel: str
    text: str
    thread_ts: Optional[str] = None
    blocks: Optional[List[Dict[str, Any]]] = None
    attachments: Optional[List[Dict[str, Any]]] = None


class SlackUserInfo(BaseModel):
    """Slackユーザー情報"""
    user_id: str
    name: str
    email: Optional[str] = None
    display_name: str
    real_name: str
    is_bot: bool = False


class BotMentionEvent(BaseModel):
    """ボットメンション検出結果"""
    is_mention: bool
    intent: str  # create_event, check_status, help
    parameters: Dict[str, Any] = Field(default_factory=dict)
    confidence: float


class DMWorkflowState(BaseModel):
    """DM workflow状態"""
    user_id: str
    conversation_id: str
    current_step: str
    step_data: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class SlackEventHandler:
    """
    Slack Bolt SDK統合イベントハンドラー
    - イベント検証とルーティング
    - ボットメンション解析
    - DM workflow管理
    - 日本語自然言語理解
    """

    def __init__(self, bot_token: str, signing_secret: str):
        self.bot_token = bot_token
        self.signing_secret = signing_secret

        # イベントハンドラー登録
        self.event_handlers: Dict[str, Callable] = {}

        # DM workflow状態管理
        self.dm_workflows: Dict[str, DMWorkflowState] = {}

        # 日本語意図解析パターン
        self.intent_patterns = {
            "create_event": [
                re.compile(r"(イベント|飲み会|会議|勉強会).*(作成|作って|開催|企画)", re.IGNORECASE),
                re.compile(r"(みんなで|一緒に).*(食事|飲み|勉強)", re.IGNORECASE),
                re.compile(r"(新しい|新規).*(イベント|企画)", re.IGNORECASE)
            ],
            "check_status": [
                re.compile(r"(状況|状態|進捗).*(確認|教えて|どう)", re.IGNORECASE),
                re.compile(r"(イベント).*(どうなった|進んでる)", re.IGNORECASE),
                re.compile(r"(参加者|出席者).*(状況|どう)", re.IGNORECASE)
            ],
            "help": [
                re.compile(r"(ヘルプ|使い方|help)", re.IGNORECASE),
                re.compile(r"(何が|どんな).*(できる|機能)", re.IGNORECASE),
                re.compile(r"(コマンド|操作).*(教えて|説明)", re.IGNORECASE)
            ],
            "yes_confirmation": [
                re.compile(r"^(はい|yes|ok|おけ|いいよ|大丈夫|参加)$", re.IGNORECASE),
                re.compile(r"参加し(ます|たい)", re.IGNORECASE)
            ],
            "no_confirmation": [
                re.compile(r"^(いいえ|no|ng|だめ|無理|参加しない)$", re.IGNORECASE),
                re.compile(r"参加でき(ない|ません)", re.IGNORECASE)
            ],
            "schedule_preference": [
                re.compile(r"(\d{1,2}時|\d{1,2}:\d{2})", re.IGNORECASE),
                re.compile(r"(午前|午後|朝|昼|夜|夕方)", re.IGNORECASE),
                re.compile(r"(月|火|水|木|金|土|日)曜", re.IGNORECASE)
            ]
        }

        # レスポンステンプレート
        self.response_templates = {
            "event_creation_started": "イベント作成を開始します！詳細をDMでお聞きしますね。",
            "status_check": "現在の状況をお調べします。少々お待ちください。",
            "help_message": self._get_help_message(),
            "dm_introduction": "こんにちは！イベントの詳細をお聞きします。\n\nまず、どのようなイベントを開催したいですか？\n例：チーム飲み会、勉強会、ランチ会など",
            "confirmation_request": "イベント「{title}」への参加確認です。\n\n参加されますか？\n「はい」または「いいえ」でお答えください。",
            "unknown_intent": "申し訳ありませんが、よく理解できませんでした。\n「ヘルプ」と入力すると使い方をご確認いただけます。"
        }

    def register_event_handler(self, event_type: str, handler: Callable):
        """イベントハンドラー登録"""
        self.event_handlers[event_type] = handler

    async def handle_slack_event(self, event_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Slackイベント処理メイン"""
        try:
            # イベントデータ解析
            slack_event = self._parse_slack_event(event_data)

            # イベントタイプ別処理
            if slack_event.event_type == "app_mention":
                return await self._handle_bot_mention(slack_event)
            elif slack_event.event_type == "message" and slack_event.channel_id.startswith("D"):
                return await self._handle_direct_message(slack_event)
            elif slack_event.event_type == "message" and slack_event.thread_ts:
                return await self._handle_thread_reply(slack_event)
            else:
                logger.info(f"未処理イベントタイプ: {slack_event.event_type}")
                return None

        except Exception as e:
            logger.error(f"Slackイベント処理エラー: {str(e)}")
            return self._create_error_response(str(e))

    async def _handle_bot_mention(self, event: SlackEventData) -> Dict[str, Any]:
        """ボットメンション処理"""
        logger.info(f"ボットメンション検出: {event.text}")

        # 意図解析
        mention_analysis = self._analyze_bot_mention(event.text)

        if mention_analysis.intent == "create_event":
            # イベント作成開始
            response = await self._start_event_creation_workflow(event)
        elif mention_analysis.intent == "check_status":
            # 状況確認
            response = await self._handle_status_check(event)
        elif mention_analysis.intent == "help":
            # ヘルプ表示
            response = self._create_help_response(event)
        else:
            # 不明な意図
            response = self._create_unknown_intent_response(event)

        # 登録されたハンドラーに通知
        if "app_mention" in self.event_handlers:
            await self.event_handlers["app_mention"](event, mention_analysis)

        return response

    async def _handle_direct_message(self, event: SlackEventData) -> Dict[str, Any]:
        """DM処理"""
        logger.info(f"DM受信: {event.user_id}")

        # 既存workflow確認
        workflow = self.dm_workflows.get(event.user_id)

        if workflow:
            # 既存workflowの継続
            response = await self._continue_dm_workflow(event, workflow)
        else:
            # 新規DM（単発確認など）
            response = await self._handle_standalone_dm(event)

        # 登録されたハンドラーに通知
        if "direct_message" in self.event_handlers:
            await self.event_handlers["direct_message"](event)

        return response

    async def _handle_thread_reply(self, event: SlackEventData) -> Dict[str, Any]:
        """スレッド返信処理"""
        logger.info(f"スレッド返信: {event.thread_ts}")

        # スレッド文脈解析
        thread_context = await self._analyze_thread_context(event)

        if thread_context.get("is_event_discussion"):
            # イベント関連スレッド
            response = await self._handle_event_thread_reply(event, thread_context)
        else:
            # 一般的なスレッド返信
            response = await self._handle_general_thread_reply(event)

        # 登録されたハンドラーに通知
        if "thread_reply" in self.event_handlers:
            await self.event_handlers["thread_reply"](event, thread_context)

        return response

    def _parse_slack_event(self, event_data: Dict[str, Any]) -> SlackEventData:
        """Slackイベントデータ解析"""
        event = event_data.get("event", {})

        return SlackEventData(
            event_type=event.get("type", "unknown"),
            user_id=event.get("user", ""),
            channel_id=event.get("channel", ""),
            thread_ts=event.get("thread_ts"),
            text=event.get("text", ""),
            timestamp=event.get("ts", ""),
            team_id=event_data.get("team_id", "")
        )

    def _analyze_bot_mention(self, text: str) -> BotMentionEvent:
        """ボットメンション意図解析"""
        # ボット名を除去
        clean_text = re.sub(r"<@[UW][A-Z0-9]+>", "", text).strip()

        max_confidence = 0.0
        detected_intent = "unknown"
        parameters = {}

        # 各意図パターンをチェック
        for intent, patterns in self.intent_patterns.items():
            for pattern in patterns:
                if pattern.search(clean_text):
                    confidence = 0.8  # 基本信頼度

                    # パターン特化の信頼度調整
                    if intent == "create_event":
                        confidence += 0.1
                        parameters = self._extract_event_parameters(clean_text)

                    if confidence > max_confidence:
                        max_confidence = confidence
                        detected_intent = intent

        return BotMentionEvent(
            is_mention=True,
            intent=detected_intent,
            parameters=parameters,
            confidence=max_confidence
        )

    def _extract_event_parameters(self, text: str) -> Dict[str, Any]:
        """イベントパラメーター抽出"""
        parameters = {}

        # イベントタイプ検出
        if re.search(r"(飲み会|懇親会|歓送迎会)", text):
            parameters["event_type"] = "dining"
        elif re.search(r"(会議|ミーティング|打合せ)", text):
            parameters["event_type"] = "meeting"
        elif re.search(r"(勉強会|セミナー|研修)", text):
            parameters["event_type"] = "study"

        # 日時情報抽出
        date_match = re.search(r"(\d{1,2})/(\d{1,2})|(\d{1,2})月(\d{1,2})日", text)
        if date_match:
            parameters["suggested_date"] = date_match.group(0)

        time_match = re.search(r"(\d{1,2}):(\d{2})|(\d{1,2})時", text)
        if time_match:
            parameters["suggested_time"] = time_match.group(0)

        return parameters

    async def _start_event_creation_workflow(self, event: SlackEventData) -> Dict[str, Any]:
        """イベント作成workflow開始"""
        # DM開始
        dm_response = await self._send_dm_to_user(
            event.user_id,
            self.response_templates["dm_introduction"]
        )

        # Workflow状態初期化
        workflow = DMWorkflowState(
            user_id=event.user_id,
            conversation_id=f"event_creation_{event.timestamp}",
            current_step="event_type_input",
            step_data={"channel_id": event.channel_id},
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        self.dm_workflows[event.user_id] = workflow

        # チャネルへの応答
        return self._create_slack_response(
            event.channel_id,
            self.response_templates["event_creation_started"],
            event.thread_ts
        )

    async def _continue_dm_workflow(self, event: SlackEventData, workflow: DMWorkflowState) -> Dict[str, Any]:
        """DM workflow継続"""
        step_handler = {
            "event_type_input": self._handle_event_type_input,
            "title_input": self._handle_title_input,
            "participant_input": self._handle_participant_input,
            "schedule_input": self._handle_schedule_input,
            "confirmation": self._handle_workflow_confirmation
        }.get(workflow.current_step)

        if step_handler:
            return await step_handler(event, workflow)
        else:
            logger.warning(f"不明なworkflowステップ: {workflow.current_step}")
            return self._create_slack_response(
                event.channel_id,
                "申し訳ございません。処理中にエラーが発生しました。"
            )

    async def _handle_event_type_input(self, event: SlackEventData, workflow: DMWorkflowState) -> Dict[str, Any]:
        """イベントタイプ入力処理"""
        event_type = "dining"  # デフォルト

        if re.search(r"(会議|ミーティング|勉強会)", event.text):
            event_type = "meeting"

        workflow.step_data["event_type"] = event_type
        workflow.current_step = "title_input"
        workflow.updated_at = datetime.now()

        return self._create_slack_response(
            event.channel_id,
            "イベントのタイトルを教えてください。\n例：チーム懇親会、月次会議など"
        )

    async def _handle_title_input(self, event: SlackEventData, workflow: DMWorkflowState) -> Dict[str, Any]:
        """タイトル入力処理"""
        workflow.step_data["title"] = event.text
        workflow.current_step = "participant_input"
        workflow.updated_at = datetime.now()

        return self._create_slack_response(
            event.channel_id,
            "参加者を教えてください。\n@マークで参加者をメンションするか、「全員」「チーム」などでも結構です。"
        )

    async def _handle_participant_input(self, event: SlackEventData, workflow: DMWorkflowState) -> Dict[str, Any]:
        """参加者入力処理"""
        # メンション抽出
        mentions = re.findall(r"<@([UW][A-Z0-9]+)>", event.text)

        workflow.step_data["participants"] = mentions
        workflow.step_data["participant_text"] = event.text
        workflow.current_step = "schedule_input"
        workflow.updated_at = datetime.now()

        return self._create_slack_response(
            event.channel_id,
            "希望する日時を教えてください。\n例：今度の金曜日の18時から、来週の火曜日など"
        )

    async def _handle_schedule_input(self, event: SlackEventData, workflow: DMWorkflowState) -> Dict[str, Any]:
        """スケジュール入力処理"""
        workflow.step_data["schedule_text"] = event.text
        workflow.current_step = "confirmation"
        workflow.updated_at = datetime.now()

        # 入力内容確認
        summary = f"""
イベント内容を確認してください：

タイトル: {workflow.step_data.get('title')}
タイプ: {workflow.step_data.get('event_type')}
参加者: {workflow.step_data.get('participant_text')}
希望日時: {workflow.step_data.get('schedule_text')}

この内容でイベント作成を開始しますか？
「はい」または「いいえ」でお答えください。
"""

        return self._create_slack_response(event.channel_id, summary)

    async def _handle_workflow_confirmation(self, event: SlackEventData, workflow: DMWorkflowState) -> Dict[str, Any]:
        """workflow確認処理"""
        if re.search(r"(はい|yes|ok)", event.text, re.IGNORECASE):
            # 承認 - 実際のイベント作成プロセス開始
            await self._trigger_event_creation(workflow)

            # workflow完了
            del self.dm_workflows[event.user_id]

            return self._create_slack_response(
                event.channel_id,
                "イベント作成を開始しました！参加者への確認を行います。"
            )
        else:
            # 拒否 - workflow終了
            del self.dm_workflows[event.user_id]

            return self._create_slack_response(
                event.channel_id,
                "イベント作成をキャンセルしました。"
            )

    async def _trigger_event_creation(self, workflow: DMWorkflowState):
        """実際のイベント作成プロセス開始"""
        # Coordination Agentに作成依頼送信
        if "event_creation_trigger" in self.event_handlers:
            await self.event_handlers["event_creation_trigger"](workflow.step_data)

    async def _handle_status_check(self, event: SlackEventData) -> Dict[str, Any]:
        """状況確認処理"""
        # 状況確認ハンドラー呼び出し
        if "status_check" in self.event_handlers:
            status_info = await self.event_handlers["status_check"](event.channel_id)

            if status_info:
                return self._create_slack_response(
                    event.channel_id,
                    f"現在の状況：\n{status_info}",
                    event.thread_ts
                )

        return self._create_slack_response(
            event.channel_id,
            self.response_templates["status_check"],
            event.thread_ts
        )

    async def _handle_standalone_dm(self, event: SlackEventData) -> Dict[str, Any]:
        """単発DM処理"""
        # 確認応答パターン検出
        if re.search(r"(はい|いいえ|yes|no)", event.text, re.IGNORECASE):
            # 参加確認への応答の可能性
            if "participation_response" in self.event_handlers:
                await self.event_handlers["participation_response"](event)

        return self._create_slack_response(
            event.channel_id,
            "ご連絡ありがとうございます。内容を確認いたします。"
        )

    async def _analyze_thread_context(self, event: SlackEventData) -> Dict[str, Any]:
        """スレッド文脈解析"""
        # Mock実装：実際にはスレッド履歴を分析
        return {
            "is_event_discussion": True,
            "event_id": "mock_event_id",
            "discussion_type": "schedule_coordination"
        }

    async def _handle_event_thread_reply(self, event: SlackEventData, context: Dict[str, Any]) -> Dict[str, Any]:
        """イベントスレッド返信処理"""
        if "event_thread_reply" in self.event_handlers:
            await self.event_handlers["event_thread_reply"](event, context)

        return {"processed": True}

    async def _handle_general_thread_reply(self, event: SlackEventData) -> Dict[str, Any]:
        """一般スレッド返信処理"""
        return {"processed": True}

    async def _send_dm_to_user(self, user_id: str, message: str) -> Dict[str, Any]:
        """ユーザーにDM送信（Mock）"""
        logger.info(f"DM送信: {user_id} - {message}")
        # 実際の実装では、Slack APIを使用してDM送信
        return {"sent": True}

    def _create_slack_response(self, channel: str, text: str, thread_ts: Optional[str] = None) -> Dict[str, Any]:
        """Slack応答作成"""
        response = {
            "channel": channel,
            "text": text
        }

        if thread_ts:
            response["thread_ts"] = thread_ts

        return response

    def _create_help_response(self, event: SlackEventData) -> Dict[str, Any]:
        """ヘルプ応答作成"""
        return self._create_slack_response(
            event.channel_id,
            self.response_templates["help_message"],
            event.thread_ts
        )

    def _create_unknown_intent_response(self, event: SlackEventData) -> Dict[str, Any]:
        """不明意図応答作成"""
        return self._create_slack_response(
            event.channel_id,
            self.response_templates["unknown_intent"],
            event.thread_ts
        )

    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """エラー応答作成"""
        return {
            "error": True,
            "message": error_message
        }

    def _get_help_message(self) -> str:
        """ヘルプメッセージ取得"""
        return """
📅 イベント企画ボットの使い方

【イベント作成】
「@bot イベント作って」「飲み会企画して」など

【状況確認】
「@bot 状況教えて」「進捗どう？」など

【機能】
• 参加者への自動確認DM
• スケジュール最適化
• 会場検索と予約
• カレンダー登録

何かご不明な点があれば、お気軽にお声かけください！
"""


class SlackMessageSender:
    """
    Slack メッセージ送信管理
    - フォーマット済みメッセージ送信
    - ブロック形式メッセージ
    - 添付ファイル対応
    """

    def __init__(self, bot_token: str):
        self.bot_token = bot_token

    async def send_participation_request(self, user_id: str, event_info: Dict[str, Any]) -> bool:
        """参加確認リクエスト送信"""
        message = f"""
🎉 イベント参加のお誘い

【イベント名】{event_info.get('title', 'イベント')}
【日時】{event_info.get('date_time', '調整中')}
【場所】{event_info.get('venue', '未定')}

ご参加いただけますでしょうか？
「はい」または「いいえ」でお答えください。
"""

        return await self._send_dm(user_id, message)

    async def send_schedule_confirmation(self, user_id: str, schedule_options: List[str]) -> bool:
        """スケジュール確認送信"""
        options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(schedule_options)])

        message = f"""
📅 スケジュール確認

以下の候補からご都合の良い時間を選んでください：

{options_text}

番号でお答えください（例：1）
"""

        return await self._send_dm(user_id, message)

    async def send_event_update(self, channel_id: str, update_info: Dict[str, Any]) -> bool:
        """イベント更新通知送信"""
        message = f"""
📢 イベント更新情報

{update_info.get('message', 'イベント情報が更新されました。')}
"""

        return await self._send_channel_message(channel_id, message)

    async def _send_dm(self, user_id: str, message: str) -> bool:
        """DM送信（Mock）"""
        logger.info(f"DM送信: {user_id}")
        # 実際の実装では、Slack APIを使用
        return True

    async def _send_channel_message(self, channel_id: str, message: str) -> bool:
        """チャンネルメッセージ送信（Mock）"""
        logger.info(f"チャンネルメッセージ送信: {channel_id}")
        # 実際の実装では、Slack APIを使用
        return True