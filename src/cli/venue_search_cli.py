"""
Venue Search Testing CLI - 会場検索テスト用CLI
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, track
from rich.prompt import Prompt, IntPrompt, FloatPrompt
import logging

# プロジェクト内インポート
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from src.integrations.google_places import GooglePlacesClient, PlaceSearchManager, PlaceSearchRequest, PlaceType, PriceLevel
from src.integrations.gurume_navi import GurumeNaviClient, RestaurantSearchManager, GurumeNaviSearchRequest, CuisineCategory, BudgetRange
from src.models.venue import Venue, VenueType, BookingStatus

console = Console()
app = typer.Typer(help="Venue Search Testing CLI - 会場検索テストツール")

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VenueSearchTestResult(typer.Enum):
    """検索テスト結果タイプ"""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    ERROR = "error"


class VenueSearchCLI:
    """
    会場検索CLI
    - Google Places・ぐるなび API テスト
    - 検索パラメータ最適化
    - API比較・評価
    """

    def __init__(self):
        # 環境変数からAPIキーを取得（フォールバック用ダミーキー）
        google_api_key = os.getenv("GOOGLE_PLACES_API_KEY", "development_fallback_key")
        gurume_api_key = os.getenv("GURUME_NAVI_API_KEY", "development_fallback_key")

        self.google_client = GooglePlacesClient(google_api_key)
        self.gurume_client = GurumeNaviClient(gurume_api_key)
        self.place_manager = PlaceSearchManager(self.google_client)
        self.restaurant_manager = RestaurantSearchManager(self.gurume_client)
        self.console = Console()

        # テスト統計
        self.test_stats = {
            "google_places": {"requests": 0, "successes": 0, "errors": 0},
            "gurume_navi": {"requests": 0, "successes": 0, "errors": 0},
            "total_venues_found": 0,
            "average_response_time": 0.0
        }

        # 東京主要エリア座標
        self.tokyo_areas = {
            "渋谷": {"lat": 35.6595, "lng": 139.7006},
            "新宿": {"lat": 35.6896, "lng": 139.6917},
            "銀座": {"lat": 35.6762, "lng": 139.7649},
            "六本木": {"lat": 35.6627, "lng": 139.7314},
            "恵比寿": {"lat": 35.6467, "lng": 139.7109},
            "品川": {"lat": 35.6284, "lng": 139.7387},
            "池袋": {"lat": 35.7295, "lng": 139.7109},
            "上野": {"lat": 35.7141, "lng": 139.7774}
        }

    async def test_google_places_search(self, search_params: Dict[str, Any]) -> Dict[str, Any]:
        """Google Places検索テスト"""
        start_time = datetime.now()

        try:
            request = PlaceSearchRequest(
                query=search_params.get("query"),
                location_lat=search_params["lat"],
                location_lng=search_params["lng"],
                radius_meters=search_params.get("radius", 1000),
                place_type=PlaceType(search_params.get("place_type", "restaurant")),
                min_rating=search_params.get("min_rating", 3.5),
                max_price_level=PriceLevel(search_params.get("max_price_level", 3)),
                open_now=search_params.get("open_now", False)
            )

            result = await self.google_client.search_places(request)
            response_time = (datetime.now() - start_time).total_seconds()

            self.test_stats["google_places"]["requests"] += 1
            if result.success:
                self.test_stats["google_places"]["successes"] += 1
                self.test_stats["total_venues_found"] += len(result.results)

            return {
                "success": result.success,
                "results_count": len(result.results) if result.success else 0,
                "results": [self._format_google_result(r) for r in result.results] if result.success else [],
                "response_time": response_time,
                "error_message": result.error_message if not result.success else None,
                "quota_exceeded": result.quota_exceeded
            }

        except Exception as e:
            self.test_stats["google_places"]["errors"] += 1
            return {
                "success": False,
                "results_count": 0,
                "results": [],
                "response_time": (datetime.now() - start_time).total_seconds(),
                "error_message": str(e),
                "quota_exceeded": False
            }

    async def test_gurume_navi_search(self, search_params: Dict[str, Any]) -> Dict[str, Any]:
        """ぐるなび検索テスト"""
        start_time = datetime.now()

        try:
            request = GurumeNaviSearchRequest(
                latitude=search_params["lat"],
                longitude=search_params["lng"],
                range_km=search_params.get("range_km", 1.0),
                cuisine_category=CuisineCategory(search_params.get("cuisine_category", "japanese")) if search_params.get("cuisine_category") else None,
                keyword=search_params.get("keyword"),
                budget_range=BudgetRange(search_params.get("budget_range", "range_2000_3000")) if search_params.get("budget_range") else None,
                party_size=search_params.get("party_size"),
                accepts_reservations=search_params.get("accepts_reservations", False),
                has_private_room=search_params.get("has_private_room", False)
            )

            result = await self.gurume_client.search_restaurants(request)
            response_time = (datetime.now() - start_time).total_seconds()

            self.test_stats["gurume_navi"]["requests"] += 1
            if result.success:
                self.test_stats["gurume_navi"]["successes"] += 1
                self.test_stats["total_venues_found"] += len(result.results)

            return {
                "success": result.success,
                "results_count": len(result.results) if result.success else 0,
                "results": [self._format_gurume_result(r) for r in result.results] if result.success else [],
                "response_time": response_time,
                "error_message": result.error_message if not result.success else None,
                "rate_limit_exceeded": result.rate_limit_exceeded
            }

        except Exception as e:
            self.test_stats["gurume_navi"]["errors"] += 1
            return {
                "success": False,
                "results_count": 0,
                "results": [],
                "response_time": (datetime.now() - start_time).total_seconds(),
                "error_message": str(e),
                "rate_limit_exceeded": False
            }

    async def compare_api_results(self, search_params: Dict[str, Any]) -> Dict[str, Any]:
        """API結果比較"""
        # 並行して両APIを実行
        google_task = self.test_google_places_search(search_params)
        gurume_task = self.test_gurume_navi_search(search_params)

        google_result, gurume_result = await asyncio.gather(google_task, gurume_task)

        # 結果比較分析
        comparison = {
            "google_places": google_result,
            "gurume_navi": gurume_result,
            "comparison_analysis": self._analyze_api_comparison(google_result, gurume_result),
            "search_params": search_params,
            "timestamp": datetime.now().isoformat()
        }

        return comparison

    def _analyze_api_comparison(self, google_result: Dict[str, Any], gurume_result: Dict[str, Any]) -> Dict[str, Any]:
        """API比較分析"""
        analysis = {
            "response_time_comparison": {
                "google_faster": google_result["response_time"] < gurume_result["response_time"],
                "time_difference": abs(google_result["response_time"] - gurume_result["response_time"])
            },
            "results_count_comparison": {
                "google_count": google_result["results_count"],
                "gurume_count": gurume_result["results_count"],
                "total_unique_results": google_result["results_count"] + gurume_result["results_count"]  # 簡易計算
            },
            "success_rate": {
                "google_success": google_result["success"],
                "gurume_success": gurume_result["success"],
                "both_successful": google_result["success"] and gurume_result["success"]
            },
            "recommendation": self._generate_api_recommendation(google_result, gurume_result)
        }

        return analysis

    def _generate_api_recommendation(self, google_result: Dict[str, Any], gurume_result: Dict[str, Any]) -> str:
        """API推奨事項生成"""
        if not google_result["success"] and not gurume_result["success"]:
            return "両APIとも失敗。検索条件を見直してください。"

        if google_result["success"] and not gurume_result["success"]:
            return "Google Placesのみ成功。ぐるなびAPIの条件を緩和することを推奨。"

        if not google_result["success"] and gurume_result["success"]:
            return "ぐるなびのみ成功。Google Places APIの条件を緩和することを推奨。"

        # 両方成功の場合の推奨
        if google_result["results_count"] > gurume_result["results_count"]:
            return "Google Placesが多くの結果を返しました。幅広い検索に適しています。"
        elif gurume_result["results_count"] > google_result["results_count"]:
            return "ぐるなびが多くの結果を返しました。日本の飲食店検索に適しています。"
        else:
            return "両APIとも同程度の結果。併用することで網羅性が向上します。"

    def _format_google_result(self, result) -> Dict[str, Any]:
        """Google Places結果フォーマット"""
        place = result.place
        return {
            "source": "google_places",
            "place_id": place.place_id,
            "name": place.name,
            "address": place.formatted_address,
            "rating": place.rating,
            "price_level": place.price_level.value if place.price_level else None,
            "location": place.location,
            "distance_meters": result.distance_meters,
            "relevance_score": result.relevance_score,
            "place_types": place.place_types
        }

    def _format_gurume_result(self, result) -> Dict[str, Any]:
        """ぐるなび結果フォーマット"""
        restaurant = result.restaurant
        return {
            "source": "gurume_navi",
            "restaurant_id": restaurant.restaurant_id,
            "name": restaurant.name,
            "address": restaurant.address,
            "budget_dinner": restaurant.budget_dinner,
            "budget_lunch": restaurant.budget_lunch,
            "cuisine_genres": restaurant.cuisine_genres,
            "has_private_room": restaurant.has_private_room,
            "accepts_credit_card": restaurant.accepts_credit_card,
            "distance_km": result.distance_km,
            "match_score": result.match_score
        }

    async def benchmark_search_performance(self, test_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """検索パフォーマンスベンチマーク"""
        benchmark_results = {
            "test_cases_count": len(test_cases),
            "individual_results": [],
            "aggregate_stats": {
                "google_places": {"total_time": 0, "avg_results": 0, "success_rate": 0},
                "gurume_navi": {"total_time": 0, "avg_results": 0, "success_rate": 0}
            },
            "performance_comparison": {}
        }

        for i, test_case in enumerate(test_cases):
            console.print(f"📊 ベンチマークテスト {i+1}/{len(test_cases)}: {test_case.get('name', 'Unnamed')}")

            comparison = await self.compare_api_results(test_case["search_params"])
            benchmark_results["individual_results"].append({
                "test_case": test_case,
                "results": comparison
            })

            # 統計更新
            google_result = comparison["google_places"]
            gurume_result = comparison["gurume_navi"]

            benchmark_results["aggregate_stats"]["google_places"]["total_time"] += google_result["response_time"]
            benchmark_results["aggregate_stats"]["google_places"]["avg_results"] += google_result["results_count"]

            benchmark_results["aggregate_stats"]["gurume_navi"]["total_time"] += gurume_result["response_time"]
            benchmark_results["aggregate_stats"]["gurume_navi"]["avg_results"] += gurume_result["results_count"]

        # 平均値計算
        test_count = len(test_cases)
        for api in ["google_places", "gurume_navi"]:
            stats = benchmark_results["aggregate_stats"][api]
            stats["avg_response_time"] = stats["total_time"] / test_count
            stats["avg_results_count"] = stats["avg_results"] / test_count

            success_count = sum(1 for result in benchmark_results["individual_results"]
                              if result["results"][api]["success"])
            stats["success_rate"] = success_count / test_count

        # パフォーマンス比較
        google_stats = benchmark_results["aggregate_stats"]["google_places"]
        gurume_stats = benchmark_results["aggregate_stats"]["gurume_navi"]

        benchmark_results["performance_comparison"] = {
            "faster_api": "google_places" if google_stats["avg_response_time"] < gurume_stats["avg_response_time"] else "gurume_navi",
            "more_results_api": "google_places" if google_stats["avg_results_count"] > gurume_stats["avg_results_count"] else "gurume_navi",
            "more_reliable_api": "google_places" if google_stats["success_rate"] > gurume_stats["success_rate"] else "gurume_navi",
            "overall_recommendation": self._generate_overall_recommendation(google_stats, gurume_stats)
        }

        return benchmark_results


    def _generate_overall_recommendation(self, google_stats: Dict[str, Any], gurume_stats: Dict[str, Any]) -> str:
        """総合推奨事項生成"""
        google_score = 0
        gurume_score = 0

        # レスポンス時間スコア
        if google_stats["avg_response_time"] < gurume_stats["avg_response_time"]:
            google_score += 1
        else:
            gurume_score += 1

        # 結果数スコア
        if google_stats["avg_results_count"] > gurume_stats["avg_results_count"]:
            google_score += 1
        else:
            gurume_score += 1

        # 信頼性スコア
        if google_stats["success_rate"] > gurume_stats["success_rate"]:
            google_score += 1
        else:
            gurume_score += 1

        if google_score > gurume_score:
            return "Google Placesが総合的に優れています。"
        elif gurume_score > google_score:
            return "ぐるなびが総合的に優れています。"
        else:
            return "両APIの性能が同等です。用途に応じて使い分けを推奨します。"


# CLI コマンド定義
@app.command()
def search_venues(
    area: str = typer.Option("渋谷", help="検索エリア"),
    venue_type: str = typer.Option("restaurant", help="会場タイプ"),
    api: str = typer.Option("both", help="使用API (google/gurume/both)"),
    output_file: str = typer.Option(None, help="結果出力ファイル")
):
    """会場検索実行"""

    async def _search():
        cli = VenueSearchCLI()

        if area not in cli.tokyo_areas:
            console.print(f"❌ 未対応エリア: {area}", style="red")
            console.print(f"対応エリア: {', '.join(cli.tokyo_areas.keys())}")
            return

        coords = cli.tokyo_areas[area]
        search_params = {
            "lat": coords["lat"],
            "lng": coords["lng"],
            "place_type": venue_type,
            "radius": 1000
        }

        console.print(f"🔍 {area}エリアで会場検索開始...")

        if api in ["google", "both"]:
            console.print("Google Places API検索中...")
            google_result = await cli.test_google_places_search(search_params)
            _display_search_results("Google Places", google_result)

        if api in ["gurume", "both"]:
            console.print("ぐるなび API検索中...")
            gurume_result = await cli.test_gurume_navi_search(search_params)
            _display_search_results("ぐるなび", gurume_result)

        if api == "both":
            console.print("API比較分析中...")
            comparison = await cli.compare_api_results(search_params)

            # 比較結果表示
            analysis = comparison["comparison_analysis"]
            console.print(f"\n📊 API比較結果:")
            console.print(f"推奨事項: {analysis['recommendation']}")

            # 出力ファイル保存
            if output_file:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(comparison, f, ensure_ascii=False, indent=2)
                console.print(f"📁 比較結果を保存: {output_file}")

    asyncio.run(_search())


@app.command()
def interactive_search():
    """インタラクティブ検索"""

    async def _interactive():
        cli = VenueSearchCLI()

        console.print("🔍 インタラクティブ会場検索")

        # エリア選択
        area_options = list(cli.tokyo_areas.keys())
        console.print(f"利用可能エリア: {', '.join(area_options)}")
        area = Prompt.ask("検索エリアを選択してください", choices=area_options, default="渋谷")

        # 検索タイプ選択
        venue_types = ["restaurant", "cafe", "bar", "meeting_room"]
        venue_type = Prompt.ask("会場タイプを選択してください", choices=venue_types, default="restaurant")

        # 検索半径
        radius = IntPrompt.ask("検索半径（メートル）", default=1000)

        # 最小評価
        min_rating = FloatPrompt.ask("最小評価（1-5）", default=3.5)

        # 検索実行
        coords = cli.tokyo_areas[area]
        search_params = {
            "lat": coords["lat"],
            "lng": coords["lng"],
            "place_type": venue_type,
            "radius": radius,
            "min_rating": min_rating
        }

        comparison = await cli.compare_api_results(search_params)

        # 結果表示
        console.print(f"\n🎯 検索結果 ({area}エリア)")
        _display_comparison_results(comparison)

    asyncio.run(_interactive())


@app.command()
def benchmark(
    config_file: str = typer.Option("benchmark_config.json", help="ベンチマーク設定ファイル"),
    output_dir: str = typer.Option("./benchmark_results", help="結果出力ディレクトリ")
):
    """パフォーマンスベンチマーク実行"""

    async def _benchmark():
        cli = VenueSearchCLI()

        # 設定ファイル読み込み（存在しない場合はデフォルト生成）
        if not Path(config_file).exists():
            default_config = _create_default_benchmark_config(cli.tokyo_areas)
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=2)
            console.print(f"📝 デフォルト設定ファイルを生成: {config_file}")

        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # ベンチマーク実行
        console.print(f"⚡ ベンチマーク開始: {len(config['test_cases'])}ケース")

        results = await cli.benchmark_search_performance(config['test_cases'])

        # 結果出力
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        results_file = Path(output_dir) / "benchmark_results.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)

        # 結果表示
        _display_benchmark_results(results)

        console.print(f"📊 ベンチマーク完了。結果: {output_dir}/")

    asyncio.run(_benchmark())


@app.command()
def stats():
    """検索統計表示"""
    cli = VenueSearchCLI()

    table = Table(title="Venue Search Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Google Places", style="green")
    table.add_column("ぐるなび", style="blue")

    stats = cli.test_stats

    table.add_row("総リクエスト数",
                  str(stats["google_places"]["requests"]),
                  str(stats["gurume_navi"]["requests"]))

    table.add_row("成功数",
                  str(stats["google_places"]["successes"]),
                  str(stats["gurume_navi"]["successes"]))

    table.add_row("エラー数",
                  str(stats["google_places"]["errors"]),
                  str(stats["gurume_navi"]["errors"]))

    # 成功率計算
    google_rate = (stats["google_places"]["successes"] / stats["google_places"]["requests"] * 100) if stats["google_places"]["requests"] > 0 else 0
    gurume_rate = (stats["gurume_navi"]["successes"] / stats["gurume_navi"]["requests"] * 100) if stats["gurume_navi"]["requests"] > 0 else 0

    table.add_row("成功率",
                  f"{google_rate:.1f}%",
                  f"{gurume_rate:.1f}%")

    console.print(table)
    console.print(f"\n📍 総発見会場数: {stats['total_venues_found']}")


def _display_search_results(api_name: str, result: Dict[str, Any]):
    """検索結果表示"""
    if result["success"]:
        console.print(f"✅ {api_name}: {result['results_count']}件 ({result['response_time']:.2f}s)", style="green")
        if result["results_count"] > 0:
            # 上位3件表示
            for i, venue in enumerate(result["results"][:3]):
                console.print(f"  {i+1}. {venue['name']} - {venue.get('address', 'N/A')}")
    else:
        console.print(f"❌ {api_name}: 検索失敗 - {result['error_message']}", style="red")


def _display_comparison_results(comparison: Dict[str, Any]):
    """比較結果表示"""
    google_result = comparison["google_places"]
    gurume_result = comparison["gurume_navi"]
    analysis = comparison["comparison_analysis"]

    # 結果統計
    table = Table(title="API Comparison Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Google Places", style="green")
    table.add_column("ぐるなび", style="blue")

    table.add_row("結果数", str(google_result["results_count"]), str(gurume_result["results_count"]))
    table.add_row("レスポンス時間", f"{google_result['response_time']:.2f}s", f"{gurume_result['response_time']:.2f}s")
    table.add_row("成功", "✅" if google_result["success"] else "❌", "✅" if gurume_result["success"] else "❌")

    console.print(table)
    console.print(f"\n💡 {analysis['recommendation']}")


def _display_benchmark_results(results: Dict[str, Any]):
    """ベンチマーク結果表示"""
    console.print(f"\n⚡ ベンチマーク結果 ({results['test_cases_count']}ケース)")

    # 統計テーブル
    table = Table(title="Performance Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Google Places", style="green")
    table.add_column("ぐるなび", style="blue")

    google_stats = results["aggregate_stats"]["google_places"]
    gurume_stats = results["aggregate_stats"]["gurume_navi"]

    table.add_row("平均レスポンス時間", f"{google_stats['avg_response_time']:.2f}s", f"{gurume_stats['avg_response_time']:.2f}s")
    table.add_row("平均結果数", f"{google_stats['avg_results_count']:.1f}", f"{gurume_stats['avg_results_count']:.1f}")
    table.add_row("成功率", f"{google_stats['success_rate']*100:.1f}%", f"{gurume_stats['success_rate']*100:.1f}%")

    console.print(table)

    # 推奨事項
    comparison = results["performance_comparison"]
    console.print(f"\n🏆 最速API: {comparison['faster_api']}")
    console.print(f"🎯 最多結果API: {comparison['more_results_api']}")
    console.print(f"🛡️ 最信頼API: {comparison['more_reliable_api']}")
    console.print(f"💡 総合推奨: {comparison['overall_recommendation']}")


def _create_default_benchmark_config(tokyo_areas: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
    """デフォルトベンチマーク設定作成"""
    test_cases = []

    for area_name, coords in list(tokyo_areas.items())[:3]:  # 最初の3エリア
        for venue_type in ["restaurant", "cafe"]:
            test_case = {
                "name": f"{area_name}_{venue_type}",
                "search_params": {
                    "lat": coords["lat"],
                    "lng": coords["lng"],
                    "place_type": venue_type,
                    "radius": 1000,
                    "min_rating": 3.5
                }
            }
            test_cases.append(test_case)

    return {"test_cases": test_cases}


if __name__ == "__main__":
    app()