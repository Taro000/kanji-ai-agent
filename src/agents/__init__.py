"""
エージェントパッケージ - Enhanced Slack Bot Event Organizer AI Agent

このパッケージには、イベント調整を自動化するマルチエージェントシステムが含まれています。
ADK（Agent Development Kit）フレームワークを使用して実装されています。
"""

from .base_agent import BaseAgent, AgentMessage, AgentCapability
from .coordination_agent import CoordinationAgent
from .participant_agent import ParticipantAgent
from .scheduling_agent import SchedulingAgent
from .venue_agent import VenueAgent
from .calendar_agent import CalendarAgent

__all__ = [
    # 基底クラス・インターフェース
    "BaseAgent",
    "AgentMessage",
    "AgentCapability",

    # 具体的なエージェント
    "CoordinationAgent",
    "ParticipantAgent",
    "SchedulingAgent",
    "VenueAgent",
    "CalendarAgent",
]