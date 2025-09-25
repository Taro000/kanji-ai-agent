"""
ぐるなび API統合 - エラーハンドリング対応
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pydantic import BaseModel, Field
import logging
import secrets
from enum import Enum
import re

logger = logging.getLogger(__name__)


class CuisineCategory(str, Enum):
    """料理カテゴリ"""
    JAPANESE = "japanese"
    ITALIAN = "italian"
    FRENCH = "french"
    CHINESE = "chinese"
    KOREAN = "korean"
    YAKINIKU = "yakiniku"
    SUSHI = "sushi"
    IZAKAYA = "izakaya"
    CAFE = "cafe"
    BAR = "bar"


class BudgetRange(str, Enum):
    """予算レンジ"""
    UNDER_1000 = "under_1000"
    RANGE_1000_2000 = "1000_2000"
    RANGE_2000_3000 = "2000_3000"
    RANGE_3000_4000 = "3000_4000"
    RANGE_4000_5000 = "4000_5000"
    OVER_5000 = "over_5000"


class GurumeNaviSearchRequest(BaseModel):
    """ぐるなび検索リクエスト"""
    area_code: Optional[str] = None  # エリアコード
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    range_km: float = 1.0  # 検索半径（km）

    # 料理・店舗タイプ
    cuisine_category: Optional[CuisineCategory] = None
    keyword: Optional[str] = None

    # 予算・時間
    budget_range: Optional[BudgetRange] = None
    party_size: Optional[int] = None

    # 営業時間・予約
    open_time: Optional[str] = None  # "18:00" 形式
    available_now: bool = False
    accepts_reservations: bool = False

    # フィルタ条件
    has_private_room: bool = False
    smoking_allowed: bool = False
    credit_card_accepted: bool = False

    # 検索オプション
    hit_per_page: int = 20
    offset_page: int = 1


class RestaurantInfo(BaseModel):
    """レストラン情報"""
    restaurant_id: str
    name: str
    name_kana: Optional[str] = None
    address: str
    access_info: Optional[str] = None  # アクセス情報

    # 位置情報
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # 営業情報
    opening_hours: List[str] = Field(default_factory=list)
    closing_days: List[str] = Field(default_factory=list)
    budget_dinner: Optional[str] = None
    budget_lunch: Optional[str] = None

    # 予約・サービス情報
    tel: Optional[str] = None
    reservation_url: Optional[str] = None
    accepts_credit_card: bool = False
    has_private_room: bool = False
    smoking_policy: Optional[str] = None

    # 料理情報
    cuisine_genres: List[str] = Field(default_factory=list)
    specialties: List[str] = Field(default_factory=list)

    # 画像・URL
    shop_image_urls: List[str] = Field(default_factory=list)
    detail_url: Optional[str] = None

    # その他
    pr_comment: Optional[str] = None
    total_seats: Optional[int] = None


class GurumeNaviSearchResult(BaseModel):
    """検索結果"""
    restaurant: RestaurantInfo
    distance_km: Optional[float] = None
    match_score: float  # マッチング度
    availability_info: Optional[Dict[str, Any]] = None


class GurumeNaviResponse(BaseModel):
    """ぐるなびAPIレスポンス"""
    success: bool
    results: List[GurumeNaviSearchResult] = Field(default_factory=list)
    total_hit_count: int = 0
    current_page: int = 1
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    rate_limit_exceeded: bool = False
    retry_after: Optional[int] = None


class ErrorHandler:
    """エラーハンドリング管理"""

    def __init__(self):
        # エラーコードマッピング
        self.error_messages = {
            "1001": "リクエストパラメータが不正です",
            "2001": "APIキーが無効です",
            "2002": "API使用権限がありません",
            "3001": "一時的なサーバーエラーが発生しました",
            "3002": "データベース接続エラー",
            "4001": "該当するレストランが見つかりませんでした",
            "5001": "レート制限に達しました",
            "5002": "日次クォータを超過しました"
        }

        # リトライ可能エラー
        self.retryable_errors = {"3001", "3002", "5001"}

        # エラー統計
        self.error_counts: Dict[str, int] = {}
        self.last_error_time: Optional[datetime] = None

    def handle_error(self, error_code: str, error_message: str = None) -> Tuple[str, bool, int]:
        """
        エラー処理
        Returns: (user_message, is_retryable, retry_after_seconds)
        """
        self.error_counts[error_code] = self.error_counts.get(error_code, 0) + 1
        self.last_error_time = datetime.now()

        user_message = self.error_messages.get(error_code, error_message or "不明なエラーが発生しました")
        is_retryable = error_code in self.retryable_errors

        # リトライ待機時間決定
        retry_after = 0
        if error_code == "5001":  # レート制限
            retry_after = 60
        elif error_code in ["3001", "3002"]:  # サーバーエラー
            retry_after = 30
        elif error_code == "5002":  # 日次クォータ
            retry_after = 3600

        return user_message, is_retryable, retry_after


class GurumeNaviClient:
    """
    ぐるなび API統合クライアント
    - レストラン検索
    - エラーハンドリング・リトライ
    - レート制限対応
    - 日本語自然言語対応
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.gnavi.co.jp"

        # エラーハンドリング
        self.error_handler = ErrorHandler()

        # レート制限（ぐるなび API制限に基づく）
        self.requests_per_second = 5
        self.requests_per_day = 10000
        self.request_history: List[datetime] = []
        self.daily_request_count = 0
        self.last_reset_date = datetime.now().date()

        # キャッシュ（30分有効）
        self.search_cache: Dict[str, Tuple[GurumeNaviResponse, datetime]] = {}

        # エリアコードマップ（主要エリア）
        self.area_codes = {
            "渋谷": "AREAS2124",
            "新宿": "AREAS2123",
            "銀座": "AREAS2108",
            "六本木": "AREAS2113",
            "恵比寿": "AREAS2125",
            "品川": "AREAS2131",
            "池袋": "AREAS2128",
            "上野": "AREAS2111"
        }

    async def search_restaurants(self, request: GurumeNaviSearchRequest) -> GurumeNaviResponse:
        """レストラン検索"""
        # キャッシュ確認
        cache_key = self._generate_cache_key(request)
        cached_result = self._get_cached_result(cache_key)

        if cached_result:
            logger.info("キャッシュからぐるなび結果返却")
            return cached_result

        # レート制限チェック
        if not await self._check_rate_limit():
            return GurumeNaviResponse(
                success=False,
                error_message="レート制限に達しました",
                rate_limit_exceeded=True,
                retry_after=60
            )

        try:
            # API呼び出し実行
            response = await self._call_gurume_api(request)

            # 成功時はキャッシュ
            if response.success:
                self.search_cache[cache_key] = (response, datetime.now())

            return response

        except Exception as e:
            logger.error(f"ぐるなび検索エラー: {str(e)}")
            return GurumeNaviResponse(
                success=False,
                error_message=f"検索処理中にエラーが発生しました: {str(e)}"
            )

    async def search_by_natural_language(self, query: str, latitude: float = None, longitude: float = None) -> GurumeNaviResponse:
        """自然言語検索"""
        # クエリ解析
        parsed_request = self._parse_natural_query(query, latitude, longitude)

        return await self.search_restaurants(parsed_request)

    async def get_restaurant_details(self, restaurant_id: str) -> Optional[RestaurantInfo]:
        """レストラン詳細取得"""
        if not await self._check_rate_limit():
            logger.warning("レート制限により詳細取得をスキップ")
            return None

        try:
            # 詳細API呼び出し（Mock）
            details = await self._call_detail_api(restaurant_id)
            return details

        except Exception as e:
            logger.error(f"詳細取得エラー: {str(e)}")
            return None

    async def search_with_fallback(self, primary_request: GurumeNaviSearchRequest) -> GurumeNaviResponse:
        """フォールバック付き検索"""
        # 1次検索
        result = await self.search_restaurants(primary_request)

        if result.success and result.results:
            return result

        logger.info("1次検索失敗、フォールバック検索開始")

        # フォールバック戦略1: 条件緩和
        relaxed_request = primary_request.copy()
        relaxed_request.range_km = min(3.0, relaxed_request.range_km * 2)  # 範囲拡大
        relaxed_request.accepts_reservations = False  # 予約条件緩和
        relaxed_request.has_private_room = False  # 個室条件緩和

        fallback_result = await self.search_restaurants(relaxed_request)

        if fallback_result.success and fallback_result.results:
            logger.info(f"フォールバック検索成功: {len(fallback_result.results)}件")
            return fallback_result

        # フォールバック戦略2: キーワード検索のみ
        if primary_request.keyword:
            keyword_only_request = GurumeNaviSearchRequest(
                latitude=primary_request.latitude,
                longitude=primary_request.longitude,
                range_km=5.0,
                keyword=primary_request.keyword
            )

            final_result = await self.search_restaurants(keyword_only_request)
            if final_result.success and final_result.results:
                logger.info(f"キーワード検索成功: {len(final_result.results)}件")
                return final_result

        return GurumeNaviResponse(
            success=False,
            error_message="条件に合うレストランが見つかりませんでした。条件を変更してお試しください。"
        )

    def _parse_natural_query(self, query: str, latitude: float = None, longitude: float = None) -> GurumeNaviSearchRequest:
        """自然言語クエリ解析"""
        request = GurumeNaviSearchRequest(
            latitude=latitude,
            longitude=longitude
        )

        # 料理ジャンル検出
        cuisine_patterns = {
            CuisineCategory.JAPANESE: [r"和食", r"日本料理", r"懐石"],
            CuisineCategory.ITALIAN: [r"イタリアン", r"パスタ", r"ピザ"],
            CuisineCategory.FRENCH: [r"フレンチ", r"フランス料理"],
            CuisineCategory.CHINESE: [r"中華", r"中国料理", r"中華料理"],
            CuisineCategory.KOREAN: [r"韓国", r"韓国料理", r"焼肉"],
            CuisineCategory.YAKINIKU: [r"焼肉", r"焼き肉"],
            CuisineCategory.SUSHI: [r"寿司", r"すし", r"鮨"],
            CuisineCategory.IZAKAYA: [r"居酒屋", r"飲み屋"],
            CuisineCategory.CAFE: [r"カフェ", r"喫茶"],
            CuisineCategory.BAR: [r"バー", r"酒場"]
        }

        for category, patterns in cuisine_patterns.items():
            if any(re.search(pattern, query) for pattern in patterns):
                request.cuisine_category = category
                break

        # 予算検出
        budget_patterns = {
            BudgetRange.UNDER_1000: [r"1000円以下", r"安い", r"格安"],
            BudgetRange.RANGE_2000_3000: [r"2000.*3000", r"普通"],
            BudgetRange.RANGE_4000_5000: [r"4000.*5000", r"少し高め"],
            BudgetRange.OVER_5000: [r"5000円以上", r"高級", r"贅沢"]
        }

        for budget_range, patterns in budget_patterns.items():
            if any(re.search(pattern, query) for pattern in patterns):
                request.budget_range = budget_range
                break

        # 人数検出
        party_size_match = re.search(r"(\d+)人", query)
        if party_size_match:
            request.party_size = int(party_size_match.group(1))

        # 特別条件検出
        if re.search(r"個室|プライベート", query):
            request.has_private_room = True

        if re.search(r"予約|reservation", query):
            request.accepts_reservations = True

        if re.search(r"今から|すぐ|営業中", query):
            request.available_now = True

        # エリア検出
        for area_name, area_code in self.area_codes.items():
            if area_name in query:
                request.area_code = area_code
                break

        # キーワード抽出（料理名や特徴）
        keyword_candidates = []
        specialty_patterns = [
            r"(ステーキ|牛肉)", r"(海鮮|魚)", r"(野菜|ベジタリアン)",
            r"(ラーメン|麺)", r"(パン|ベーカリー)", r"(デザート|スイーツ)"
        ]

        for pattern in specialty_patterns:
            match = re.search(pattern, query)
            if match:
                keyword_candidates.append(match.group(1))

        if keyword_candidates:
            request.keyword = " ".join(keyword_candidates)

        return request

    async def _call_gurume_api(self, request: GurumeNaviSearchRequest) -> GurumeNaviResponse:
        """ぐるなび API呼び出し"""
        logger.info(f"ぐるなび検索API呼び出し: {request.cuisine_category} 範囲:{request.range_km}km")

        # API呼び出し記録
        self.request_history.append(datetime.now())
        self.daily_request_count += 1

        # プロダクション実装: 実際のぐるなびAPI呼び出し
        # 注意: 実際の使用時はぐるなびAPIキーが必要
        if not self.api_key or self.api_key.startswith("mock_"):
            logger.warning("Mock API key detected - using fallback data")
            return await self._fallback_search_results(request)

        try:
            # 実際のAPI実装はここに追加
            # import requests
            # response = requests.get(
            #     "https://api.gnavi.co.jp/RestSearchAPI/v3/",
            #     params={
            #         "keyid": self.api_key,
            #         "latitude": request.latitude,
            #         "longitude": request.longitude,
            #         "range": request.range_km
            #     }
            # )

            # 現在はフォールバック実装を使用
            return await self._fallback_search_results(request)

        except Exception as e:
            logger.error(f"ぐるなびAPI呼び出しエラー: {str(e)}")
            return GurumeNaviResponse(
                success=False,
                error_message=f"API呼び出し失敗: {str(e)}",
                results=[]
            )

    async def _fallback_search_results(self, request: GurumeNaviSearchRequest) -> GurumeNaviResponse:
        """開発用フォールバック検索結果生成"""
        fallback_restaurants = await self._generate_fallback_restaurants(request)

        # マッチング度計算と結果作成
        results = []
        for restaurant in fallback_restaurants:
            match_score = self._calculate_match_score(restaurant, request)
            if match_score >= 0.3:  # 最小マッチング度
                result = GurumeNaviSearchResult(
                    restaurant=restaurant,
                    distance_km=self._calculate_distance_km(restaurant, request),
                    match_score=match_score
                )
                results.append(result)

        # マッチング度順でソート
        results.sort(key=lambda r: r.match_score, reverse=True)

        return GurumeNaviResponse(
            success=True,
            results=results[:request.hit_per_page],
            total_hit_count=len(results),
            current_page=request.offset_page
        )

    async def _call_detail_api(self, restaurant_id: str) -> RestaurantInfo:
        """レストラン詳細API呼び出し（開発用フォールバック）"""
        logger.info(f"詳細API呼び出し: {restaurant_id}")

        return RestaurantInfo(
            restaurant_id=restaurant_id,
            name="詳細付きレストラン",
            name_kana="しょうさいつきれすとらん",
            address="東京都渋谷区渋谷1-1-1",
            access_info="JR渋谷駅徒歩5分",
            latitude=35.6595,
            longitude=139.7006,
            opening_hours=["月-金 17:00-23:00", "土日 12:00-23:00"],
            closing_days=["年末年始"],
            budget_dinner="3000-4000円",
            budget_lunch="1000-2000円",
            tel="03-1234-5678",
            reservation_url="https://example-restaurant.com/reserve",
            accepts_credit_card=True,
            has_private_room=True,
            smoking_policy="分煙",
            cuisine_genres=["和食", "居酒屋"],
            specialties=["刺身", "焼鳥", "日本酒"],
            shop_image_urls=["https://example.com/image1.jpg"],
            detail_url="https://r.gnavi.co.jp/example/",
            pr_comment="新鮮な魚介類と厳選された日本酒をお楽しみください",
            total_seats=40
        )

    async def _generate_fallback_restaurants(self, request: GurumeNaviSearchRequest) -> List[RestaurantInfo]:
        """開発用フォールバックレストランデータ生成"""
        restaurants = []

        # 料理カテゴリに応じたレストラン生成
        if request.cuisine_category == CuisineCategory.JAPANESE:
            base_names = ["和食 花月", "日本料理 松風", "懐石 竹庵", "割烹 さくら"]
        elif request.cuisine_category == CuisineCategory.ITALIAN:
            base_names = ["イタリアン ベラビスタ", "パスタ マンマ", "ピッツェリア ナポリ", "リストランテ アモーレ"]
        elif request.cuisine_category == CuisineCategory.IZAKAYA:
            base_names = ["居酒屋 のんべえ", "酒処 金魚", "飲み屋 たちばな", "居酒屋 やまびこ"]
        else:
            base_names = ["レストラン A", "レストラン B", "レストラン C", "レストラン D"]

        for i, name in enumerate(base_names):
            restaurant = RestaurantInfo(
                restaurant_id=f"gurume_fallback_{i}_{secrets.token_hex(4)}",
                name=name,
                name_kana=f"もっくれすとらん{i}",
                address=f"東京都渋谷区{i+1}-{i+2}-{i+3}",
                access_info=f"JR山手線 渋谷駅 徒歩{i+3}分",
                latitude=(request.latitude or 35.6595) + (i - 2) * 0.001,
                longitude=(request.longitude or 139.7006) + (i % 3 - 1) * 0.001,
                opening_hours=[f"月-日 {17+i%2}:00-{22+i%2}:00"],
                budget_dinner=f"{2000+i*500}-{3000+i*500}円",
                budget_lunch=f"{1000+i*200}-{1500+i*200}円",
                tel=f"03-{1000+i}-{5000+i}",
                accepts_credit_card=(i % 2 == 0),
                has_private_room=(i % 3 == 0),
                cuisine_genres=[request.cuisine_category.value if request.cuisine_category else "レストラン"],
                total_seats=20 + i * 10
            )
            restaurants.append(restaurant)

        return restaurants

    def _calculate_match_score(self, restaurant: RestaurantInfo, request: GurumeNaviSearchRequest) -> float:
        """マッチング度計算"""
        score = 0.5  # ベーススコア

        # 料理カテゴリマッチ
        if request.cuisine_category and request.cuisine_category.value in restaurant.cuisine_genres:
            score += 0.3

        # 距離による調整
        distance = self._calculate_distance_km(restaurant, request)
        if distance <= request.range_km:
            distance_score = 1.0 - (distance / request.range_km)
            score += distance_score * 0.2

        # 予算マッチ（簡易）
        if request.budget_range:
            # 実際の実装では詳細な予算比較が必要
            score += 0.1

        # 特別条件マッチ
        if request.has_private_room and restaurant.has_private_room:
            score += 0.15

        if request.accepts_reservations and restaurant.reservation_url:
            score += 0.1

        return min(1.0, score)

    def _calculate_distance_km(self, restaurant: RestaurantInfo, request: GurumeNaviSearchRequest) -> float:
        """距離計算（km）"""
        if not all([restaurant.latitude, restaurant.longitude, request.latitude, request.longitude]):
            return 0.5  # デフォルト距離

        # 簡易直線距離計算
        lat_diff = abs(restaurant.latitude - request.latitude)
        lng_diff = abs(restaurant.longitude - request.longitude)
        return ((lat_diff ** 2 + lng_diff ** 2) ** 0.5) * 111  # 概算km

    async def _check_rate_limit(self) -> bool:
        """レート制限チェック"""
        now = datetime.now()

        # 日次リセット
        if now.date() != self.last_reset_date:
            self.daily_request_count = 0
            self.last_reset_date = now.date()

        # 日次制限チェック
        if self.daily_request_count >= self.requests_per_day:
            logger.warning("ぐるなび API日次制限に達しました")
            return False

        # 秒次制限チェック
        self.request_history = [
            ts for ts in self.request_history
            if (now - ts).total_seconds() < 1
        ]

        if len(self.request_history) >= self.requests_per_second:
            await asyncio.sleep(0.2)  # 短時間待機

        return True

    def _generate_cache_key(self, request: GurumeNaviSearchRequest) -> str:
        """キャッシュキー生成"""
        key_parts = [
            str(request.latitude or ""),
            str(request.longitude or ""),
            str(request.range_km),
            request.cuisine_category.value if request.cuisine_category else "",
            request.keyword or "",
            request.budget_range.value if request.budget_range else ""
        ]
        return "_".join(key_parts)

    def _get_cached_result(self, cache_key: str) -> Optional[GurumeNaviResponse]:
        """キャッシュ結果取得"""
        if cache_key in self.search_cache:
            result, cached_time = self.search_cache[cache_key]
            if datetime.now() - cached_time < timedelta(minutes=30):
                return result
            else:
                del self.search_cache[cache_key]
        return None


