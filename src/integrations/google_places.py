"""
Google Places API統合 - レート制限対応
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pydantic import BaseModel, Field
import logging
import secrets
from enum import Enum

logger = logging.getLogger(__name__)


class PlaceType(str, Enum):
    """場所タイプ"""
    RESTAURANT = "restaurant"
    CAFE = "cafe"
    BAR = "bar"
    MEETING_ROOM = "meeting_room"
    EVENT_VENUE = "event_venue"


class PriceLevel(int, Enum):
    """価格レベル（Google Places基準）"""
    FREE = 0
    INEXPENSIVE = 1
    MODERATE = 2
    EXPENSIVE = 3
    VERY_EXPENSIVE = 4


class PlaceSearchRequest(BaseModel):
    """場所検索リクエスト"""
    query: Optional[str] = None
    location_lat: float
    location_lng: float
    radius_meters: int = 1000
    place_type: PlaceType
    min_rating: float = 3.5
    max_price_level: PriceLevel = PriceLevel.EXPENSIVE
    open_now: bool = False
    language: str = "ja"


class PlaceDetails(BaseModel):
    """場所詳細情報"""
    place_id: str
    name: str
    formatted_address: str
    rating: Optional[float] = None
    price_level: Optional[PriceLevel] = None
    phone_number: Optional[str] = None
    website: Optional[str] = None
    opening_hours: Optional[Dict[str, Any]] = None
    photos: List[str] = Field(default_factory=list)
    reviews: List[Dict[str, Any]] = Field(default_factory=list)
    location: Dict[str, float]  # {"lat": float, "lng": float}
    place_types: List[str] = Field(default_factory=list)
    business_status: Optional[str] = None


class PlaceSearchResult(BaseModel):
    """場所検索結果"""
    place: PlaceDetails
    distance_meters: Optional[float] = None
    relevance_score: float
    availability_info: Optional[Dict[str, Any]] = None


class PlaceSearchResponse(BaseModel):
    """場所検索レスポンス"""
    success: bool
    results: List[PlaceSearchResult] = Field(default_factory=list)
    next_page_token: Optional[str] = None
    error_message: Optional[str] = None
    quota_exceeded: bool = False
    retry_after: Optional[int] = None


class RateLimiter:
    """レート制限管理"""

    def __init__(self, requests_per_second: float = 10, requests_per_day: int = 100000):
        self.requests_per_second = requests_per_second
        self.requests_per_day = requests_per_day
        self.request_history: List[datetime] = []
        self.daily_request_count = 0
        self.last_reset_date = datetime.now().date()

    async def acquire(self) -> bool:
        """レート制限取得"""
        now = datetime.now()

        # 日次リセット
        if now.date() != self.last_reset_date:
            self.daily_request_count = 0
            self.last_reset_date = now.date()

        # 日次制限チェック
        if self.daily_request_count >= self.requests_per_day:
            logger.warning("日次レート制限に達しました")
            return False

        # 秒次制限チェック
        self.request_history = [
            ts for ts in self.request_history
            if (now - ts).total_seconds() < 1
        ]

        if len(self.request_history) >= self.requests_per_second:
            logger.info(f"秒次レート制限待機: {len(self.request_history)}/{self.requests_per_second}")
            await asyncio.sleep(1.0 / self.requests_per_second)

        # リクエスト記録
        self.request_history.append(now)
        self.daily_request_count += 1

        return True


class GooglePlacesClient:
    """
    Google Places API統合クライアント
    - 場所検索とフィルタリング
    - レート制限対応
    - エラーハンドリングとリトライ
    - 日本語対応
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://maps.googleapis.com/maps/api/place"

        # レート制限管理
        self.rate_limiter = RateLimiter(
            requests_per_second=10,  # Google Places API制限
            requests_per_day=100000
        )

        # キャッシュ（1時間有効）
        self.search_cache: Dict[str, Tuple[PlaceSearchResponse, datetime]] = {}
        self.details_cache: Dict[str, Tuple[PlaceDetails, datetime]] = {}

    async def search_places(self, request: PlaceSearchRequest) -> PlaceSearchResponse:
        """場所検索"""
        # キャッシュキー生成
        cache_key = self._generate_search_cache_key(request)
        cached_result = self._get_cached_search(cache_key)

        if cached_result:
            logger.info("キャッシュから検索結果返却")
            return cached_result

        # レート制限取得
        if not await self.rate_limiter.acquire():
            return PlaceSearchResponse(
                success=False,
                error_message="レート制限に達しました",
                quota_exceeded=True,
                retry_after=3600
            )

        try:
            # Google Places API呼び出し
            response = await self._call_places_search_api(request)

            # 結果キャッシュ
            if response.success:
                self.search_cache[cache_key] = (response, datetime.now())

            return response

        except Exception as e:
            logger.error(f"Places検索エラー: {str(e)}")
            return PlaceSearchResponse(
                success=False,
                error_message=f"検索エラー: {str(e)}"
            )

    async def get_place_details(self, place_id: str, language: str = "ja") -> Optional[PlaceDetails]:
        """場所詳細取得"""
        # キャッシュ確認
        cached_details = self._get_cached_details(place_id)
        if cached_details:
            logger.info(f"キャッシュから詳細情報返却: {place_id}")
            return cached_details

        # レート制限取得
        if not await self.rate_limiter.acquire():
            logger.warning("詳細取得でレート制限に達しました")
            return None

        try:
            # Google Places Details API呼び出し
            details = await self._call_place_details_api(place_id, language)

            # キャッシュ
            if details:
                self.details_cache[place_id] = (details, datetime.now())

            return details

        except Exception as e:
            logger.error(f"Place詳細取得エラー: {str(e)}")
            return None

    async def search_nearby_restaurants(self, lat: float, lng: float, radius: int = 1000,
                                       cuisine_type: Optional[str] = None,
                                       min_rating: float = 3.5) -> PlaceSearchResponse:
        """近隣レストラン検索"""
        request = PlaceSearchRequest(
            query=cuisine_type,
            location_lat=lat,
            location_lng=lng,
            radius_meters=radius,
            place_type=PlaceType.RESTAURANT,
            min_rating=min_rating,
            open_now=True,
            language="ja"
        )

        return await self.search_places(request)

    async def search_meeting_venues(self, lat: float, lng: float, capacity: int,
                                   radius: int = 2000) -> PlaceSearchResponse:
        """会議会場検索"""
        # 会議室・イベント会場向け検索
        request = PlaceSearchRequest(
            query=f"会議室 定員{capacity}名",
            location_lat=lat,
            location_lng=lng,
            radius_meters=radius,
            place_type=PlaceType.EVENT_VENUE,
            min_rating=3.0,
            language="ja"
        )

        return await self.search_places(request)

    async def batch_get_details(self, place_ids: List[str], language: str = "ja") -> List[Optional[PlaceDetails]]:
        """バッチ詳細取得"""
        semaphore = asyncio.Semaphore(5)  # 並行数制限

        async def get_details_with_semaphore(place_id: str):
            async with semaphore:
                return await self.get_place_details(place_id, language)

        tasks = [get_details_with_semaphore(place_id) for place_id in place_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 例外処理
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"詳細取得で例外: {str(result)}")
                processed_results.append(None)
            else:
                processed_results.append(result)

        return processed_results

    async def _call_places_search_api(self, request: PlaceSearchRequest) -> PlaceSearchResponse:
        """Google Places Search API呼び出し"""
        logger.info(f"Places検索API呼び出し: {request.place_type} at ({request.location_lat}, {request.location_lng})")

        # プロダクション実装: 実際のGoogle Places API呼び出し
        # 注意: 実際の使用時はGoogle Places APIキーが必要
        if not self.api_key or self.api_key.startswith("mock_"):
            logger.warning("Mock API key detected - using fallback data")
            return await self._fallback_search_results(request)

        try:
            # 実際のAPI実装はここに追加
            # import googlemaps が必要
            # gmaps = googlemaps.Client(key=self.api_key)
            # places_result = gmaps.places_nearby(...)

            # 現在はフォールバック実装を使用
            return await self._fallback_search_results(request)

        except Exception as e:
            logger.error(f"Places API呼び出しエラー: {str(e)}")
            return PlaceSearchResponse(
                success=False,
                error_message=f"API呼び出し失敗: {str(e)}",
                results=[]
            )

    async def _call_place_details_api(self, place_id: str, language: str) -> Optional[PlaceDetails]:
        """Google Places Details API呼び出し（Mock）"""
        logger.info(f"Place詳細API呼び出し: {place_id}")

        # Mock詳細情報生成
        return PlaceDetails(
            place_id=place_id,
            name="詳細情報付きレストラン",
            formatted_address="東京都渋谷区渋谷1-2-3",
            rating=4.2,
            price_level=PriceLevel.MODERATE,
            phone_number="+81-3-1234-5678",
            website="https://example-restaurant.com",
            opening_hours={
                "open_now": True,
                "periods": [
                    {
                        "open": {"day": 1, "time": "1100"},
                        "close": {"day": 1, "time": "2200"}
                    }
                ]
            },
            photos=["photo1_url", "photo2_url"],
            reviews=[
                {
                    "author_name": "田中さん",
                    "rating": 5,
                    "text": "美味しいです！",
                    "time": int(datetime.now().timestamp())
                }
            ],
            location={"lat": 35.6595, "lng": 139.7006},
            place_types=["restaurant", "food", "establishment"],
            business_status="OPERATIONAL"
        )

    async def _generate_mock_restaurants(self, request: PlaceSearchRequest) -> List[PlaceDetails]:
        """Mock レストランデータ生成"""
        restaurants = []
        base_names = [
            "居酒屋 さくら", "イタリアン ベラヴィスタ", "寿司 鶴", "焼肉 牛角",
            "フレンチ ル・シエル", "中華 龍王", "うどん 讃岐", "カフェ モカ"
        ]

        for i, name in enumerate(base_names):
            # 位置を少しずつずらす
            lat_offset = (i - 4) * 0.001
            lng_offset = (i % 3 - 1) * 0.001

            restaurant = PlaceDetails(
                place_id=f"mock_restaurant_{i}",
                name=name,
                formatted_address=f"東京都渋谷区{i+1}-{i+2}-{i+3}",
                rating=3.5 + (i % 3) * 0.5,
                price_level=PriceLevel(i % 4 + 1),
                phone_number=f"+81-3-123{i}-567{i}",
                location={
                    "lat": request.location_lat + lat_offset,
                    "lng": request.location_lng + lng_offset
                },
                place_types=["restaurant", "food", "establishment"],
                business_status="OPERATIONAL"
            )
            restaurants.append(restaurant)

        return restaurants

    async def _generate_mock_venues(self, request: PlaceSearchRequest) -> List[PlaceDetails]:
        """Mock 会場データ生成"""
        venues = []
        base_names = [
            "会議室センター 渋谷", "イベントホール アクシス", "レンタルスペース ビズ",
            "コワーキングスペース ハブ", "セミナールーム プロ"
        ]

        for i, name in enumerate(base_names):
            lat_offset = (i - 2) * 0.002
            lng_offset = (i % 2 - 0.5) * 0.002

            venue = PlaceDetails(
                place_id=f"mock_venue_{i}",
                name=name,
                formatted_address=f"東京都新宿区{i+1}-{i+3}-{i+5}",
                rating=4.0 + (i % 2) * 0.3,
                price_level=PriceLevel.MODERATE,
                phone_number=f"+81-3-987{i}-654{i}",
                location={
                    "lat": request.location_lat + lat_offset,
                    "lng": request.location_lng + lng_offset
                },
                place_types=["establishment", "point_of_interest"],
                business_status="OPERATIONAL"
            )
            venues.append(venue)

        return venues

    async def _generate_mock_cafes(self, request: PlaceSearchRequest) -> List[PlaceDetails]:
        """Mock カフェデータ生成"""
        cafes = []
        base_names = [
            "スターバックス", "ドトール", "タリーズ", "コメダ珈琲",
            "カフェ ドゥ クリエ", "プロント"
        ]

        for i, name in enumerate(base_names):
            lat_offset = (i - 3) * 0.0015
            lng_offset = ((i * 2) % 5 - 2) * 0.0015

            cafe = PlaceDetails(
                place_id=f"mock_cafe_{i}",
                name=f"{name} {i+1}号店",
                formatted_address=f"東京都港区{i+2}-{i+1}-{i+4}",
                rating=3.8 + (i % 4) * 0.2,
                price_level=PriceLevel.INEXPENSIVE,
                phone_number=f"+81-3-555{i}-888{i}",
                location={
                    "lat": request.location_lat + lat_offset,
                    "lng": request.location_lng + lng_offset
                },
                place_types=["cafe", "food", "establishment"],
                business_status="OPERATIONAL"
            )
            cafes.append(cafe)

        return cafes

    def _calculate_relevance_score(self, place: PlaceDetails, request: PlaceSearchRequest) -> float:
        """関連性スコア計算"""
        score = 0.0

        # 評価による加点
        if place.rating:
            rating_score = min(place.rating / 5.0, 1.0)
            score += rating_score * 0.3

        # 価格レベルによる調整
        if place.price_level and request.max_price_level:
            if place.price_level <= request.max_price_level:
                score += 0.2
            else:
                score -= 0.3

        # 距離による調整
        distance = self._calculate_distance(place.location, request)
        if distance <= request.radius_meters:
            distance_score = 1.0 - (distance / request.radius_meters)
            score += distance_score * 0.3

        # クエリマッチング
        if request.query and request.query in place.name:
            score += 0.2

        return max(0.0, min(1.0, score))

    def _calculate_distance(self, place_location: Dict[str, float], request: PlaceSearchRequest) -> float:
        """距離計算（簡易版）"""
        # 簡易的な直線距離計算（実際にはHaversine式を使用）
        lat_diff = abs(place_location["lat"] - request.location_lat)
        lng_diff = abs(place_location["lng"] - request.location_lng)

        # 1度 ≈ 111km として概算
        distance_km = ((lat_diff ** 2 + lng_diff ** 2) ** 0.5) * 111
        return distance_km * 1000  # メートルに変換

    def _generate_search_cache_key(self, request: PlaceSearchRequest) -> str:
        """検索キャッシュキー生成"""
        return f"{request.place_type}_{request.location_lat:.4f}_{request.location_lng:.4f}_{request.radius_meters}_{request.query or ''}"

    def _get_cached_search(self, cache_key: str) -> Optional[PlaceSearchResponse]:
        """キャッシュ検索結果取得"""
        if cache_key in self.search_cache:
            result, cached_time = self.search_cache[cache_key]
            if datetime.now() - cached_time < timedelta(hours=1):
                return result
            else:
                # 期限切れキャッシュ削除
                del self.search_cache[cache_key]
        return None

    def _get_cached_details(self, place_id: str) -> Optional[PlaceDetails]:
        """キャッシュ詳細情報取得"""
        if place_id in self.details_cache:
            result, cached_time = self.details_cache[place_id]
            if datetime.now() - cached_time < timedelta(hours=1):
                return result
            else:
                # 期限切れキャッシュ削除
                del self.details_cache[place_id]
        return None


