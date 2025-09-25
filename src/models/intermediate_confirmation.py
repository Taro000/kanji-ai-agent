"""
IntermediateConfirmation エンティティモデル

調整過程での主催者承認チェックポイントを表現します。
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import uuid4

from pydantic import BaseModel, Field, validator


class ConfirmationType(str, Enum):
    """確認タイプ列挙"""
    SCHEDULE_CONFIRMATION = "schedule_confirmation"    # スケジュール確認
    VENUE_CONFIRMATION = "venue_confirmation"          # 会場確認
    PARTICIPANT_CONFIRMATION = "participant_confirmation"  # 参加者確認
    FINAL_CONFIRMATION = "final_confirmation"          # 最終確認
    BUDGET_CONFIRMATION = "budget_confirmation"        # 予算確認
    CHANGE_CONFIRMATION = "change_confirmation"        # 変更確認


class ConfirmationStatus(str, Enum):
    """確認ステータス列挙"""
    PENDING = "pending"        # 確認待ち
    APPROVED = "approved"      # 承認済み
    REJECTED = "rejected"      # 拒否
    TIMEOUT = "timeout"       # タイムアウト
    CANCELLED = "cancelled"    # キャンセル


class ConfirmationOption(BaseModel):
    """確認オプション"""
    option_id: str = Field(default_factory=lambda: str(uuid4()))
    option_type: str = Field(..., description="オプションタイプ")
    title: str = Field(..., description="オプションタイトル")
    description: Optional[str] = Field(None, description="詳細説明")
    data: Dict[str, Any] = Field(default_factory=dict, description="オプション固有データ")
    recommended: bool = Field(default=False, description="推奨オプションか")
    cost_impact: Optional[str] = Field(None, description="コストへの影響")
    pros: List[str] = Field(default_factory=list, description="メリット")
    cons: List[str] = Field(default_factory=list, description="デメリット")

    def add_pro(self, pro: str) -> None:
        """メリットを追加"""
        if pro not in self.pros:
            self.pros.append(pro)

    def add_con(self, con: str) -> None:
        """デメリットを追加"""
        if con not in self.cons:
            self.cons.append(con)


class UserResponse(BaseModel):
    """ユーザー回答"""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    response_type: str = Field(..., description="回答タイプ")
    selected_option_id: Optional[str] = Field(None, description="選択されたオプションID")
    custom_input: Optional[str] = Field(None, description="カスタム入力")
    feedback: Optional[str] = Field(None, description="フィードバック")
    confidence_level: Optional[int] = Field(None, description="確信度（1-5）")

    @validator('confidence_level')
    def validate_confidence_level(cls, v):
        """確信度の検証"""
        if v is not None and (v < 1 or v > 5):
            raise ValueError('確信度は1-5の範囲である必要があります')
        return v


class IntermediateConfirmation(BaseModel):
    """中間確認エンティティ"""

    # 基本識別情報
    confirmation_id: str = Field(default_factory=lambda: str(uuid4()))
    event_id: str = Field(..., description="関連するイベントID")
    session_id: str = Field(..., description="関連する調整セッションID")

    # 確認情報
    confirmation_type: ConfirmationType = Field(..., description="確認タイプ")
    title: str = Field(..., description="確認タイトル")
    description: str = Field(..., description="確認内容の説明")
    urgency_level: str = Field(default="normal", description="緊急度（low, normal, high）")

    # オプション・選択肢
    proposed_options: List[ConfirmationOption] = Field(
        default_factory=list,
        description="提案されたオプション"
    )
    allow_custom_input: bool = Field(default=False, description="カスタム入力を許可するか")
    custom_input_prompt: Optional[str] = Field(None, description="カスタム入力のプロンプト")

    # 選択・回答
    selected_option: Optional[ConfirmationOption] = Field(None, description="選択されたオプション")
    user_responses: List[UserResponse] = Field(default_factory=list, description="ユーザー回答履歴")
    final_decision: Optional[str] = Field(None, description="最終決定内容")

    # ステータス・タイミング
    status: ConfirmationStatus = Field(default=ConfirmationStatus.PENDING, description="確認ステータス")
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    responded_at: Optional[datetime] = Field(None, description="回答時刻")
    timeout_at: Optional[datetime] = Field(None, description="タイムアウト時刻")

    # Slack通信情報
    thread_ts: str = Field(..., description="確認を要求したSlackスレッド")
    message_ts: Optional[str] = Field(None, description="確認メッセージのタイムスタンプ")
    reminder_sent_count: int = Field(default=0, description="リマインダー送信回数")
    last_reminder_at: Optional[datetime] = Field(None, description="最後のリマインダー送信時刻")

    # フィードバック・改善
    feedback: Optional[str] = Field(None, description="主催者からの追加フィードバック")
    satisfaction_rating: Optional[int] = Field(None, description="満足度評価（1-5）")
    improvement_suggestions: List[str] = Field(default_factory=list, description="改善提案")

    # 関連データ
    context_data: Dict[str, Any] = Field(default_factory=dict, description="コンテキストデータ")
    related_confirmations: List[str] = Field(default_factory=list, description="関連する確認ID")

    # メタデータ
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        """Pydantic設定"""
        use_enum_values = True
        validate_assignment = True
        arbitrary_types_allowed = True

    @validator('thread_ts')
    def validate_thread_ts(cls, v):
        """Slackスレッドタイムスタンプの形式検証"""
        import re
        if not re.match(r'^\d{10}\.\d{6}$', v):
            raise ValueError('Slackスレッドタイムスタンプは正しい形式である必要があります')
        return v

    @validator('urgency_level')
    def validate_urgency_level(cls, v):
        """緊急度の検証"""
        valid_levels = ["low", "normal", "high", "critical"]
        if v not in valid_levels:
            raise ValueError(f'緊急度は{valid_levels}のいずれかである必要があります')
        return v

    @validator('satisfaction_rating')
    def validate_satisfaction_rating(cls, v):
        """満足度評価の検証"""
        if v is not None and (v < 1 or v > 5):
            raise ValueError('満足度評価は1-5の範囲である必要があります')
        return v

    @validator('reminder_sent_count')
    def validate_reminder_count(cls, v):
        """リマインダー送信回数の検証"""
        if v < 0 or v > 10:
            raise ValueError('リマインダー送信回数は0-10回の範囲である必要があります')
        return v

    def update_timestamp(self) -> None:
        """更新タイムスタンプを現在時刻に設定"""
        self.updated_at = datetime.utcnow()

    def add_option(
        self,
        option_type: str,
        title: str,
        description: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        recommended: bool = False
    ) -> str:
        """オプションを追加"""
        option = ConfirmationOption(
            option_type=option_type,
            title=title,
            description=description,
            data=data or {},
            recommended=recommended
        )
        self.proposed_options.append(option)
        self.update_timestamp()
        return option.option_id

    def remove_option(self, option_id: str) -> bool:
        """オプションを削除"""
        for i, option in enumerate(self.proposed_options):
            if option.option_id == option_id:
                self.proposed_options.pop(i)
                self.update_timestamp()
                return True
        return False

    def mark_option_recommended(self, option_id: str) -> bool:
        """オプションを推奨にマーク"""
        for option in self.proposed_options:
            option.recommended = False  # 他のオプションの推奨を解除
            if option.option_id == option_id:
                option.recommended = True
                self.update_timestamp()
                return True
        return False

    def approve_option(self, option_id: str, feedback: Optional[str] = None) -> bool:
        """オプションを承認"""
        for option in self.proposed_options:
            if option.option_id == option_id:
                self.selected_option = option
                self.status = ConfirmationStatus.APPROVED
                self.responded_at = datetime.utcnow()
                if feedback:
                    self.feedback = feedback

                # 回答を記録
                response = UserResponse(
                    response_type="approval",
                    selected_option_id=option_id,
                    feedback=feedback
                )
                self.user_responses.append(response)
                self.update_timestamp()
                return True
        return False

    def reject_all_options(self, reason: Optional[str] = None) -> None:
        """全オプションを拒否"""
        self.status = ConfirmationStatus.REJECTED
        self.responded_at = datetime.utcnow()
        if reason:
            self.feedback = reason

        # 拒否回答を記録
        response = UserResponse(
            response_type="rejection",
            feedback=reason
        )
        self.user_responses.append(response)
        self.update_timestamp()

    def provide_custom_response(self, custom_input: str, feedback: Optional[str] = None) -> None:
        """カスタム回答を提供"""
        if not self.allow_custom_input:
            raise ValueError('カスタム入力は許可されていません')

        self.final_decision = custom_input
        self.status = ConfirmationStatus.APPROVED
        self.responded_at = datetime.utcnow()
        if feedback:
            self.feedback = feedback

        # カスタム回答を記録
        response = UserResponse(
            response_type="custom",
            custom_input=custom_input,
            feedback=feedback
        )
        self.user_responses.append(response)
        self.update_timestamp()

    def mark_timeout(self) -> None:
        """タイムアウトとしてマーク"""
        self.status = ConfirmationStatus.TIMEOUT
        self.responded_at = datetime.utcnow()
        self.update_timestamp()

    def cancel_confirmation(self, reason: Optional[str] = None) -> None:
        """確認をキャンセル"""
        self.status = ConfirmationStatus.CANCELLED
        if reason:
            self.feedback = reason
        self.update_timestamp()

    def send_reminder(self) -> None:
        """リマインダー送信を記録"""
        self.reminder_sent_count += 1
        self.last_reminder_at = datetime.utcnow()
        self.update_timestamp()

    def is_pending(self) -> bool:
        """確認待ち状態かチェック"""
        return self.status == ConfirmationStatus.PENDING

    def is_responded(self) -> bool:
        """回答済みかチェック"""
        return self.status in [ConfirmationStatus.APPROVED, ConfirmationStatus.REJECTED]

    def is_expired(self) -> bool:
        """期限切れかチェック"""
        return (
            self.timeout_at is not None and
            datetime.utcnow() > self.timeout_at and
            self.status == ConfirmationStatus.PENDING
        )

    def needs_reminder(self, reminder_interval_hours: int = 24, max_reminders: int = 3) -> bool:
        """リマインダーが必要かチェック"""
        if not self.is_pending():
            return False

        if self.reminder_sent_count >= max_reminders:
            return False

        if self.last_reminder_at is None:
            # 最初のリマインダー（要求から1時間後）
            hours_since_request = (datetime.utcnow() - self.requested_at).total_seconds() / 3600
            return hours_since_request >= 1

        # 前回のリマインダーからの経過時間
        hours_since_last_reminder = (
            datetime.utcnow() - self.last_reminder_at
        ).total_seconds() / 3600

        return hours_since_last_reminder >= reminder_interval_hours

    def get_recommended_option(self) -> Optional[ConfirmationOption]:
        """推奨オプションを取得"""
        for option in self.proposed_options:
            if option.recommended:
                return option
        return None

    def get_response_time_minutes(self) -> Optional[int]:
        """回答時間（分）を取得"""
        if self.responded_at:
            return int((self.responded_at - self.requested_at).total_seconds() / 60)
        return None

    def get_status_display(self) -> str:
        """ステータスの日本語表示"""
        status_display = {
            ConfirmationStatus.PENDING: "確認待ち",
            ConfirmationStatus.APPROVED: "承認済み",
            ConfirmationStatus.REJECTED: "拒否",
            ConfirmationStatus.TIMEOUT: "タイムアウト",
            ConfirmationStatus.CANCELLED: "キャンセル"
        }
        return status_display.get(self.status, "不明")

    def get_urgency_display(self) -> str:
        """緊急度の日本語表示"""
        urgency_display = {
            "low": "低",
            "normal": "通常",
            "high": "高",
            "critical": "緊急"
        }
        return urgency_display.get(self.urgency_level, "不明")

    def get_confirmation_type_display(self) -> str:
        """確認タイプの日本語表示"""
        type_display = {
            ConfirmationType.SCHEDULE_CONFIRMATION: "スケジュール確認",
            ConfirmationType.VENUE_CONFIRMATION: "会場確認",
            ConfirmationType.PARTICIPANT_CONFIRMATION: "参加者確認",
            ConfirmationType.FINAL_CONFIRMATION: "最終確認",
            ConfirmationType.BUDGET_CONFIRMATION: "予算確認",
            ConfirmationType.CHANGE_CONFIRMATION: "変更確認"
        }
        return type_display.get(self.confirmation_type, "不明")

    def generate_summary(self) -> Dict[str, Any]:
        """確認の概要を生成"""
        return {
            "confirmation_id": self.confirmation_id,
            "type": self.get_confirmation_type_display(),
            "title": self.title,
            "status": self.get_status_display(),
            "urgency": self.get_urgency_display(),
            "option_count": len(self.proposed_options),
            "recommended_option": self.get_recommended_option().title if self.get_recommended_option() else None,
            "response_time_minutes": self.get_response_time_minutes(),
            "reminder_count": self.reminder_sent_count,
            "requested_at": self.requested_at.strftime("%Y-%m-%d %H:%M"),
            "responded_at": self.responded_at.strftime("%Y-%m-%d %H:%M") if self.responded_at else None
        }

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換（Firestore保存用）"""
        return {
            "confirmation_id": self.confirmation_id,
            "event_id": self.event_id,
            "session_id": self.session_id,
            "confirmation_type": self.confirmation_type.value,
            "title": self.title,
            "description": self.description,
            "urgency_level": self.urgency_level,
            "proposed_options": [option.dict() for option in self.proposed_options],
            "allow_custom_input": self.allow_custom_input,
            "custom_input_prompt": self.custom_input_prompt,
            "selected_option": self.selected_option.dict() if self.selected_option else None,
            "user_responses": [response.dict() for response in self.user_responses],
            "final_decision": self.final_decision,
            "status": self.status.value,
            "requested_at": self.requested_at.isoformat(),
            "responded_at": self.responded_at.isoformat() if self.responded_at else None,
            "timeout_at": self.timeout_at.isoformat() if self.timeout_at else None,
            "thread_ts": self.thread_ts,
            "message_ts": self.message_ts,
            "reminder_sent_count": self.reminder_sent_count,
            "last_reminder_at": self.last_reminder_at.isoformat() if self.last_reminder_at else None,
            "feedback": self.feedback,
            "satisfaction_rating": self.satisfaction_rating,
            "improvement_suggestions": self.improvement_suggestions,
            "context_data": self.context_data,
            "related_confirmations": self.related_confirmations,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IntermediateConfirmation":
        """辞書から IntermediateConfirmation インスタンスを作成"""
        # datetimeフィールドの変換
        datetime_fields = [
            "requested_at", "responded_at", "timeout_at",
            "last_reminder_at", "created_at", "updated_at"
        ]
        for field in datetime_fields:
            if data.get(field):
                data[field] = datetime.fromisoformat(data[field])

        # proposed_optionsリストの変換
        if data.get("proposed_options"):
            data["proposed_options"] = [
                ConfirmationOption(**option_data)
                for option_data in data["proposed_options"]
            ]

        # selected_optionの変換
        if data.get("selected_option"):
            data["selected_option"] = ConfirmationOption(**data["selected_option"])

        # user_responsesリストの変換
        if data.get("user_responses"):
            responses = []
            for response_data in data["user_responses"]:
                if response_data.get("timestamp"):
                    response_data["timestamp"] = datetime.fromisoformat(response_data["timestamp"])
                responses.append(UserResponse(**response_data))
            data["user_responses"] = responses

        return cls(**data)