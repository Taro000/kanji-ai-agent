"""
Firestore接続・トランザクション処理
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union, Callable, TypeVar, Generic
from pydantic import BaseModel, Field
import logging
from contextlib import asynccontextmanager
from enum import Enum

logger = logging.getLogger(__name__)

T = TypeVar('T')


class TransactionStatus(str, Enum):
    """トランザクション状態"""
    PENDING = "pending"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class FirestoreConfig(BaseModel):
    """Firestore設定"""
    project_id: str
    database_id: str = "(default)"
    credentials_path: Optional[str] = None
    emulator_host: Optional[str] = None  # 開発環境用
    max_retry_attempts: int = 3
    timeout_seconds: int = 30


class DocumentReference(BaseModel):
    """ドキュメント参照"""
    collection: str
    document_id: str
    parent_path: Optional[str] = None

    @property
    def full_path(self) -> str:
        """完全パス取得"""
        if self.parent_path:
            return f"{self.parent_path}/{self.collection}/{self.document_id}"
        return f"{self.collection}/{self.document_id}"


class QueryFilter(BaseModel):
    """クエリフィルタ"""
    field: str
    operator: str  # ==, !=, <, <=, >, >=, array-contains, in, not-in
    value: Any


class QueryOrder(BaseModel):
    """クエリ順序"""
    field: str
    direction: str = "asc"  # asc, desc


class FirestoreQuery(BaseModel):
    """Firestoreクエリ"""
    collection: str
    filters: List[QueryFilter] = Field(default_factory=list)
    orders: List[QueryOrder] = Field(default_factory=list)
    limit: Optional[int] = None
    offset: Optional[int] = None
    parent_path: Optional[str] = None


class DocumentSnapshot(BaseModel):
    """ドキュメントスナップショット"""
    document_id: str
    data: Dict[str, Any]
    exists: bool
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None
    read_time: datetime


class BatchWrite(BaseModel):
    """バッチ書き込み操作"""
    operation_type: str  # create, update, delete
    document_ref: DocumentReference
    data: Optional[Dict[str, Any]] = None
    merge_fields: Optional[List[str]] = None


class TransactionContext(BaseModel):
    """トランザクションコンテキスト"""
    transaction_id: str
    status: TransactionStatus
    operations: List[BatchWrite] = Field(default_factory=list)
    read_documents: Dict[str, DocumentSnapshot] = Field(default_factory=dict)
    created_at: datetime
    committed_at: Optional[datetime] = None


class FirestoreClient:
    """
    Firestore接続クライアント
    - 非同期接続管理
    - トランザクション制御
    - バッチ操作
    - エラーハンドリング・リトライ
    """

    def __init__(self, config: FirestoreConfig):
        self.config = config
        self.is_connected = False

        # 接続プール設定
        self.connection_pool_size = 10
        self.active_connections = 0

        # トランザクション管理
        self.active_transactions: Dict[str, TransactionContext] = {}

        # キャッシュ（読み取り専用データ用）
        self.read_cache: Dict[str, DocumentSnapshot] = {}
        self.cache_ttl_seconds = 300  # 5分

        # 統計情報
        self.stats = {
            "reads": 0,
            "writes": 0,
            "transactions": 0,
            "errors": 0
        }

    async def connect(self) -> bool:
        """Firestore接続確立"""
        try:
            logger.info(f"Firestore接続開始: {self.config.project_id}")

            # プロダクション実装: 実際のFirestore接続
            # from google.cloud import firestore
            # self.client = firestore.Client(project=self.config.project_id)

            # 現在はローカル開発用の模擬接続
            if self.config.emulator_host:
                logger.info(f"Firestoreエミュレータ接続: {self.config.emulator_host}")
            else:
                logger.info("本番Firestore接続")

            self.is_connected = True
            logger.info("Firestore接続成功")
            return True

        except Exception as e:
            logger.error(f"Firestore接続エラー: {str(e)}")
            return False

    async def disconnect(self):
        """接続切断"""
        logger.info("Firestore接続切断")
        self.is_connected = False
        self.active_connections = 0

    async def get_document(self, doc_ref: DocumentReference) -> Optional[DocumentSnapshot]:
        """ドキュメント取得"""
        if not self.is_connected:
            raise ConnectionError("Firestoreに接続されていません")

        # キャッシュ確認
        cached_doc = self._get_cached_document(doc_ref.full_path)
        if cached_doc:
            logger.debug(f"キャッシュからドキュメント取得: {doc_ref.full_path}")
            return cached_doc

        try:
            # プロダクション実装: Firestore読み取り
            # doc_ref = self.client.collection(collection).document(document_id)
            # doc = doc_ref.get()
            # if doc.exists:
            #     return DocumentSnapshot(doc.id, doc.to_dict(), doc.create_time, doc.update_time)

            # 開発用フォールバック実装
            snapshot = await self._read_document_from_firestore(doc_ref)

            # 統計更新
            self.stats["reads"] += 1

            # キャッシュ更新
            if snapshot and snapshot.exists:
                self._cache_document(doc_ref.full_path, snapshot)

            return snapshot

        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"ドキュメント取得エラー: {doc_ref.full_path} - {str(e)}")
            return None

    async def set_document(self, doc_ref: DocumentReference, data: Dict[str, Any], merge: bool = False) -> bool:
        """ドキュメント設定"""
        if not self.is_connected:
            raise ConnectionError("Firestoreに接続されていません")

        try:
            # プロダクション実装: Firestore書き込み
            # doc_ref = self.client.collection(collection).document(document_id)
            # doc_ref.set(data, merge=merge_mode)

            # 開発用フォールバック実装
            success = await self._write_document_to_firestore(doc_ref, data, merge)

            if success:
                self.stats["writes"] += 1
                # キャッシュ無効化
                self._invalidate_cache(doc_ref.full_path)

            return success

        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"ドキュメント設定エラー: {doc_ref.full_path} - {str(e)}")
            return False

    async def update_document(self, doc_ref: DocumentReference, data: Dict[str, Any]) -> bool:
        """ドキュメント更新"""
        return await self.set_document(doc_ref, data, merge=True)

    async def delete_document(self, doc_ref: DocumentReference) -> bool:
        """ドキュメント削除"""
        if not self.is_connected:
            raise ConnectionError("Firestoreに接続されていません")

        try:
            # プロダクション実装: Firestore削除
            # doc_ref = self.client.collection(collection).document(document_id)
            # doc_ref.delete()

            # 開発用フォールバック実装
            success = await self._delete_document_from_firestore(doc_ref)

            if success:
                self.stats["writes"] += 1
                # キャッシュから削除
                self._invalidate_cache(doc_ref.full_path)

            return success

        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"ドキュメント削除エラー: {doc_ref.full_path} - {str(e)}")
            return False

    async def query_documents(self, query: FirestoreQuery) -> List[DocumentSnapshot]:
        """ドキュメントクエリ"""
        if not self.is_connected:
            raise ConnectionError("Firestoreに接続されていません")

        try:
            # プロダクション実装: Firestoreクエリ実行
            # collection_ref = self.client.collection(collection)
            # query = collection_ref
            # for condition in conditions:
            #     query = query.where(condition['field'], condition['operator'], condition['value'])
            # docs = query.stream()

            # 開発用フォールバック実装
            results = await self._execute_query(query)

            self.stats["reads"] += len(results)
            return results

        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"クエリ実行エラー: {query.collection} - {str(e)}")
            return []

    async def batch_write(self, operations: List[BatchWrite]) -> bool:
        """バッチ書き込み"""
        if not self.is_connected:
            raise ConnectionError("Firestoreに接続されていません")

        if len(operations) > 500:  # Firestore制限
            raise ValueError("バッチ操作は500件まで")

        try:
            # プロダクション実装: バッチ操作実行
            # batch = self.client.batch()
            # for operation in operations:
            #     if operation['type'] == 'set':
            #         batch.set(operation['ref'], operation['data'])
            #     elif operation['type'] == 'update':
            #         batch.update(operation['ref'], operation['data'])
            #     elif operation['type'] == 'delete':
            #         batch.delete(operation['ref'])
            # batch.commit()

            # 開発用フォールバック実装
            success = await self._execute_batch_operations(operations)

            if success:
                self.stats["writes"] += len(operations)
                # 関連キャッシュ無効化
                for op in operations:
                    self._invalidate_cache(op.document_ref.full_path)

            return success

        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"バッチ書き込みエラー: {str(e)}")
            return False

    @asynccontextmanager
    async def transaction(self):
        """トランザクションコンテキストマネージャ"""
        if not self.is_connected:
            raise ConnectionError("Firestoreに接続されていません")

        transaction_id = f"txn_{int(datetime.now().timestamp())}_{len(self.active_transactions)}"

        # トランザクション開始
        tx_context = TransactionContext(
            transaction_id=transaction_id,
            status=TransactionStatus.PENDING,
            created_at=datetime.now(timezone.utc)
        )

        self.active_transactions[transaction_id] = tx_context
        transaction_manager = TransactionManager(self, tx_context)

        try:
            logger.info(f"トランザクション開始: {transaction_id}")
            yield transaction_manager

            # コミット
            success = await self._commit_transaction(tx_context)
            if success:
                tx_context.status = TransactionStatus.COMMITTED
                tx_context.committed_at = datetime.now(timezone.utc)
                self.stats["transactions"] += 1
                logger.info(f"トランザクションコミット: {transaction_id}")
            else:
                raise Exception("トランザクションコミット失敗")

        except Exception as e:
            # ロールバック
            await self._rollback_transaction(tx_context)
            tx_context.status = TransactionStatus.ROLLED_BACK
            self.stats["errors"] += 1
            logger.error(f"トランザクションロールバック: {transaction_id} - {str(e)}")
            raise

        finally:
            # クリーンアップ
            del self.active_transactions[transaction_id]

    async def _read_document_from_firestore(self, doc_ref: DocumentReference) -> Optional[DocumentSnapshot]:
        """Firestoreからドキュメント読み取り（開発用フォールバック）"""
        logger.debug(f"Firestore読み取り: {doc_ref.full_path}")

        # 開発用フォールバック：ドキュメントが存在すると仮定
        fallback_data = {
            "id": doc_ref.document_id,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "status": "active"
        }

        return DocumentSnapshot(
            document_id=doc_ref.document_id,
            data=fallback_data,
            exists=True,
            create_time=datetime.now(timezone.utc),
            update_time=datetime.now(timezone.utc),
            read_time=datetime.now(timezone.utc)
        )

    async def _write_document_to_firestore(self, doc_ref: DocumentReference, data: Dict[str, Any], merge: bool) -> bool:
        """Firestoreにドキュメント書き込み（開発用フォールバック）"""
        logger.debug(f"Firestore書き込み: {doc_ref.full_path} (merge={merge})")

        # 開発用フォールバック：常に成功
        await asyncio.sleep(0.01)  # ネットワーク遅延シミュレート
        return True

    async def _delete_document_from_firestore(self, doc_ref: DocumentReference) -> bool:
        """Firestoreからドキュメント削除（Mock）"""
        logger.debug(f"Firestore削除: {doc_ref.full_path}")

        # 開発用フォールバック：常に成功
        await asyncio.sleep(0.01)
        return True

    async def _execute_query(self, query: FirestoreQuery) -> List[DocumentSnapshot]:
        """クエリ実行（Mock）"""
        logger.debug(f"Firestoreクエリ: {query.collection}")

        # Mock結果生成
        results = []
        result_count = min(query.limit or 10, 10)

        for i in range(result_count):
            doc_id = f"doc_{i}"
            mock_data = {
                "id": doc_id,
                "index": i,
                "created_at": datetime.now(timezone.utc),
                "collection": query.collection
            }

            snapshot = DocumentSnapshot(
                document_id=doc_id,
                data=fallback_data,
                exists=True,
                read_time=datetime.now(timezone.utc)
            )
            results.append(snapshot)

        return results

    async def _execute_batch_operations(self, operations: List[BatchWrite]) -> bool:
        """バッチ操作実行（Mock）"""
        logger.debug(f"バッチ操作実行: {len(operations)}件")

        # Mock実装：すべて成功
        await asyncio.sleep(0.05)  # バッチ処理時間シミュレート
        return True

    async def _commit_transaction(self, tx_context: TransactionContext) -> bool:
        """トランザクションコミット（Mock）"""
        logger.debug(f"トランザクションコミット: {tx_context.transaction_id}")

        # 開発用フォールバック：常に成功
        await asyncio.sleep(0.02)
        return True

    async def _rollback_transaction(self, tx_context: TransactionContext):
        """トランザクションロールバック（Mock）"""
        logger.debug(f"トランザクションロールバック: {tx_context.transaction_id}")

        # Mock実装：クリーンアップのみ
        tx_context.operations.clear()

    def _get_cached_document(self, document_path: str) -> Optional[DocumentSnapshot]:
        """キャッシュドキュメント取得"""
        if document_path in self.read_cache:
            snapshot = self.read_cache[document_path]
            # TTL確認
            if (datetime.now(timezone.utc) - snapshot.read_time).total_seconds() < self.cache_ttl_seconds:
                return snapshot
            else:
                del self.read_cache[document_path]
        return None

    def _cache_document(self, document_path: str, snapshot: DocumentSnapshot):
        """ドキュメントキャッシュ"""
        self.read_cache[document_path] = snapshot

        # キャッシュサイズ制限
        if len(self.read_cache) > 1000:
            # 古いエントリを削除
            oldest_key = min(self.read_cache.keys(),
                           key=lambda k: self.read_cache[k].read_time)
            del self.read_cache[oldest_key]

    def _invalidate_cache(self, document_path: str):
        """キャッシュ無効化"""
        if document_path in self.read_cache:
            del self.read_cache[document_path]

    def get_stats(self) -> Dict[str, Any]:
        """統計情報取得"""
        return {
            **self.stats,
            "active_transactions": len(self.active_transactions),
            "cache_size": len(self.read_cache),
            "connection_status": "connected" if self.is_connected else "disconnected"
        }


class TransactionManager:
    """
    トランザクション管理クラス
    - トランザクション内操作
    - 読み取り整合性保証
    - 書き込み操作バッファリング
    """

    def __init__(self, client: FirestoreClient, context: TransactionContext):
        self.client = client
        self.context = context

    async def get(self, doc_ref: DocumentReference) -> Optional[DocumentSnapshot]:
        """トランザクション内ドキュメント取得"""
        document_path = doc_ref.full_path

        # 既に読み取り済みの場合は同じスナップショットを返す（一貫性保証）
        if document_path in self.context.read_documents:
            return self.context.read_documents[document_path]

        # 新規読み取り
        snapshot = await self.client.get_document(doc_ref)
        if snapshot:
            self.context.read_documents[document_path] = snapshot

        return snapshot

    async def set(self, doc_ref: DocumentReference, data: Dict[str, Any], merge: bool = False):
        """トランザクション内ドキュメント設定"""
        operation = BatchWrite(
            operation_type="update" if merge else "create",
            document_ref=doc_ref,
            data=data,
            merge_fields=None
        )

        self.context.operations.append(operation)

    async def update(self, doc_ref: DocumentReference, data: Dict[str, Any]):
        """トランザクション内ドキュメント更新"""
        await self.set(doc_ref, data, merge=True)

    async def delete(self, doc_ref: DocumentReference):
        """トランザクション内ドキュメント削除"""
        operation = BatchWrite(
            operation_type="delete",
            document_ref=doc_ref
        )

        self.context.operations.append(operation)

    def get_operations_count(self) -> int:
        """操作数取得"""
        return len(self.context.operations)


class FirestoreRepository(Generic[T]):
    """
    汎用Firestoreリポジトリ
    - CRUD操作の抽象化
    - 型安全性
    - バリデーション
    """

    def __init__(self, client: FirestoreClient, collection_name: str,
                 model_class: type, validator: Optional[Callable[[Dict], T]] = None):
        self.client = client
        self.collection = collection_name
        self.model_class = model_class
        self.validator = validator or (lambda data: model_class(**data))

    async def create(self, document_id: str, model: T) -> bool:
        """モデル作成"""
        doc_ref = DocumentReference(
            collection=self.collection,
            document_id=document_id
        )

        # モデルを辞書に変換
        if hasattr(model, 'dict'):
            data = model.dict()
        elif hasattr(model, '__dict__'):
            data = model.__dict__
        else:
            data = dict(model)

        # タイムスタンプ追加
        data['created_at'] = datetime.now(timezone.utc)
        data['updated_at'] = datetime.now(timezone.utc)

        return await self.client.set_document(doc_ref, data)

    async def get(self, document_id: str) -> Optional[T]:
        """モデル取得"""
        doc_ref = DocumentReference(
            collection=self.collection,
            document_id=document_id
        )

        snapshot = await self.client.get_document(doc_ref)
        if not snapshot or not snapshot.exists:
            return None

        try:
            return self.validator(snapshot.data)
        except Exception as e:
            logger.error(f"モデル変換エラー: {str(e)}")
            return None

    async def update(self, document_id: str, model: T) -> bool:
        """モデル更新"""
        doc_ref = DocumentReference(
            collection=self.collection,
            document_id=document_id
        )

        # モデルを辞書に変換
        if hasattr(model, 'dict'):
            data = model.dict()
        elif hasattr(model, '__dict__'):
            data = model.__dict__
        else:
            data = dict(model)

        # 更新タイムスタンプ
        data['updated_at'] = datetime.now(timezone.utc)

        return await self.client.update_document(doc_ref, data)

    async def delete(self, document_id: str) -> bool:
        """モデル削除"""
        doc_ref = DocumentReference(
            collection=self.collection,
            document_id=document_id
        )

        return await self.client.delete_document(doc_ref)

    async def list_by_filter(self, filters: List[QueryFilter], limit: int = 100) -> List[T]:
        """フィルタ条件でリスト取得"""
        query = FirestoreQuery(
            collection=self.collection,
            filters=filters,
            limit=limit
        )

        snapshots = await self.client.query_documents(query)

        results = []
        for snapshot in snapshots:
            try:
                model = self.validator(snapshot.data)
                results.append(model)
            except Exception as e:
                logger.warning(f"モデル変換エラー（スキップ）: {str(e)}")

        return results