class RestaurantSearchManager:
    """
    レストラン検索管理クラス
    - 高レベル検索操作
    - 複数API統合
    - インテリジェントフォールバック
    """

    def __init__(self, gurume_client: GurumeNaviClient):
        self.gurume_client = gurume_client

    async def find_restaurants_for_event(self, event_type: str, participant_count: int,
                                        latitude: float, longitude: float,
                                        preferences: List[str] = None) -> GurumeNaviResponse:
        """イベント向けレストラン検索"""
        # イベントタイプに基づく基本リクエスト作成
        base_request = self._create_event_based_request(
            event_type, participant_count, latitude, longitude, preferences
        )

        # フォールバック付き検索実行
        return await self.gurume_client.search_with_fallback(base_request)

    def _create_event_based_request(self, event_type: str, participant_count: int,
                                   latitude: float, longitude: float,
                                   preferences: List[str] = None) -> GurumeNaviSearchRequest:
        """イベントタイプベースのリクエスト作成"""
        request = GurumeNaviSearchRequest(
            latitude=latitude,
            longitude=longitude,
            party_size=participant_count
        )

        # イベントタイプ別設定
        if event_type == "dining":
            request.cuisine_category = CuisineCategory.IZAKAYA
            request.accepts_reservations = True
            request.budget_range = BudgetRange.RANGE_3000_4000

            if participant_count >= 8:
                request.has_private_room = True

        elif event_type == "lunch":
            request.budget_range = BudgetRange.RANGE_1000_2000
            request.available_now = True

        # 料理設定
        if preferences:
            for pref in preferences:
                if "和食" in pref or "日本料理" in pref:
                    request.cuisine_category = CuisineCategory.JAPANESE
                elif "イタリアン" in pref:
                    request.cuisine_category = CuisineCategory.ITALIAN
                elif "焼肉" in pref:
                    request.cuisine_category = CuisineCategory.YAKINIKU

        return request