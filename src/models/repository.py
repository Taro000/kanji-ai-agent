"""
Firestore Repository 基底クラス

CRUD操作、トランザクション、暗号化機能を提供します。
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Type, TypeVar, Generic, Callable
from cryptography.fernet import Fernet
import os
import base64

from google.cloud import firestore
from google.cloud.firestore import Transaction, Query
from pydantic import BaseModel

# ログ設定
logger = logging.getLogger(__name__)

# 型変数
T = TypeVar('T', bound=BaseModel)


class RepositoryError(Exception):
    """リポジトリエラー基底クラス"""
    pass


class DocumentNotFoundError(RepositoryError):
    """ドキュメント未発見エラー"""
    pass


class ValidationError(RepositoryError):
    """バリデーションエラー"""
    pass


class EncryptionError(RepositoryError):
    """暗号化エラー"""
    pass


class EncryptionManager:
    """暗号化・復号化管理"""

    def __init__(self, encryption_key: Optional[str] = None):
        """
        暗号化マネージャーを初期化

        Args:
            encryption_key: Base64エンコードされた暗号化キー
        """
        if encryption_key is None:
            encryption_key = os.getenv('ENCRYPTION_KEY')

        if not encryption_key:
            # 開発環境用のデフォルトキー（本番では必ず環境変数を設定）
            logger.warning("暗号化キーが設定されていません。デフォルトキーを使用します。")
            encryption_key = Fernet.generate_key().decode()

        try:
            self.fernet = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
        except Exception as e:
            raise EncryptionError(f"暗号化キーの初期化に失敗しました: {e}")

    def encrypt(self, data: str) -> str:
        """文字列を暗号化"""
        try:
            encrypted_bytes = self.fernet.encrypt(data.encode('utf-8'))
            return base64.b64encode(encrypted_bytes).decode('utf-8')
        except Exception as e:
            raise EncryptionError(f"暗号化に失敗しました: {e}")

    def decrypt(self, encrypted_data: str) -> str:
        """暗号化された文字列を復号化"""
        try:
            encrypted_bytes = base64.b64decode(encrypted_data.encode('utf-8'))
            decrypted_bytes = self.fernet.decrypt(encrypted_bytes)
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            raise EncryptionError(f"復号化に失敗しました: {e}")

    def encrypt_dict(self, data: Dict[str, Any], encrypt_fields: List[str]) -> Dict[str, Any]:
        """辞書の指定フィールドを暗号化"""
        result = data.copy()
        for field in encrypt_fields:
            if field in result and result[field] is not None:
                result[field] = self.encrypt(str(result[field]))
        return result

    def decrypt_dict(self, data: Dict[str, Any], encrypt_fields: List[str]) -> Dict[str, Any]:
        """辞書の指定フィールドを復号化"""
        result = data.copy()
        for field in encrypt_fields:
            if field in result and result[field] is not None:
                try:
                    result[field] = self.decrypt(result[field])
                except EncryptionError:
                    # 暗号化されていないデータの可能性
                    logger.warning(f"フィールド {field} の復号化に失敗しました（暗号化されていない可能性）")
        return result


class BaseRepository(ABC, Generic[T]):
    """Firestore リポジトリ基底クラス"""

    def __init__(
        self,
        collection_name: str,
        model_class: Type[T],
        firestore_client: Optional[firestore.Client] = None,
        encryption_manager: Optional[EncryptionManager] = None
    ):
        """
        リポジトリを初期化

        Args:
            collection_name: Firestoreコレクション名
            model_class: エンティティのPydanticモデルクラス
            firestore_client: Firestoreクライアント
            encryption_manager: 暗号化マネージャー
        """
        self.collection_name = collection_name
        self.model_class = model_class
        self.db = firestore_client or firestore.Client()
        self.collection = self.db.collection(collection_name)
        self.encryption_manager = encryption_manager or EncryptionManager()

        # モデル固有の設定
        self.id_field = self._get_id_field()
        self.encrypted_fields = self._get_encrypted_fields()
        self.ttl_field = self._get_ttl_field()

    @abstractmethod
    def _get_id_field(self) -> str:
        """IDフィールド名を返す（継承クラスで実装）"""
        pass

    def _get_encrypted_fields(self) -> List[str]:
        """暗号化対象フィールドのリストを返す（オーバーライド可能）"""
        return []

    def _get_ttl_field(self) -> Optional[str]:
        """TTLフィールド名を返す（オーバーライド可能）"""
        return None

    def _prepare_data_for_storage(self, entity: T) -> Dict[str, Any]:
        """ストレージ用にデータを準備"""
        data = entity.to_dict() if hasattr(entity, 'to_dict') else entity.dict()

        # 暗号化
        if self.encrypted_fields:
            data = self.encryption_manager.encrypt_dict(data, self.encrypted_fields)

        # TTL設定
        if self.ttl_field and self.ttl_field not in data:
            # デフォルトで30日後に期限切れ
            data[self.ttl_field] = datetime.utcnow() + timedelta(days=30)

        return data

    def _prepare_data_from_storage(self, data: Dict[str, Any]) -> T:
        """ストレージからデータを復元"""
        # 復号化
        if self.encrypted_fields:
            data = self.encryption_manager.decrypt_dict(data, self.encrypted_fields)

        # モデルインスタンス作成
        if hasattr(self.model_class, 'from_dict'):
            return self.model_class.from_dict(data)
        else:
            return self.model_class(**data)

    async def create(self, entity: T) -> T:
        """エンティティを作成"""
        try:
            data = self._prepare_data_for_storage(entity)
            entity_id = getattr(entity, self.id_field)

            # ドキュメント存在確認
            doc_ref = self.collection.document(entity_id)
            if (await doc_ref.get()).exists:
                raise ValidationError(f"ID {entity_id} のドキュメントは既に存在します")

            await doc_ref.set(data)
            logger.info(f"{self.collection_name}に新しいドキュメントを作成: {entity_id}")

            return entity

        except Exception as e:
            logger.error(f"{self.collection_name}ドキュメント作成エラー: {e}")
            raise RepositoryError(f"作成に失敗しました: {e}")

    async def get_by_id(self, entity_id: str) -> Optional[T]:
        """IDでエンティティを取得"""
        try:
            doc_ref = self.collection.document(entity_id)
            doc = await doc_ref.get()

            if not doc.exists:
                return None

            data = doc.to_dict()
            return self._prepare_data_from_storage(data)

        except Exception as e:
            logger.error(f"{self.collection_name}ドキュメント取得エラー: {e}")
            raise RepositoryError(f"取得に失敗しました: {e}")

    async def update(self, entity: T) -> T:
        """エンティティを更新"""
        try:
            entity_id = getattr(entity, self.id_field)
            data = self._prepare_data_for_storage(entity)

            doc_ref = self.collection.document(entity_id)
            if not (await doc_ref.get()).exists:
                raise DocumentNotFoundError(f"ID {entity_id} のドキュメントが見つかりません")

            await doc_ref.update(data)
            logger.info(f"{self.collection_name}ドキュメントを更新: {entity_id}")

            return entity

        except DocumentNotFoundError:
            raise
        except Exception as e:
            logger.error(f"{self.collection_name}ドキュメント更新エラー: {e}")
            raise RepositoryError(f"更新に失敗しました: {e}")

    async def delete(self, entity_id: str) -> bool:
        """エンティティを削除"""
        try:
            doc_ref = self.collection.document(entity_id)
            doc = await doc_ref.get()

            if not doc.exists:
                return False

            await doc_ref.delete()
            logger.info(f"{self.collection_name}ドキュメントを削除: {entity_id}")

            return True

        except Exception as e:
            logger.error(f"{self.collection_name}ドキュメント削除エラー: {e}")
            raise RepositoryError(f"削除に失敗しました: {e}")

    async def list_all(
        self,
        limit: Optional[int] = None,
        order_by: Optional[str] = None,
        ascending: bool = True
    ) -> List[T]:
        """全エンティティを一覧取得"""
        try:
            query = self.collection

            if order_by:
                direction = Query.ASCENDING if ascending else Query.DESCENDING
                query = query.order_by(order_by, direction=direction)

            if limit:
                query = query.limit(limit)

            docs = await query.get()

            results = []
            for doc in docs:
                data = doc.to_dict()
                entity = self._prepare_data_from_storage(data)
                results.append(entity)

            return results

        except Exception as e:
            logger.error(f"{self.collection_name}一覧取得エラー: {e}")
            raise RepositoryError(f"一覧取得に失敗しました: {e}")

    async def find_by_field(
        self,
        field_name: str,
        value: Any,
        limit: Optional[int] = None
    ) -> List[T]:
        """指定フィールドでエンティティを検索"""
        try:
            query = self.collection.where(field_name, '==', value)

            if limit:
                query = query.limit(limit)

            docs = await query.get()

            results = []
            for doc in docs:
                data = doc.to_dict()
                entity = self._prepare_data_from_storage(data)
                results.append(entity)

            return results

        except Exception as e:
            logger.error(f"{self.collection_name}検索エラー: {e}")
            raise RepositoryError(f"検索に失敗しました: {e}")

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """エンティティ数をカウント"""
        try:
            query = self.collection

            if filters:
                for field, value in filters.items():
                    query = query.where(field, '==', value)

            docs = await query.get()
            return len(docs)

        except Exception as e:
            logger.error(f"{self.collection_name}カウントエラー: {e}")
            raise RepositoryError(f"カウントに失敗しました: {e}")

    async def exists(self, entity_id: str) -> bool:
        """エンティティの存在確認"""
        try:
            doc_ref = self.collection.document(entity_id)
            doc = await doc_ref.get()
            return doc.exists

        except Exception as e:
            logger.error(f"{self.collection_name}存在確認エラー: {e}")
            raise RepositoryError(f"存在確認に失敗しました: {e}")

    async def batch_create(self, entities: List[T]) -> List[T]:
        """バッチでエンティティを作成"""
        try:
            batch = self.db.batch()

            for entity in entities:
                entity_id = getattr(entity, self.id_field)
                data = self._prepare_data_for_storage(entity)
                doc_ref = self.collection.document(entity_id)
                batch.set(doc_ref, data)

            await batch.commit()
            logger.info(f"{self.collection_name}に{len(entities)}件のドキュメントをバッチ作成")

            return entities

        except Exception as e:
            logger.error(f"{self.collection_name}バッチ作成エラー: {e}")
            raise RepositoryError(f"バッチ作成に失敗しました: {e}")

    async def transaction_update(
        self,
        entity_id: str,
        update_func: Callable[[T], T]
    ) -> T:
        """トランザクション内でエンティティを更新"""
        @firestore.transactional
        async def _update_in_transaction(transaction: Transaction) -> T:
            doc_ref = self.collection.document(entity_id)
            doc = await doc_ref.get(transaction=transaction)

            if not doc.exists:
                raise DocumentNotFoundError(f"ID {entity_id} のドキュメントが見つかりません")

            # 現在のデータを取得してエンティティに変換
            current_data = doc.to_dict()
            current_entity = self._prepare_data_from_storage(current_data)

            # 更新関数を適用
            updated_entity = update_func(current_entity)

            # 更新データを準備
            updated_data = self._prepare_data_for_storage(updated_entity)

            # トランザクション内で更新
            transaction.update(doc_ref, updated_data)

            return updated_entity

        try:
            transaction = self.db.transaction()
            result = await _update_in_transaction(transaction)
            logger.info(f"{self.collection_name}ドキュメントをトランザクション更新: {entity_id}")
            return result

        except DocumentNotFoundError:
            raise
        except Exception as e:
            logger.error(f"{self.collection_name}トランザクション更新エラー: {e}")
            raise RepositoryError(f"トランザクション更新に失敗しました: {e}")

    async def cleanup_expired(self) -> int:
        """期限切れドキュメントをクリーンアップ"""
        if not self.ttl_field:
            return 0

        try:
            now = datetime.utcnow()
            query = self.collection.where(self.ttl_field, '<', now)
            docs = await query.get()

            deleted_count = 0
            batch = self.db.batch()

            for doc in docs:
                batch.delete(doc.reference)
                deleted_count += 1

                # バッチサイズ制限（Firestoreは500件まで）
                if deleted_count % 500 == 0:
                    await batch.commit()
                    batch = self.db.batch()

            if deleted_count % 500 != 0:
                await batch.commit()

            logger.info(f"{self.collection_name}から{deleted_count}件の期限切れドキュメントを削除")
            return deleted_count

        except Exception as e:
            logger.error(f"{self.collection_name}クリーンアップエラー: {e}")
            raise RepositoryError(f"クリーンアップに失敗しました: {e}")

    async def paginate(
        self,
        page_size: int = 10,
        page_token: Optional[str] = None,
        order_by: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """ページネーション付きでエンティティを取得"""
        try:
            query = self.collection

            # フィルター適用
            if filters:
                for field, value in filters.items():
                    query = query.where(field, '==', value)

            # 並び順設定
            if order_by:
                query = query.order_by(order_by)

            # ページング
            if page_token:
                # page_tokenから開始位置を復元
                start_after_doc = self.collection.document(page_token)
                query = query.start_after(start_after_doc)

            query = query.limit(page_size + 1)  # 次ページ有無確認のため+1

            docs = await query.get()

            # 結果処理
            results = []
            has_next_page = len(docs) > page_size

            for i, doc in enumerate(docs):
                if i >= page_size:  # page_size+1件目は次ページ判定用
                    break
                data = doc.to_dict()
                entity = self._prepare_data_from_storage(data)
                results.append(entity)

            # 次ページトークン生成
            next_page_token = None
            if has_next_page and results:
                last_entity = results[-1]
                next_page_token = getattr(last_entity, self.id_field)

            return {
                "items": results,
                "next_page_token": next_page_token,
                "has_next_page": has_next_page,
                "page_size": page_size
            }

        except Exception as e:
            logger.error(f"{self.collection_name}ページネーションエラー: {e}")
            raise RepositoryError(f"ページネーションに失敗しました: {e}")


class EventRepository(BaseRepository):
    """Event エンティティ用リポジトリ（具体例）"""

    def _get_id_field(self) -> str:
        return "event_id"

    def _get_encrypted_fields(self) -> List[str]:
        return []  # Eventには暗号化フィールドなし


class ParticipantRepository(BaseRepository):
    """Participant エンティティ用リポジトリ（具体例）"""

    def _get_id_field(self) -> str:
        return "participant_id"

    def _get_encrypted_fields(self) -> List[str]:
        return ["google_calendar_email", "oauth_token_encrypted"]


class CoordinationSessionRepository(BaseRepository):
    """CoordinationSession エンティティ用リポジトリ（具体例）"""

    def _get_id_field(self) -> str:
        return "session_id"

    def _get_ttl_field(self) -> str:
        return "expires_at"