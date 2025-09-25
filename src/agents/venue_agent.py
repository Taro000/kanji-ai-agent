"""
会場エージェント (Venue Agent)

Google Places APIとぐるなびAPIを使用した会場検索、
適合性評価、予約管理、フォールバック戦略を担当します。
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
import asyncio

from pydantic import BaseModel, Field

from ..models import (
    Event, EventType, Venue, VenueType, BookingStatus, PriceLevel,
    VenueFeature, BusinessHours
)
from ..models.repository import VenueRepository, EventRepository
from .base_agent import (
    BaseAgent, AgentMessage, AgentCapability, AgentStatus,
    MessageType, MessagePriority
)

logger = logging.getLogger(__name__)


class VenueSearchCriteria(BaseModel):
    """会場検索条件"""
    event_type: EventType = Field(..., description="イベントタイプ")
    participant_count: int = Field(..., description="参加者数")
    datetime: datetime = Field(..., description="イベント日時")
    duration_minutes: int = Field(..., description="イベント時間（分）")
    budget_per_person: Optional[int] = Field(None, description="一人当たり予算")
    location_hint: str = Field(default="東京", description="場所のヒント")
    required_features: List[str] = Field(default_factory=list, description="必須設備")
    accessibility_required: bool = Field(default=False, description="バリアフリー要求")


class VenueSearchResult(BaseModel):
    """会場検索結果"""
    venue: Venue = Field(..., description="会場情報")
    source_api: str = Field(..., description="データソース（places/gurume）")
    suitability_score: float = Field(..., description="適合性スコア（0.0-1.0）")
    availability_confirmed: bool = Field(default=False, description="空き状況確認済み")
    booking_required: bool = Field(default=True, description="予約が必要か")
    estimated_total_cost: Optional[int] = Field(None, description="総予算見積もり")
    notes: List[str] = Field(default_factory=list, description="注意事項")


class APIFailureRecord(BaseModel):
    """API失敗記録"""
    api_name: str = Field(..., description="API名")
    failure_time: datetime = Field(default_factory=datetime.utcnow)
    error_type: str = Field(..., description="エラータイプ")
    error_message: str = Field(..., description="エラーメッセージ")
    retry_count: int = Field(default=0, description="リトライ回数")


class VenueAgent(BaseAgent):
    """会場エージェント - マルチAPI会場検索と予約管理"""

    def __init__(
        self,
        event_id: str,
        session_id: str,
        venue_repository: Optional[VenueRepository] = None,
        event_repository: Optional[EventRepository] = None,
        google_places_api_key: Optional[str] = None,
        gurume_api_key: Optional[str] = None
    ):
        """
        会場エージェントを初期化

        Args:
            event_id: 関連するイベントID
            session_id: 関連するセッションID
            venue_repository: 会場リポジトリ
            event_repository: イベントリポジトリ
            google_places_api_key: Google Places API キー
            gurume_api_key: ぐるなび API キー
        """
        capabilities = [
            AgentCapability(
                capability_name="multi_api_venue_search",
                description="複数APIを使用した会場検索",
                input_types=["search_criteria", "location_coordinates"],
                output_types=["venue_list", "search_results"],
                dependencies=[],
                is_async=True,
                estimated_duration_ms=3000
            ),
            AgentCapability(
                capability_name="venue_suitability_analysis",
                description="会場の適合性評価とスコアリング",
                input_types=["venue_details", "event_requirements"],
                output_types=["suitability_score", "recommendation"],
                dependencies=["multi_api_venue_search"],
                is_async=True,
                estimated_duration_ms=500
            ),
            AgentCapability(
                capability_name="booking_management",
                description="会場予約の管理と追跡",
                input_types=["venue_selection", "booking_details"],
                output_types=["booking_status", "confirmation"],
                dependencies=["venue_suitability_analysis"],
                is_async=True,
                estimated_duration_ms=2000
            ),
            AgentCapability(
                capability_name="fallback_strategy",
                description="API失敗時のフォールバック戦略",
                input_types=["api_failure", "search_criteria"],
                output_types=["alternative_search", "manual_intervention"],
                dependencies=["multi_api_venue_search"],
                is_async=True,
                estimated_duration_ms=1000
            )
        ]

        super().__init__(
            agent_id=f"venue_agent_{event_id}",
            name="会場エージェント",
            description="マルチAPI会場検索と予約管理",
            capabilities=capabilities,
            event_id=event_id,
            session_id=session_id
        )

        # リポジトリ
        self.venue_repository = venue_repository or VenueRepository(
            collection_name="venues",
            model_class=Venue
        )
        self.event_repository = event_repository or EventRepository(
            collection_name="events",
            model_class=Event
        )

        # API設定
        self.google_places_api_key = google_places_api_key
        self.gurume_api_key = gurume_api_key

        # 状態管理
        self.current_event: Optional[Event] = None
        self.search_criteria: Optional[VenueSearchCriteria] = None
        self.search_results: List[VenueSearchResult] = []
        self.selected_venue: Optional[Venue] = None
        self.api_failures: List[APIFailureRecord] = []

        # API優先順位（1が最高優先度）
        self.api_priority = {
            "google_places": 1,
            "gurume": 2,
            "manual_fallback": 99
        }

        # イベントタイプ別検索設定
        self.search_settings = {
            EventType.DINING: {
                "venue_types": ["restaurant", "cafe", "bar"],
                "google_places_types": ["restaurant", "cafe", "meal_takeaway"],
                "gurume_categories": ["RSFST08000", "RSFST09000"],  # 和食、洋食
                "required_features": ["食事提供"],
                "search_radius": 2000  # 2km
            },
            EventType.STUDY: {
                "venue_types": ["meeting_room", "cafe", "external"],
                "google_places_types": ["library", "university", "cafe"],
                "gurume_categories": [],  # 勉強会ではぐるなび使用しない
                "required_features": ["WiFi", "静かな環境"],
                "search_radius": 5000  # 5km
            },
            EventType.MEETING: {
                "venue_types": ["meeting_room", "external"],
                "google_places_types": ["lodging", "conference_center"],
                "gurume_categories": [],
                "required_features": ["プロジェクター", "WiFi", "会議設備"],
                "search_radius": 10000  # 10km
            }
        }

    async def _initialize_impl(self) -> None:
        """会場エージェント固有の初期化"""
        try:
            # イベント情報をロード
            self.current_event = await self.event_repository.get_by_id(self.event_id)
            if not self.current_event:
                raise ValueError(f"イベントが見つかりません: {self.event_id}")

            # 検索条件を準備
            await self._prepare_search_criteria()

            # メッセージハンドラー登録
            self.register_handler(MessageType.COMMAND, self._handle_command)
            self.register_handler(MessageType.QUERY, self._handle_query)
            self.register_handler(MessageType.EVENT, self._handle_event)

            logger.info(f"会場エージェント初期化完了: {self.current_event.event_type}タイプのイベント")

        except Exception as e:
            logger.error(f"会場エージェント初期化エラー: {e}")
            raise

    async def _start_impl(self) -> None:
        """会場エージェント開始処理"""
        try:
            # 会場検索を開始
            await self._search_venues()

            # 検索結果を評価
            await self._evaluate_search_results()

            # 最適な会場を選択
            await self._select_best_venue()

            logger.info(f"会場エージェント開始: {len(self.search_results)}件の候補を検索")

        except Exception as e:
            logger.error(f"会場エージェント開始エラー: {e}")
            raise

    async def _stop_impl(self) -> None:
        """会場エージェント停止処理"""
        try:
            # 選択された会場を保存
            if self.selected_venue:
                await self.venue_repository.create(self.selected_venue)

                # イベントに会場情報を設定
                self.current_event.venue_id = self.selected_venue.venue_id
                await self.event_repository.update(self.current_event)

            # 完了報告を送信
            await self._send_completion_report()

            logger.info(f"会場エージェント停止完了: {self.agent_id}")

        except Exception as e:
            logger.error(f"会場エージェント停止エラー: {e}")
            raise

    # 検索条件準備

    async def _prepare_search_criteria(self) -> None:
        """検索条件を準備"""
        if not self.current_event.scheduled_datetime:
            raise ValueError("イベント日時が設定されていません")

        # 参加者数を取得（簡略化）
        participant_count = self.current_event.get_participant_count()
        if participant_count == 0:
            participant_count = 5  # デフォルト値

        self.search_criteria = VenueSearchCriteria(
            event_type=self.current_event.event_type,
            participant_count=participant_count,
            datetime=self.current_event.scheduled_datetime,
            duration_minutes=self.current_event.duration_minutes or 120,
            budget_per_person=3000,  # デフォルト予算
            location_hint="東京駅周辺",  # 実際はイベント詳細から取得
            required_features=self.search_settings[self.current_event.event_type]["required_features"],
            accessibility_required=False
        )

        logger.info(f"検索条件準備完了: {participant_count}人、{self.current_event.event_type}")

    # 会場検索

    async def _search_venues(self) -> List[VenueSearchResult]:
        """会場検索を実行"""
        logger.info("会場検索開始")
        all_results = []

        # 並列でAPI検索を実行
        search_tasks = []

        if self._should_use_api("google_places"):
            search_tasks.append(self._search_google_places())

        if self._should_use_api("gurume"):
            search_tasks.append(self._search_gurume())

        # 並列実行
        if search_tasks:
            results_lists = await asyncio.gather(*search_tasks, return_exceptions=True)

            for result in results_lists:
                if isinstance(result, Exception):
                    logger.error(f"API検索エラー: {result}")
                    await self._record_api_failure("unknown", str(result))
                elif isinstance(result, list):
                    all_results.extend(result)

        # フォールバック検索
        if not all_results:
            logger.warning("全API検索が失敗、フォールバック検索を実行")
            fallback_results = await self._fallback_search()
            all_results.extend(fallback_results)

        self.search_results = all_results
        logger.info(f"会場検索完了: {len(all_results)}件の候補")

        return all_results

    def _should_use_api(self, api_name: str) -> bool:
        """APIを使用すべきかチェック"""
        # 最近の失敗をチェック
        recent_failures = [
            f for f in self.api_failures
            if f.api_name == api_name and
            (datetime.utcnow() - f.failure_time).total_seconds() < 300  # 5分以内
        ]

        if len(recent_failures) >= 3:
            logger.warning(f"API {api_name} は最近失敗が多いためスキップ")
            return False

        # API設定チェック
        if api_name == "google_places" and not self.google_places_api_key:
            return False
        if api_name == "gurume" and not self.gurume_api_key:
            return False

        # イベントタイプ適合性チェック
        search_setting = self.search_settings[self.current_event.event_type]
        if api_name == "gurume" and not search_setting["gurume_categories"]:
            return False

        return True

    async def _search_google_places(self) -> List[VenueSearchResult]:
        """Google Places APIで検索"""
        logger.info("Google Places API検索開始")
        results = []

        try:
            # 実際のAPI呼び出しは簡略化（モック実装）
            mock_places_results = await self._mock_google_places_search()

            for place_data in mock_places_results:
                venue = await self._convert_places_to_venue(place_data)
                suitability_score = venue.calculate_suitability_score(
                    self.search_criteria.participant_count,
                    self.search_criteria.budget_per_person,
                    self.search_criteria.required_features
                )

                result = VenueSearchResult(
                    venue=venue,
                    source_api="google_places",
                    suitability_score=suitability_score,
                    estimated_total_cost=venue.estimated_cost_per_person * self.search_criteria.participant_count if venue.estimated_cost_per_person else None
                )
                results.append(result)

            logger.info(f"Google Places検索完了: {len(results)}件")

        except Exception as e:
            logger.error(f"Google Places API検索エラー: {e}")
            await self._record_api_failure("google_places", str(e))

        return results

    async def _search_gurume(self) -> List[VenueSearchResult]:
        """ぐるなびAPIで検索"""
        logger.info("ぐるなびAPI検索開始")
        results = []

        try:
            # 実際のAPI呼び出しは簡略化（モック実装）
            mock_gurume_results = await self._mock_gurume_search()

            for restaurant_data in mock_gurume_results:
                venue = await self._convert_gurume_to_venue(restaurant_data)
                suitability_score = venue.calculate_suitability_score(
                    self.search_criteria.participant_count,
                    self.search_criteria.budget_per_person,
                    self.search_criteria.required_features
                )

                result = VenueSearchResult(
                    venue=venue,
                    source_api="gurume",
                    suitability_score=suitability_score,
                    estimated_total_cost=venue.estimated_cost_per_person * self.search_criteria.participant_count if venue.estimated_cost_per_person else None
                )
                results.append(result)

            logger.info(f"ぐるなび検索完了: {len(results)}件")

        except Exception as e:
            logger.error(f"ぐるなびAPI検索エラー: {e}")
            await self._record_api_failure("gurume", str(e))

        return results

    async def _fallback_search(self) -> List[VenueSearchResult]:
        """フォールバック検索（手動候補）"""
        logger.info("フォールバック検索開始")
        results = []

        # 手動で定義された候補会場
        fallback_venues = [
            {
                "name": "会議室A（フォールバック）",
                "address": "東京都千代田区",
                "venue_type": VenueType.MEETING_ROOM,
                "capacity": 20,
                "estimated_cost": 2000
            },
            {
                "name": "カフェB（フォールバック）",
                "address": "東京都港区",
                "venue_type": VenueType.RESTAURANT,
                "capacity": 15,
                "estimated_cost": 1500
            }
        ]

        for venue_data in fallback_venues:
            venue = Venue(
                event_id=self.event_id,
                venue_type=venue_data["venue_type"],
                name=venue_data["name"],
                address=venue_data["address"],
                capacity=venue_data["capacity"],
                estimated_cost_per_person=venue_data["estimated_cost"],
                booking_status=BookingStatus.MANUAL_REQUIRED
            )

            # 手動予約が必要であることを明記
            venue.admin_notes = "API検索失敗のためフォールバック候補。手動確認が必要。"

            suitability_score = venue.calculate_suitability_score(
                self.search_criteria.participant_count,
                self.search_criteria.budget_per_person,
                self.search_criteria.required_features
            )

            result = VenueSearchResult(
                venue=venue,
                source_api="manual_fallback",
                suitability_score=suitability_score * 0.7,  # フォールバックは減点
                booking_required=True,
                notes=["手動確認が必要", "API検索失敗のためのフォールバック候補"]
            )
            results.append(result)

        logger.info(f"フォールバック検索完了: {len(results)}件")
        return results

    # モック実装（実際にはAPIクライアントを使用）

    async def _mock_google_places_search(self) -> List[Dict[str, Any]]:
        """Google Places API検索のモック実装"""
        await asyncio.sleep(0.5)  # API呼び出しをシミュレート

        return [
            {
                "place_id": "mock_place_1",
                "name": "イタリアンレストラン Roma",
                "formatted_address": "東京都千代田区丸の内1-1-1",
                "rating": 4.2,
                "price_level": 2,
                "types": ["restaurant", "food", "establishment"],
                "geometry": {"location": {"lat": 35.6812, "lng": 139.7671}},
                "user_ratings_total": 150
            },
            {
                "place_id": "mock_place_2",
                "name": "カフェ&コワーキング Space",
                "formatted_address": "東京都港区新橋2-2-2",
                "rating": 4.0,
                "price_level": 1,
                "types": ["cafe", "establishment"],
                "geometry": {"location": {"lat": 35.6684, "lng": 139.7587}},
                "user_ratings_total": 89
            }
        ]

    async def _mock_gurume_search(self) -> List[Dict[str, Any]]:
        """ぐるなびAPI検索のモック実装"""
        await asyncio.sleep(0.7)  # API呼び出しをシミュレート

        return [
            {
                "id": "mock_gurume_1",
                "name": "和食処 さくら",
                "address": "東京都中央区銀座3-3-3",
                "latitude": 35.6721,
                "longitude": 139.7640,
                "category": "和食",
                "budget": 3000,
                "access": "銀座駅徒歩3分",
                "pr": "厳選された季節の食材を使用した本格和食"
            },
            {
                "id": "mock_gurume_2",
                "name": "ビストロ パリ",
                "address": "東京都渋谷区恵比寿4-4-4",
                "latitude": 35.6466,
                "longitude": 139.7105,
                "category": "フレンチ",
                "budget": 4000,
                "access": "恵比寿駅徒歩5分",
                "pr": "本場仕込みのフレンチを気軽にお楽しみください"
            }
        ]

    # データ変換

    async def _convert_places_to_venue(self, place_data: Dict[str, Any]) -> Venue:
        """Google Places APIデータをVenueオブジェクトに変換"""
        venue = Venue(
            event_id=self.event_id,
            venue_type=VenueType.RESTAURANT,  # タイプから判定
            name=place_data["name"],
            address=place_data["formatted_address"],
            google_places_id=place_data["place_id"],
            latitude=place_data["geometry"]["location"]["lat"],
            longitude=place_data["geometry"]["location"]["lng"],
            capacity=30,  # デフォルト値（実際はAPI詳細から取得）
            rating=place_data.get("rating"),
            review_count=place_data.get("user_ratings_total"),
            price_level=PriceLevel(place_data["price_level"]) if "price_level" in place_data else None,
            estimated_cost_per_person=self._estimate_cost_from_price_level(place_data.get("price_level"))
        )

        # 設備情報を追加
        if "cafe" in place_data.get("types", []):
            venue.add_feature("WiFi", True, "カフェのため WiFi 利用可能と推定")
        if "restaurant" in place_data.get("types", []):
            venue.add_feature("食事提供", True, "レストランのため食事提供可能")

        return venue

    async def _convert_gurume_to_venue(self, restaurant_data: Dict[str, Any]) -> Venue:
        """ぐるなびAPIデータをVenueオブジェクトに変換"""
        venue = Venue(
            event_id=self.event_id,
            venue_type=VenueType.RESTAURANT,
            name=restaurant_data["name"],
            address=restaurant_data["address"],
            gurume_id=restaurant_data["id"],
            latitude=restaurant_data["latitude"],
            longitude=restaurant_data["longitude"],
            capacity=20,  # デフォルト値
            estimated_cost_per_person=restaurant_data.get("budget"),
            nearest_station=restaurant_data.get("access"),
            description=restaurant_data.get("pr")
        )

        # カテゴリに基づく設備追加
        if "和食" in restaurant_data.get("category", ""):
            venue.add_feature("和食", True, "和食レストラン")
        elif "フレンチ" in restaurant_data.get("category", ""):
            venue.add_feature("洋食", True, "フレンチレストラン")

        venue.add_feature("食事提供", True, "レストランのため食事提供可能")

        return venue

    def _estimate_cost_from_price_level(self, price_level: Optional[int]) -> Optional[int]:
        """価格レベルから予算を推定"""
        if price_level is None:
            return None

        cost_mapping = {
            0: 500,   # 無料
            1: 1500,  # 安価
            2: 3000,  # 普通
            3: 5000,  # 高価
            4: 8000   # 非常に高価
        }

        return cost_mapping.get(price_level, 3000)

    # 検索結果評価

    async def _evaluate_search_results(self) -> None:
        """検索結果を評価"""
        logger.info("検索結果評価開始")

        for result in self.search_results:
            # 時間適合性チェック
            is_time_suitable = await self._check_time_suitability(result.venue)
            if not is_time_suitable:
                result.notes.append("営業時間が合わない可能性")
                result.suitability_score *= 0.8

            # 予算チェック
            if (result.estimated_total_cost and
                self.search_criteria.budget_per_person and
                result.estimated_total_cost > self.search_criteria.budget_per_person * self.search_criteria.participant_count):
                result.notes.append("予算超過の可能性")
                result.suitability_score *= 0.9

            # アクセシビリティチェック
            if self.search_criteria.accessibility_required and not result.venue.wheelchair_accessible:
                result.notes.append("バリアフリー対応未確認")
                result.suitability_score *= 0.7

        # スコア順でソート
        self.search_results.sort(key=lambda x: x.suitability_score, reverse=True)

        logger.info(f"検索結果評価完了: 最高スコア {self.search_results[0].suitability_score:.2f}" if self.search_results else "評価結果なし")

    async def _check_time_suitability(self, venue: Venue) -> bool:
        """時間適合性をチェック"""
        if not self.search_criteria.datetime:
            return True

        # 営業時間情報がない場合は適合と仮定
        if not venue.business_hours:
            return True

        event_time = self.search_criteria.datetime
        day_of_week = (event_time.weekday() + 1) % 7  # 月曜=0 → 日曜=0に変換

        for hours in venue.business_hours:
            if hours.day_of_week == day_of_week:
                if hours.is_closed:
                    return False

                # 簡単な時間チェック（実際はより複雑な処理が必要）
                event_hour = event_time.strftime("%H:%M")
                return hours.open_time <= event_hour <= hours.close_time

        return True

    # 会場選択

    async def _select_best_venue(self) -> Optional[Venue]:
        """最適な会場を選択"""
        if not self.search_results:
            logger.warning("選択可能な会場がありません")
            return None

        best_result = self.search_results[0]
        self.selected_venue = best_result.venue

        # 予約ステータスを設定
        if best_result.source_api == "manual_fallback":
            self.selected_venue.booking_status = BookingStatus.MANUAL_REQUIRED
        else:
            self.selected_venue.booking_status = BookingStatus.PENDING

        logger.info(f"最適会場選択: {self.selected_venue.name} (スコア: {best_result.suitability_score:.2f})")

        # 選択結果を通知
        await self._notify_venue_selection()

        return self.selected_venue

    async def _notify_venue_selection(self) -> None:
        """会場選択結果を通知"""
        if not self.selected_venue:
            return

        notification_message = AgentMessage(
            sender_id=self.agent_id,
            message_type=MessageType.EVENT,
            subject="会場選択通知",
            payload={
                "event_type": "venue_selected",
                "venue": {
                    "venue_id": self.selected_venue.venue_id,
                    "name": self.selected_venue.name,
                    "address": self.selected_venue.address,
                    "capacity": self.selected_venue.capacity,
                    "estimated_cost": self.selected_venue.estimated_cost_per_person,
                    "booking_status": self.selected_venue.booking_status,
                    "source": next(
                        (r.source_api for r in self.search_results if r.venue.venue_id == self.selected_venue.venue_id),
                        "unknown"
                    )
                }
            }
        )

        await self.send_message(notification_message)

    # エラー処理

    async def _record_api_failure(self, api_name: str, error_message: str) -> None:
        """API失敗を記録"""
        failure = APIFailureRecord(
            api_name=api_name,
            error_type=type(Exception).__name__,
            error_message=error_message
        )
        self.api_failures.append(failure)

        logger.warning(f"API失敗記録: {api_name} - {error_message}")

        # 失敗通知
        failure_message = AgentMessage(
            sender_id=self.agent_id,
            message_type=MessageType.EVENT,
            subject="API失敗通知",
            payload={
                "event_type": "api_failure",
                "api_name": api_name,
                "error_message": error_message,
                "fallback_available": True
            }
        )

        await self.send_message(failure_message)

    # 完了報告

    async def _send_completion_report(self) -> None:
        """完了報告を送信"""
        report = {
            "search_results_count": len(self.search_results),
            "selected_venue": self.selected_venue.dict() if self.selected_venue else None,
            "api_failures": len(self.api_failures),
            "fallback_used": any(r.source_api == "manual_fallback" for r in self.search_results),
            "booking_required": self.selected_venue.booking_status != BookingStatus.CONFIRMED if self.selected_venue else True
        }

        completion_message = AgentMessage(
            sender_id=self.agent_id,
            message_type=MessageType.EVENT,
            subject="会場エージェント完了報告",
            payload={
                "event_type": "agent_completed",
                "agent_name": "venue_agent",
                "result": report
            }
        )

        await self.send_message(completion_message)

    # メッセージハンドラー（簡略化）

    async def _handle_command(self, message: AgentMessage) -> Optional[AgentMessage]:
        """コマンドメッセージの処理"""
        command = message.payload.get("command")
        logger.info(f"コマンド受信: {command}")

        if command == "search_venues":
            results = await self._search_venues()
            return message.create_response(
                sender_id=self.agent_id,
                payload={
                    "status": "success",
                    "results_count": len(results),
                    "top_venue": results[0].dict() if results else None
                }
            )

        elif command == "select_venue":
            venue_id = message.payload.get("venue_id")
            # 指定された会場を選択
            for result in self.search_results:
                if result.venue.venue_id == venue_id:
                    self.selected_venue = result.venue
                    await self._notify_venue_selection()
                    return message.create_response(
                        sender_id=self.agent_id,
                        payload={"status": "success", "selected_venue": result.venue.dict()}
                    )

            return message.create_response(
                sender_id=self.agent_id,
                payload={"status": "error", "message": "指定された会場が見つかりません"}
            )

        elif command == "get_search_results":
            return message.create_response(
                sender_id=self.agent_id,
                payload={
                    "status": "success",
                    "results": [result.dict() for result in self.search_results]
                }
            )

        else:
            return message.create_response(
                sender_id=self.agent_id,
                payload={"status": "error", "message": f"未知のコマンド: {command}"}
            )

    async def _handle_query(self, message: AgentMessage) -> Optional[AgentMessage]:
        """クエリメッセージの処理"""
        query_type = message.payload.get("query_type")

        if query_type == "selected_venue":
            return message.create_response(
                sender_id=self.agent_id,
                payload={
                    "selected_venue": self.selected_venue.dict() if self.selected_venue else None
                }
            )

        elif query_type == "search_status":
            return message.create_response(
                sender_id=self.agent_id,
                payload={
                    "results_count": len(self.search_results),
                    "venue_selected": self.selected_venue is not None,
                    "api_failures": len(self.api_failures)
                }
            )

        else:
            return message.create_response(
                sender_id=self.agent_id,
                payload={"status": "error", "message": f"未知のクエリタイプ: {query_type}"}
            )

    async def _handle_event(self, message: AgentMessage) -> Optional[AgentMessage]:
        """イベントメッセージの処理"""
        event_type = message.payload.get("event_type")

        if event_type == "schedule_updated":
            # スケジュール更新時は再検索
            await self._prepare_search_criteria()
            await self._search_venues()

        elif event_type == "participant_count_changed":
            # 参加者数変更時は適合性を再評価
            await self._evaluate_search_results()

        return None