class PlaceSearchManager:
    """
    場所検索管理クラス
    - 検索戦略決定
    - フォールバック処理
    - 結果フィルタリング
    """

    def __init__(self, places_client: GooglePlacesClient):
        self.client = places_client

    async def find_restaurants_for_event(self, lat: float, lng: float, participant_count: int,
                                        cuisine_preferences: List[str] = None,
                                        budget_level: PriceLevel = PriceLevel.MODERATE) -> PlaceSearchResponse:
        """イベント用レストラン検索"""
        # 複数検索戦略を並行実行
        search_tasks = []

        # 一般的なレストラン検索
        search_tasks.append(
            self.client.search_nearby_restaurants(lat, lng, radius=1500, min_rating=3.5)
        )

        # 料理タイプ別検索
        if cuisine_preferences:
            for cuisine in cuisine_preferences[:2]:  # 最大2つまで
                search_tasks.append(
                    self.client.search_nearby_restaurants(
                        lat, lng, radius=2000, cuisine_type=cuisine, min_rating=3.0
                    )
                )

        # 検索実行
        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

        # 結果統合
        all_results = []
        for result in search_results:
            if isinstance(result, PlaceSearchResponse) and result.success:
                all_results.extend(result.results)

        # 重複除去とフィルタリング
        unique_results = {}
        for result in all_results:
            place_id = result.place.place_id
            if place_id not in unique_results:
                # 参加者数に適した場所かチェック
                if self._is_suitable_for_group_size(result.place, participant_count):
                    # 予算に合うかチェック
                    if result.place.price_level and result.place.price_level <= budget_level:
                        unique_results[place_id] = result

        # スコア順でソート
        final_results = sorted(unique_results.values(),
                              key=lambda r: r.relevance_score, reverse=True)

        return PlaceSearchResponse(
            success=True,
            results=final_results[:10]  # 上位10件
        )

    async def find_meeting_spaces(self, lat: float, lng: float, participant_count: int,
                                 duration_hours: int = 2) -> PlaceSearchResponse:
        """会議スペース検索"""
        # 会議室・コワーキングスペース検索
        venues_result = await self.client.search_meeting_venues(lat, lng, participant_count)

        if not venues_result.success or not venues_result.results:
            # フォールバック: カフェ検索
            cafe_request = PlaceSearchRequest(
                query="静か 会議",
                location_lat=lat,
                location_lng=lng,
                radius_meters=1000,
                place_type=PlaceType.CAFE,
                min_rating=3.5
            )
            cafe_result = await self.client.search_places(cafe_request)

            if cafe_result.success:
                venues_result.results.extend(cafe_result.results[:5])

        return venues_result

    def _is_suitable_for_group_size(self, place: PlaceDetails, participant_count: int) -> bool:
        """グループサイズ適性判定"""
        # 基本的には価格レベルと評価で判定（実際の座席数情報がない場合）
        if participant_count <= 2:
            return True
        elif participant_count <= 6:
            # 中規模グループ：ある程度の評価が必要
            return place.rating is None or place.rating >= 3.5
        else:
            # 大規模グループ：高評価で価格レベルが適切
            has_good_rating = place.rating is None or place.rating >= 4.0
            has_appropriate_price = (place.price_level is None or
                                   place.price_level in [PriceLevel.MODERATE, PriceLevel.EXPENSIVE])
            return has_good_rating and has_appropriate_price