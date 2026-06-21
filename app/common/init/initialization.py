"""
애플리케이션 초기화 서비스.

부팅 흐름은 두 가지:
- startup_lightweight: 매 startup 시 호출. 연결 확인 + 인메모리 인덱스만.
- full_initialization: 최초 배포/시드 필요 시 1회 호출 (admin endpoint 또는 AUTO_INIT_ON_STARTUP=1).

무거운 작업 (시드 데이터 삽입, 벡터 인덱싱, 가상 질문 생성)은 admin API로 분리되어 있다.
"""
from typing import Any, Dict, Optional

import chromadb

from app.common.dependency.dependencies import initialize_dependencies
from app.common.logging.logging_config import get_logger
from app.infrastructure.loaders.classroom_loader import load_classrooms
from app.infrastructure.loaders.content_hierarchy_loader import load_content_hierarchy
from app.infrastructure.loaders.hypothetical_questions_loader import build_hypothetical_questions
from app.infrastructure.loaders.seed_mongo_loader import seed_mongo_data
from app.infrastructure.loaders.stage1_cards_loader import load_stage1_cards
from app.infrastructure.loaders.stage2_problems_loader import load_stage2_problems
from app.infrastructure.loaders.stage3_problems_loader import load_stage3_problems
from app.domains.developer.service.indexing_service import get_indexing_service
from app.infrastructure.db.mongo.indexes import ensure_mongo_indexes
from app.infrastructure.db.mongo.mongo_client import get_mongo_client
from app.infrastructure.db.vector.vector_db import initialize_vector_db
from app.infrastructure.embedding.embedding_model import get_embedding_model
from app.infrastructure.search.bm25_retriever import get_bm25_retriever

logger = get_logger(__name__)


