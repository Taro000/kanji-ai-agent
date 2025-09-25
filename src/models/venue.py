"""
Venue エンティティモデル

レストラン、会議室、イベント会場の情報と予約状態を表現します。
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import uuid4

from pydantic import BaseModel, Field, validator


class VenueType(str, Enum):
    """会場タイプ列挙"""
    RESTAURANT = "restaurant"       # レストラン・飲食店
    MEETING_ROOM = "meeting_room"   # 会議室
    EXTERNAL = "external"           # 外部会場


class BookingStatus(str, Enum):
    """予約ステータス列挙"""
    PENDING = "pending"                # 予約待ち
    CONFIRMED = "confirmed"            # 予約確定
    FAILED = "failed"                 # 予約失敗
    MANUAL_REQUIRED = "manual_required"  # 手動予約必要


class PriceLevel(int, Enum):
    """価格レベル（Google Places API準拠）"""
    FREE = 0          # 無料
    INEXPENSIVE = 1   # 安価
    MODERATE = 2      # 普通
    EXPENSIVE = 3     # 高価
    VERY_EXPENSIVE = 4  # 非常に高価


class VenueFeature(BaseModel):
    """会場の特徴・設備"""
    feature_name: str = Field(..., description="設備・特徴名")
    available: bool = Field(default=True, description="利用可能か")
    description: Optional[str] = Field(None, description="詳細説明")


class BusinessHours(BaseModel):
    """営業時間"""
    day_of_week: int = Field(..., description="曜日（0=日曜、1=月曜...6=土曜）")
    open_time: str = Field(..., description="開店時刻（HH:MM形式）")
    close_time: str = Field(..., description="閉店時刻（HH:MM形式）")
    is_closed: bool = Field(default=False, description="定休日か")

    @validator('day_of_week')
    def validate_day_of_week(cls, v):
        """曜日の検証"""
        if v < 0 or v > 6:
            raise ValueError('曜日は0-6の範囲である必要があります')
        return v

    @validator('open_time', 'close_time')
    def validate_time_format(cls, v):
        """時刻形式の検証"""
        import re
        if not re.match(r'^([01][0-9]|2[0-3]):[0-5][0-9]$', v):
            raise ValueError('時刻はHH:MM形式である必要があります')
        return v


class Venue(BaseModel):
    """会場エンティティ"""

    # 基本識別情報
    venue_id: str = Field(default_factory=lambda: str(uuid4()))
    event_id: str = Field(..., description="関連するイベントID")
    venue_type: VenueType = Field(..., description="会場タイプ")

    # 基本情報
    name: str = Field(..., description="会場名")
    address: str = Field(..., description="住所")
    description: Optional[str] = Field(None, description="会場説明")

    # 外部API参照
    google_places_id: Optional[str] = Field(None, description="Google Places ID")
    google_maps_url: Optional[str] = Field(None, description="Google Maps URL")
    gurume_id: Optional[str] = Field(None, description="ぐるなび店舗ID")
    tabelog_id: Optional[str] = Field(None, description="食べログ店舗ID")

    # 位置情報
    latitude: Optional[float] = Field(None, description="緯度")
    longitude: Optional[float] = Field(None, description="経度")
    nearest_station: Optional[str] = Field(None, description="最寄り駅")
    walking_minutes: Optional[int] = Field(None, description="最寄り駅からの徒歩分数")

    # 収容・設備情報
    capacity: int = Field(..., description="最大収容人数")
    minimum_capacity: Optional[int] = Field(None, description="最小利用人数")
    private_room_available: bool = Field(default=False, description="個室利用可能")
    features: List[VenueFeature] = Field(default_factory=list, description="設備・特徴一覧")

    # 予約情報
    booking_status: BookingStatus = Field(default=BookingStatus.PENDING, description="予約ステータス")
    booking_reference: Optional[str] = Field(None, description="予約番号・参照番号")
    booking_details: Optional[str] = Field(None, description="予約詳細・特記事項")
    booking_deadline: Optional[datetime] = Field(None, description="予約変更期限")

    # 連絡先情報
    contact_phone: Optional[str] = Field(None, description="電話番号")
    contact_email: Optional[str] = Field(None, description="メールアドレス")
    website_url: Optional[str] = Field(None, description="ウェブサイトURL")
    menu_url: Optional[str] = Field(None, description="メニューURL")

    # 料金情報
    estimated_cost_per_person: Optional[int] = Field(None, description="一人当たり予算（円）")
    price_level: Optional[PriceLevel] = Field(None, description="価格レベル")
    course_menu_available: bool = Field(default=False, description="コースメニュー有無")
    budget_range_min: Optional[int] = Field(None, description="予算下限（円）")
    budget_range_max: Optional[int] = Field(None, description="予算上限（円）")

    # 営業時間
    business_hours: List[BusinessHours] = Field(default_factory=list, description="営業時間")
    special_hours: Optional[str] = Field(None, description="特別営業時間・注意事項")

    # 評価・レビュー
    rating: Optional[float] = Field(None, description="評価（1.0-5.0）")
    review_count: Optional[int] = Field(None, description="レビュー数")
    user_ratings_total: Optional[int] = Field(None, description="Google総評価数")

    # アクセシビリティ
    wheelchair_accessible: bool = Field(default=False, description="車椅子対応")
    elevator_available: bool = Field(default=False, description="エレベーター有無")
    parking_available: bool = Field(default=False, description="駐車場有無")

    # メタデータ
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_verified_at: Optional[datetime] = Field(None, description="最終確認日時")

    # 内部管理情報
    selection_score: Optional[float] = Field(None, description="選定スコア（0.0-1.0）")
    admin_notes: Optional[str] = Field(None, description="管理者メモ")

    class Config:
        """Pydantic設定"""
        use_enum_values = True
        validate_assignment = True
        arbitrary_types_allowed = True

    @validator('name')
    def validate_name(cls, v):
        """会場名の検証"""
        if not v or len(v.strip()) < 1:
            raise ValueError('会場名は必須です')
        return v.strip()

    @validator('address')
    def validate_address(cls, v):
        """住所の検証"""
        if not v or len(v.strip()) < 5:
            raise ValueError('住所は5文字以上である必要があります')
        return v.strip()

    @validator('capacity')
    def validate_capacity(cls, v):
        """収容人数の検証"""
        if v <= 0 or v > 10000:
            raise ValueError('収容人数は1-10000人の範囲である必要があります')
        return v

    @validator('minimum_capacity')
    def validate_minimum_capacity(cls, v, values):
        """最小利用人数の検証"""
        if v is not None:
            if v <= 0:
                raise ValueError('最小利用人数は1人以上である必要があります')
            if 'capacity' in values and v > values['capacity']:
                raise ValueError('最小利用人数は最大収容人数以下である必要があります')
        return v

    @validator('estimated_cost_per_person', 'budget_range_min', 'budget_range_max')
    def validate_cost(cls, v):
        """料金の検証"""
        if v is not None and (v < 0 or v > 100000):
            raise ValueError('料金は0円以上100,000円以下である必要があります')
        return v

    @validator('rating')
    def validate_rating(cls, v):
        """評価の検証"""
        if v is not None and (v < 1.0 or v > 5.0):
            raise ValueError('評価は1.0-5.0の範囲である必要があります')
        return v

    @validator('latitude')
    def validate_latitude(cls, v):
        """緯度の検証"""
        if v is not None and (v < -90 or v > 90):
            raise ValueError('緯度は-90～90の範囲である必要があります')
        return v

    @validator('longitude')
    def validate_longitude(cls, v):
        """経度の検証"""
        if v is not None and (v < -180 or v > 180):
            raise ValueError('経度は-180～180の範囲である必要があります')
        return v

    @validator('walking_minutes')
    def validate_walking_minutes(cls, v):
        """徒歩時間の検証"""
        if v is not None and (v < 0 or v > 120):
            raise ValueError('徒歩時間は0-120分の範囲である必要があります')
        return v

    def update_timestamp(self) -> None:
        """更新タイムスタンプを現在時刻に設定"""
        self.updated_at = datetime.utcnow()

    def confirm_booking(self, reference: Optional[str] = None, details: Optional[str] = None) -> None:
        """予約を確定"""
        self.booking_status = BookingStatus.CONFIRMED
        if reference:
            self.booking_reference = reference
        if details:
            self.booking_details = details
        self.update_timestamp()

    def fail_booking(self, reason: Optional[str] = None) -> None:
        """予約失敗を記録"""
        self.booking_status = BookingStatus.FAILED
        if reason:
            self.booking_details = f"予約失敗: {reason}"
        self.update_timestamp()

    def require_manual_booking(self, note: Optional[str] = None) -> None:
        """手動予約必要としてマーク"""
        self.booking_status = BookingStatus.MANUAL_REQUIRED
        if note:
            self.booking_details = f"手動予約必要: {note}"
        self.update_timestamp()

    def add_feature(self, feature_name: str, available: bool = True, description: Optional[str] = None) -> None:
        """設備・特徴を追加"""
        feature = VenueFeature(
            feature_name=feature_name,
            available=available,
            description=description
        )
        self.features.append(feature)
        self.update_timestamp()

    def has_feature(self, feature_name: str) -> bool:
        """指定された設備があるかチェック"""
        return any(
            f.feature_name.lower() == feature_name.lower() and f.available
            for f in self.features
        )

    def is_open_at(self, target_datetime: datetime) -> bool:
        """指定日時に営業しているかチェック"""
        day_of_week = target_datetime.weekday()
        # Pythonのweekday()は月曜が0、日曜が6なので調整
        day_of_week = (day_of_week + 1) % 7

        target_time = target_datetime.strftime("%H:%M")

        for hours in self.business_hours:
            if hours.day_of_week == day_of_week:
                if hours.is_closed:
                    return False
                return hours.open_time <= target_time <= hours.close_time

        # 営業時間情報がない場合は営業中と仮定
        return True

    def calculate_suitability_score(
        self,
        participant_count: int,
        budget_per_person: Optional[int] = None,
        required_features: Optional[List[str]] = None
    ) -> float:
        """会場適合性スコアを計算（0.0-1.0）"""
        score = 0.0

        # 収容人数適合性（40%）
        if self.minimum_capacity and participant_count < self.minimum_capacity:
            capacity_score = 0.0
        elif participant_count > self.capacity:
            capacity_score = 0.0
        else:
            # 理想的な利用率は70-80%
            utilization = participant_count / self.capacity
            if 0.7 <= utilization <= 0.8:
                capacity_score = 1.0
            elif utilization < 0.7:
                capacity_score = utilization / 0.7
            else:
                capacity_score = max(0.0, 1.0 - (utilization - 0.8) / 0.2)

        score += capacity_score * 0.4

        # 予算適合性（30%）
        budget_score = 1.0
        if budget_per_person and self.estimated_cost_per_person:
            if self.estimated_cost_per_person <= budget_per_person:
                budget_score = 1.0
            else:
                # 予算オーバーの程度に応じて減点
                over_ratio = self.estimated_cost_per_person / budget_per_person
                budget_score = max(0.0, 1.0 - (over_ratio - 1.0))

        score += budget_score * 0.3

        # 必要設備適合性（20%）
        feature_score = 1.0
        if required_features:
            matched_features = sum(1 for feature in required_features if self.has_feature(feature))
            feature_score = matched_features / len(required_features) if required_features else 1.0

        score += feature_score * 0.2

        # 評価・人気度（10%）
        rating_score = 0.5  # デフォルト
        if self.rating:
            rating_score = (self.rating - 1.0) / 4.0  # 1-5を0-1に正規化

        score += rating_score * 0.1

        return min(1.0, max(0.0, score))

    def get_booking_status_display(self) -> str:
        """予約ステータスの日本語表示"""
        status_display = {
            BookingStatus.PENDING: "予約待ち",
            BookingStatus.CONFIRMED: "予約確定",
            BookingStatus.FAILED: "予約失敗",
            BookingStatus.MANUAL_REQUIRED: "手動予約必要"
        }
        return status_display.get(self.booking_status, "不明")

    def get_venue_type_display(self) -> str:
        """会場タイプの日本語表示"""
        type_display = {
            VenueType.RESTAURANT: "レストラン",
            VenueType.MEETING_ROOM: "会議室",
            VenueType.EXTERNAL: "外部会場"
        }
        return type_display.get(self.venue_type, "不明")

    def is_booking_confirmed(self) -> bool:
        """予約が確定しているかチェック"""
        return self.booking_status == BookingStatus.CONFIRMED

    def needs_manual_intervention(self) -> bool:
        """手動対応が必要かチェック"""
        return self.booking_status in [BookingStatus.FAILED, BookingStatus.MANUAL_REQUIRED]

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換（Firestore保存用）"""
        return {
            "venue_id": self.venue_id,
            "event_id": self.event_id,
            "venue_type": self.venue_type.value,
            "name": self.name,
            "address": self.address,
            "description": self.description,
            "google_places_id": self.google_places_id,
            "google_maps_url": self.google_maps_url,
            "gurume_id": self.gurume_id,
            "tabelog_id": self.tabelog_id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "nearest_station": self.nearest_station,
            "walking_minutes": self.walking_minutes,
            "capacity": self.capacity,
            "minimum_capacity": self.minimum_capacity,
            "private_room_available": self.private_room_available,
            "features": [feature.dict() for feature in self.features],
            "booking_status": self.booking_status.value,
            "booking_reference": self.booking_reference,
            "booking_details": self.booking_details,
            "booking_deadline": self.booking_deadline.isoformat() if self.booking_deadline else None,
            "contact_phone": self.contact_phone,
            "contact_email": self.contact_email,
            "website_url": self.website_url,
            "menu_url": self.menu_url,
            "estimated_cost_per_person": self.estimated_cost_per_person,
            "price_level": self.price_level.value if self.price_level else None,
            "course_menu_available": self.course_menu_available,
            "budget_range_min": self.budget_range_min,
            "budget_range_max": self.budget_range_max,
            "business_hours": [hours.dict() for hours in self.business_hours],
            "special_hours": self.special_hours,
            "rating": self.rating,
            "review_count": self.review_count,
            "user_ratings_total": self.user_ratings_total,
            "wheelchair_accessible": self.wheelchair_accessible,
            "elevator_available": self.elevator_available,
            "parking_available": self.parking_available,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_verified_at": self.last_verified_at.isoformat() if self.last_verified_at else None,
            "selection_score": self.selection_score,
            "admin_notes": self.admin_notes
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Venue":
        """辞書から Venue インスタンスを作成"""
        # datetimeフィールドの変換
        datetime_fields = ["booking_deadline", "created_at", "updated_at", "last_verified_at"]
        for field in datetime_fields:
            if data.get(field):
                data[field] = datetime.fromisoformat(data[field])

        # featuresリストの変換
        if data.get("features"):
            data["features"] = [VenueFeature(**feature_data) for feature_data in data["features"]]

        # business_hoursリストの変換
        if data.get("business_hours"):
            data["business_hours"] = [BusinessHours(**hours_data) for hours_data in data["business_hours"]]

        # price_levelの変換
        if data.get("price_level") is not None:
            data["price_level"] = PriceLevel(data["price_level"])

        return cls(**data)