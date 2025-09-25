"""
内部Event APIエンドポイントのコントラクトテスト。

このテストは、内部Event APIエンドポイント（/api/events）が
OpenAPI仕様に従って正しく動作することを検証します。

参照: specs/002-slack-bot-ai/contracts/internal_event_api.yaml
"""

from typing import Any, Dict, List
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# NOTE: これらのインポートは実装が存在するまで失敗します（TDD）
# これはTDDアプローチに期待される必要な動作です
try:
    from src.main import app
    from src.models.event import Event, EventStatus, EventType
    from src.api.events import EventsRouter
except ImportError:
    # TDD段階では期待される - テストは最初に失敗する必要があります
    pytest.skip("実装がまだ利用できません", allow_module_level=True)


class TestInternalEventAPI:
    """内部Event APIコントラクトテスト。"""

    @pytest.fixture
    def client(self) -> TestClient:
        """テスト用APIクライアント。"""
        return TestClient(app)

    @pytest.fixture
    def event_data(self) -> Dict[str, Any]:
        """有効なイベントデータ。"""
        return {
            "title": "チームランチミーティング",
            "description": "月次チームランチで情報共有と親睦を深める",
            "event_type": "dining",
            "organizer_id": "U0123456789",
            "channel_id": "C1234567890",
            "participants": [
                {
                    "user_id": "U1111111111",
                    "display_name": "田中太郎",
                    "email": "tanaka@example.com"
                },
                {
                    "user_id": "U2222222222",
                    "display_name": "佐藤花子",
                    "email": "sato@example.com"
                }
            ],
            "proposed_dates": [
                {
                    "start_time": "2024-03-20T12:00:00+09:00",
                    "end_time": "2024-03-20T13:30:00+09:00"
                },
                {
                    "start_time": "2024-03-22T12:00:00+09:00",
                    "end_time": "2024-03-22T13:30:00+09:00"
                }
            ],
            "venue_preferences": {
                "type": "restaurant",
                "location": "渋谷",
                "budget_per_person": 2000,
                "capacity": 5
            }
        }

    @pytest.fixture
    def japanese_event_data(self) -> Dict[str, Any]:
        """日本語イベントデータ。"""
        return {
            "title": "勉強会：AI・機械学習入門",
            "description": "初心者向けのAI・機械学習勉強会です。\n\n内容：\n- 機械学習の基礎\n- Pythonでの実装\n- 実践的な演習",
            "event_type": "meeting",
            "organizer_id": "U0123456789",
            "channel_id": "C1234567890",
            "participants": [
                {
                    "user_id": "U3333333333",
                    "display_name": "山田一郎",
                    "email": "yamada@example.com"
                }
            ],
            "proposed_dates": [
                {
                    "start_time": "2024-03-25T14:00:00+09:00",
                    "end_time": "2024-03-25T17:00:00+09:00"
                }
            ],
            "venue_preferences": {
                "type": "meeting_room",
                "location": "会議室A",
                "capacity": 15
            }
        }

    def test_create_event_success(
        self,
        client: TestClient,
        event_data: Dict[str, Any]
    ) -> None:
        """イベント作成成功テスト。"""
        response = client.post(
            "/api/events",
            json=event_data,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 201
        created_event = response.json()

        # レスポンス構造検証
        assert "id" in created_event
        assert created_event["title"] == event_data["title"]
        assert created_event["event_type"] == event_data["event_type"]
        assert created_event["status"] == "proposed"
        assert created_event["organizer_id"] == event_data["organizer_id"]
        assert len(created_event["participants"]) == len(event_data["participants"])

        # タイムスタンプ検証
        assert "created_at" in created_event
        assert "updated_at" in created_event

    def test_create_japanese_event(
        self,
        client: TestClient,
        japanese_event_data: Dict[str, Any]
    ) -> None:
        """日本語イベント作成テスト。"""
        response = client.post(
            "/api/events",
            json=japanese_event_data,
            headers={"Content-Type": "application/json; charset=utf-8"}
        )

        assert response.status_code == 201
        created_event = response.json()

        # 日本語文字が正しく保存されているか確認
        assert "勉強会" in created_event["title"]
        assert "機械学習" in created_event["description"]

    def test_get_event_success(
        self,
        client: TestClient,
        event_data: Dict[str, Any]
    ) -> None:
        """イベント取得成功テスト。"""
        # まずイベントを作成
        create_response = client.post("/api/events", json=event_data)
        event_id = create_response.json()["id"]

        # イベントを取得
        response = client.get(f"/api/events/{event_id}")

        assert response.status_code == 200
        event = response.json()

        assert event["id"] == event_id
        assert event["title"] == event_data["title"]

    def test_get_event_not_found(self, client: TestClient) -> None:
        """存在しないイベント取得テスト。"""
        response = client.get("/api/events/nonexistent-id")

        assert response.status_code == 404
        error = response.json()
        assert "detail" in error
        assert "not found" in error["detail"].lower()

    def test_update_event_success(
        self,
        client: TestClient,
        event_data: Dict[str, Any]
    ) -> None:
        """イベント更新成功テスト。"""
        # イベント作成
        create_response = client.post("/api/events", json=event_data)
        event_id = create_response.json()["id"]

        # 更新データ
        update_data = {
            "title": "チームランチミーティング（更新版）",
            "description": "更新された説明文",
            "status": "confirmed"
        }

        # イベント更新
        response = client.patch(
            f"/api/events/{event_id}",
            json=update_data
        )

        assert response.status_code == 200
        updated_event = response.json()

        assert updated_event["title"] == update_data["title"]
        assert updated_event["description"] == update_data["description"]
        assert updated_event["status"] == update_data["status"]

    def test_delete_event_success(
        self,
        client: TestClient,
        event_data: Dict[str, Any]
    ) -> None:
        """イベント削除成功テスト。"""
        # イベント作成
        create_response = client.post("/api/events", json=event_data)
        event_id = create_response.json()["id"]

        # イベント削除
        response = client.delete(f"/api/events/{event_id}")

        assert response.status_code == 204

        # 削除確認
        get_response = client.get(f"/api/events/{event_id}")
        assert get_response.status_code == 404

    def test_list_events_success(
        self,
        client: TestClient,
        event_data: Dict[str, Any]
    ) -> None:
        """イベント一覧取得成功テスト。"""
        # 複数のイベントを作成
        for i in range(3):
            event_copy = event_data.copy()
            event_copy["title"] = f"イベント{i+1}"
            client.post("/api/events", json=event_copy)

        # イベント一覧取得
        response = client.get("/api/events")

        assert response.status_code == 200
        events = response.json()

        assert "items" in events
        assert "total" in events
        assert "page" in events
        assert "size" in events
        assert len(events["items"]) >= 3

    def test_list_events_with_filters(
        self,
        client: TestClient,
        event_data: Dict[str, Any]
    ) -> None:
        """フィルター付きイベント一覧取得テスト。"""
        # 異なるタイプのイベントを作成
        dining_event = event_data.copy()
        dining_event["event_type"] = "dining"
        dining_event["title"] = "ランチイベント"

        meeting_event = event_data.copy()
        meeting_event["event_type"] = "meeting"
        meeting_event["title"] = "ミーティングイベント"

        client.post("/api/events", json=dining_event)
        client.post("/api/events", json=meeting_event)

        # タイプでフィルター
        response = client.get("/api/events?event_type=dining")

        assert response.status_code == 200
        events = response.json()

        # diningタイプのイベントのみ取得されることを確認
        for event in events["items"]:
            assert event["event_type"] == "dining"

    def test_list_events_pagination(
        self,
        client: TestClient,
        event_data: Dict[str, Any]
    ) -> None:
        """ページネーション付きイベント一覧取得テスト。"""
        # 多数のイベントを作成
        for i in range(10):
            event_copy = event_data.copy()
            event_copy["title"] = f"ページネーションテスト{i+1}"
            client.post("/api/events", json=event_copy)

        # 1ページ目（サイズ5）
        response = client.get("/api/events?page=1&size=5")

        assert response.status_code == 200
        page1 = response.json()

        assert len(page1["items"]) == 5
        assert page1["page"] == 1
        assert page1["size"] == 5

        # 2ページ目
        response = client.get("/api/events?page=2&size=5")

        assert response.status_code == 200
        page2 = response.json()

        assert page2["page"] == 2
        # 1ページ目と2ページ目のアイテムが異なることを確認
        page1_ids = {item["id"] for item in page1["items"]}
        page2_ids = {item["id"] for item in page2["items"]}
        assert not page1_ids.intersection(page2_ids)

    def test_add_participant_success(
        self,
        client: TestClient,
        event_data: Dict[str, Any]
    ) -> None:
        """参加者追加成功テスト。"""
        # イベント作成
        create_response = client.post("/api/events", json=event_data)
        event_id = create_response.json()["id"]

        # 新しい参加者
        new_participant = {
            "user_id": "U9999999999",
            "display_name": "新参加者",
            "email": "new@example.com"
        }

        # 参加者追加
        response = client.post(
            f"/api/events/{event_id}/participants",
            json=new_participant
        )

        assert response.status_code == 201

        # イベント確認
        get_response = client.get(f"/api/events/{event_id}")
        event = get_response.json()

        participant_ids = [p["user_id"] for p in event["participants"]]
        assert new_participant["user_id"] in participant_ids

    def test_remove_participant_success(
        self,
        client: TestClient,
        event_data: Dict[str, Any]
    ) -> None:
        """参加者削除成功テスト。"""
        # イベント作成
        create_response = client.post("/api/events", json=event_data)
        event_id = create_response.json()["id"]

        # 参加者のuser_id
        participant_id = event_data["participants"][0]["user_id"]

        # 参加者削除
        response = client.delete(
            f"/api/events/{event_id}/participants/{participant_id}"
        )

        assert response.status_code == 204

        # イベント確認
        get_response = client.get(f"/api/events/{event_id}")
        event = get_response.json()

        participant_ids = [p["user_id"] for p in event["participants"]]
        assert participant_id not in participant_ids

    def test_update_participant_response(
        self,
        client: TestClient,
        event_data: Dict[str, Any]
    ) -> None:
        """参加者回答更新テスト。"""
        # イベント作成
        create_response = client.post("/api/events", json=event_data)
        event_id = create_response.json()["id"]

        participant_id = event_data["participants"][0]["user_id"]

        # 参加回答更新
        response_data = {
            "status": "confirmed",
            "message": "参加します！楽しみです。"
        }

        response = client.patch(
            f"/api/events/{event_id}/participants/{participant_id}/response",
            json=response_data
        )

        assert response.status_code == 200

        # イベント確認
        get_response = client.get(f"/api/events/{event_id}")
        event = get_response.json()

        participant = next(
            p for p in event["participants"]
            if p["user_id"] == participant_id
        )
        assert participant["response_status"] == "confirmed"
        assert participant["response_message"] == response_data["message"]

    def test_create_event_validation(self, client: TestClient) -> None:
        """イベント作成バリデーションテスト。"""
        invalid_cases = [
            # 必須フィールド不足
            {
                "description": "タイトルなし",
                "event_type": "dining"
            },
            # 無効なイベントタイプ
            {
                "title": "テストイベント",
                "event_type": "invalid_type"
            },
            # 無効な日付形式
            {
                "title": "テストイベント",
                "event_type": "dining",
                "proposed_dates": [
                    {
                        "start_time": "invalid-date",
                        "end_time": "2024-03-20T13:30:00+09:00"
                    }
                ]
            },
            # 終了時刻が開始時刻より前
            {
                "title": "テストイベント",
                "event_type": "dining",
                "proposed_dates": [
                    {
                        "start_time": "2024-03-20T14:00:00+09:00",
                        "end_time": "2024-03-20T12:00:00+09:00"
                    }
                ]
            }
        ]

        for invalid_data in invalid_cases:
            response = client.post("/api/events", json=invalid_data)
            assert response.status_code == 422

    def test_event_status_transitions(
        self,
        client: TestClient,
        event_data: Dict[str, Any]
    ) -> None:
        """イベントステータス遷移テスト。"""
        # イベント作成（初期ステータス: proposed）
        create_response = client.post("/api/events", json=event_data)
        event_id = create_response.json()["id"]

        # ステータス遷移テスト
        status_transitions = [
            ("proposed", "scheduling"),
            ("scheduling", "venue_selection"),
            ("venue_selection", "confirmed"),
            ("confirmed", "completed")
        ]

        for from_status, to_status in status_transitions:
            response = client.patch(
                f"/api/events/{event_id}",
                json={"status": to_status}
            )
            assert response.status_code == 200

            # ステータス確認
            get_response = client.get(f"/api/events/{event_id}")
            event = get_response.json()
            assert event["status"] == to_status

    def test_event_search(
        self,
        client: TestClient,
        event_data: Dict[str, Any]
    ) -> None:
        """イベント検索テスト。"""
        # 複数のイベントを作成
        events_to_create = [
            {"title": "Pythonランチ勉強会", "description": "Python学習"},
            {"title": "TypeScript勉強会", "description": "フロントエンド開発"},
            {"title": "チームランチ", "description": "月次ランチミーティング"}
        ]

        for event_data_item in events_to_create:
            event_copy = event_data.copy()
            event_copy.update(event_data_item)
            client.post("/api/events", json=event_copy)

        # 検索テスト
        search_cases = [
            ("q=Python", "Python"),
            ("q=勉強会", "勉強会"),
            ("q=ランチ", "ランチ")
        ]

        for query, expected_term in search_cases:
            response = client.get(f"/api/events?{query}")
            assert response.status_code == 200

            events = response.json()
            # 検索結果に期待するキーワードが含まれることを確認
            found = any(
                expected_term in event["title"] or expected_term in event["description"]
                for event in events["items"]
            )
            assert found

    def test_api_error_responses(self, client: TestClient) -> None:
        """APIエラーレスポンステスト。"""
        # 404エラー
        response = client.get("/api/events/nonexistent")
        assert response.status_code == 404
        assert "detail" in response.json()

        # 422エラー（バリデーションエラー）
        response = client.post("/api/events", json={"invalid": "data"})
        assert response.status_code == 422
        assert "detail" in response.json()

    def test_api_response_headers(
        self,
        client: TestClient,
        event_data: Dict[str, Any]
    ) -> None:
        """APIレスポンスヘッダーテスト。"""
        response = client.post("/api/events", json=event_data)

        # Content-Typeヘッダー確認
        assert response.headers["content-type"] == "application/json"

        # CORS関連ヘッダー確認（必要に応じて）
        # assert "access-control-allow-origin" in response.headers

    def test_concurrent_event_operations(
        self,
        client: TestClient,
        event_data: Dict[str, Any]
    ) -> None:
        """同時イベント操作テスト。"""
        import threading
        import time

        results = []

        def create_event(index):
            event_copy = event_data.copy()
            event_copy["title"] = f"並行イベント{index}"
            response = client.post("/api/events", json=event_copy)
            results.append(response.status_code)

        # 複数スレッドで同時にイベント作成
        threads = []
        for i in range(5):
            thread = threading.Thread(target=create_event, args=(i,))
            threads.append(thread)
            thread.start()

        # 全スレッド完了を待機
        for thread in threads:
            thread.join()

        # 全ての作成が成功することを確認
        assert all(status == 201 for status in results)