class InitializationService:
    """startup 부담을 줄이기 위해 lightweight / heavy 작업을 분리한 초기화 서비스."""

    def __init__(self):
        self.vector_db = None
        self.indexing_service = None

    # ------------------------------------------------------------------
    # Startup (lightweight)
    # ------------------------------------------------------------------

    async def startup_lightweight(self) -> Dict[str, Any]:
        """
        매 startup에서 호출. 다음만 수행한다:
        - 의존성 초기화 (OpenAI client, 임베딩 모델 — RAG 첫 호출 지연 방지)
        - 벡터 DB 연결
        - BM25 인메모리 인덱스 빌드 (데이터 없으면 no-op)

        시드 데이터/벡터 인덱싱/가상 질문 생성은 별도 admin API로 분리.
        """
        try:
            logger.info("[START] lightweight 초기화 시작...")

            initialize_dependencies()
            ensure_mongo_indexes(get_mongo_client())
            self.vector_db = initialize_vector_db()
            self.indexing_service = get_indexing_service()
            self._rebuild_bm25_safely()

            logger.info("[OK] lightweight 초기화 완료")
            return {"status": "success", "mode": "lightweight"}

        except Exception as e:
            logger.error(f"[ERROR] lightweight 초기화 실패: {e}")
            return {"status": "error", "mode": "lightweight", "message": str(e)}

    # ------------------------------------------------------------------
    # Heavy operations (admin / opt-in)
    # ------------------------------------------------------------------

    def seed_mongo_collections(self) -> Dict[str, Any]:
        """MongoDB에 카드/문제 시드 데이터를 적재한다. (admin)"""
        try:
            seed_mongo_data()
            content_ok = load_content_hierarchy()
            load_stage1_cards()
            load_stage2_problems()
            stage3_ok = load_stage3_problems()
            classes_ok = load_classrooms()
            logger.info("[OK] MongoDB 시드 적재 완료")
            return {
                "status": "success",
                "content_hierarchy": "loaded" if content_ok else "failed",
                "stage1": "loaded",
                "stage2": "loaded",
                "stage3": "loaded" if stage3_ok else "failed",
                "classes": "loaded" if classes_ok else "failed",
            }
        except Exception as e:
            logger.error(f"[ERROR] MongoDB 시드 적재 실패: {e}")
            return {"status": "error", "message": str(e)}

    async def rebuild_vector_index(self) -> Dict[str, Any]:
        """ChromaDB에 모든 컬렉션을 재인덱싱한다. (admin)"""
        try:
            indexing_service = self._ensure_indexing_service()
            result = await indexing_service.index_all_data()
            self._rebuild_bm25_safely()  # 새 벡터 데이터 반영
            return {"status": "success", "indexing_result": result}
        except Exception as e:
            logger.error(f"[ERROR] 벡터 인덱싱 실패: {e}")
            return {"status": "error", "message": str(e)}

    def rebuild_bm25_index(self) -> Dict[str, Any]:
        """ChromaDB 전체 문서를 기반으로 BM25 인덱스를 재구축한다. (admin)"""
        try:
            self._rebuild_bm25_safely()
            return {"status": "success"}
        except Exception as e:
            logger.error(f"[ERROR] BM25 재구축 실패: {e}")
            return {"status": "error", "message": str(e)}

    async def build_hypothetical_questions_index(self) -> Dict[str, Any]:
        """OpenAI로 가상 질문을 생성해 ChromaDB에 저장한다. (admin, 비용 발생)"""
        try:
            chroma_client = chromadb.PersistentClient(path="chroma_db")
            embedding_model = get_embedding_model()
            await build_hypothetical_questions(
                chroma_client=chroma_client,
                embedding_model=embedding_model,
                collection_names=["card_check", "korean_word_problems"],
            )
            return {"status": "success"}
        except Exception as e:
            logger.warning(f"[WARN] 가상 질문 생성 실패: {e}")
            return {"status": "error", "message": str(e)}

    async def full_initialization(self) -> Dict[str, Any]:
        """최초 배포 시 1회 실행. lightweight + seed + 벡터 인덱싱 + 가상 질문 생성."""
        logger.info("[START] full 초기화 시작...")

        lightweight = await self.startup_lightweight()
        seed = self.seed_mongo_collections()
        index = await self.rebuild_vector_index()
        hyp = await self.build_hypothetical_questions_index()

        return {
            "status": "success",
            "mode": "full",
            "lightweight": lightweight,
            "seed": seed,
            "vector_index": index,
            "hypothetical_questions": hyp,
        }

    # ------------------------------------------------------------------
    # Status / helpers
    # ------------------------------------------------------------------

    def get_system_status(self) -> Dict[str, Any]:
        """ChromaDB 컬렉션별 문서 수와 상태 반환."""
        try:
            vector_db = self.vector_db or initialize_vector_db()
            collections_info = {}
            for name in ["korean_word_problems", "card_check", "pdf_documents"]:
                collection = vector_db.get_collection(name)
                if collection:
                    collections_info[name] = {
                        "document_count": collection.count(),
                        "status": "available",
                    }
                else:
                    collections_info[name] = {
                        "document_count": 0,
                        "status": "not_available",
                    }
            return {"status": "success", "system": "active", "collections": collections_info}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _ensure_indexing_service(self):
        if self.indexing_service is None:
            self.indexing_service = get_indexing_service()
        if self.vector_db is None:
            self.vector_db = initialize_vector_db()
        return self.indexing_service

    def _rebuild_bm25_safely(self) -> None:
        try:
            vector_db = self.vector_db or initialize_vector_db()
            get_bm25_retriever().build_index(vector_db)
        except Exception as e:
            logger.warning(f"[WARN] BM25 인덱스 빌드 실패 (서비스는 계속): {e}")


# 전역 초기화 서비스 인스턴스
_initialization_service: Optional[InitializationService] = None


def get_initialization_service() -> InitializationService:
    """초기화 서비스 인스턴스 반환"""
    global _initialization_service
    if _initialization_service is None:
        _initialization_service = InitializationService()
    return _initialization_service
