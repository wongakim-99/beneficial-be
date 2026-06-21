import asyncio
from typing import List, Dict, Any
import logging
import os

logger = logging.getLogger(__name__)


class IndexingService:
    def __init__(self, vector_db, embedding_model):
        self.vector_db = vector_db
        self.embedding_model = embedding_model
        # 환경 변수에서 배치 크기 설정
        self.batch_size = int(os.getenv("INDEXING_BATCH_SIZE", "100"))

    async def index_documents_batch(self, documents: List[Dict[str, Any]], collection_name: str) -> int:
        """문서를 배치로 나누어 인덱싱"""
        if not documents:
            return 0

        total_docs = len(documents)
        processed_docs = 0

        logger.info(f"[DATA] {collection_name} 컬렉션에 {total_docs}개 문서 배치 인덱싱 시작...")

        # 컬렉션 가져오기
        collection = self.vector_db.get_collection(collection_name)
        if not collection:
            logger.error(f"[ERROR] 컬렉션 '{collection_name}'을 찾을 수 없습니다.")
            return 0

        for i in range(0, total_docs, self.batch_size):
            batch_docs = documents[i:i + self.batch_size]
            batch_size_actual = len(batch_docs)

            try:
                # 배치별 텍스트 추출
                batch_texts = [doc["text"] for doc in batch_docs]
                batch_ids = [doc["id"] for doc in batch_docs]
                batch_metadatas = [doc["metadata"] for doc in batch_docs]

                # 배치별 임베딩 생성 (최적화된 임베딩 모델 사용)
                embeddings = await self.embedding_model.get_embeddings(batch_texts)

                # 벡터 DB에 배치 삽입
                collection.add(
                    documents=batch_texts,
                    embeddings=embeddings,
                    metadatas=batch_metadatas,
                    ids=batch_ids
                )

                processed_docs += batch_size_actual
                progress = (processed_docs / total_docs) * 100
                logger.info(f"[WAIT] {collection_name} 진행률: {processed_docs}/{total_docs} ({progress:.1f}%)")

                # 메모리 정리를 위한 잠시 대기
                await asyncio.sleep(0.01)

            except Exception as e:
                logger.error(f"[ERROR] 배치 {i // self.batch_size + 1} 인덱싱 실패: {e}")
                # 실패한 배치는 건너뛰고 계속 진행
                continue

        logger.info(f"[OK] {collection_name} 인덱싱 완료: {processed_docs}개 문서")
        return processed_docs

    async def index_korean_word_problems(self) -> Dict[str, Any]:
        """한국어 단어 문제 데이터를 인덱싱"""
        try:
            from app.infrastructure.loaders.korean_word_problems_loader import get_korean_word_problems

            # 데이터 로드
            data = get_korean_word_problems()
            if not data:
                return {"status": "error", "message": "데이터를 찾을 수 없습니다."}

            # 문서 변환
            documents = self.embedding_model.prepare_documents_for_indexing(data, "korean_word_problems")

            # 배치 인덱싱
            indexed_count = await self.index_documents_batch(documents, "korean_word_problems")

            return {
                "status": "success",
                "message": "한국어 단어 문제 인덱싱 완료",
                "indexed_count": indexed_count
            }

        except Exception as e:
            logger.error(f"한국어 단어 문제 인덱싱 실패: {e}")
            return {"status": "error", "message": str(e)}

    async def index_card_check_data(self) -> Dict[str, Any]:
        """카드 체크 데이터를 인덱싱"""
        try:
            from app.infrastructure.loaders.card_check_loader import get_card_check_data

            # 데이터 로드
            data = get_card_check_data()
            if not data:
                return {"status": "error", "message": "데이터를 찾을 수 없습니다."}

            # 문서 변환
            documents = self.embedding_model.prepare_documents_for_indexing(data, "card_check")

            # 배치 인덱싱
            indexed_count = await self.index_documents_batch(documents, "card_check")

            return {
                "status": "success",
                "message": "카드 체크 데이터 인덱싱 완료",
                "indexed_count": indexed_count
            }

        except Exception as e:
            logger.error(f"카드 체크 데이터 인덱싱 실패: {e}")
            return {"status": "error", "message": str(e)}

    async def index_pdf_documents(self) -> Dict[str, Any]:
        """PDF 문서들을 인덱싱"""
        try:
            from app.infrastructure.loaders.pdf_loader import load_pdf_documents
            
            # PDF 데이터 로드
            pdf_data = load_pdf_documents()
            if not pdf_data:
                return {"status": "no_data", "message": "PDF 파일이 없습니다."}
            
            # 문서 변환 (이미 전처리된 상태)
            documents = self.embedding_model.prepare_documents_for_indexing(pdf_data, "pdf_documents")
            
            # 배치 인덱싱
            indexed_count = await self.index_documents_batch(documents, "pdf_documents")
            
            return {
                "status": "success",
                "message": "PDF 문서 인덱싱 완료",
                "indexed_count": indexed_count
            }
            
        except Exception as e:
            logger.error(f"PDF 문서 인덱싱 실패: {e}")
            return {"status": "error", "message": f"인덱싱 실패: {str(e)}"}

    async def index_all_data(self) -> Dict[str, Any]:
        """모든 데이터를 병렬로 인덱싱"""
        logger.info("[START] 전체 데이터 인덱싱 시작...")

        # 병렬 실행을 위한 태스크 생성
        tasks = [
            self.index_korean_word_problems(),
            self.index_card_check_data(),
            self.index_pdf_documents()  # PDF 인덱싱 추가
        ]

        # 병렬 실행
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful_collections = 0
        total_collections = len(tasks)
        detailed_results = {}

        for i, result in enumerate(results):
            collection_name = ["korean_word_problems", "card_check", "pdf_documents"][i]

            if isinstance(result, Exception):
                detailed_results[collection_name] = {
                    "status": "error",
                    "message": str(result)
                }
            elif result.get("status") == "success":
                successful_collections += 1
                detailed_results[collection_name] = result
            else:
                detailed_results[collection_name] = result

        logger.info(f"[OK] 전체 인덱싱 완료: {successful_collections}/{total_collections}개 성공")

        return {
            "total_collections": total_collections,
            "successful_collections": successful_collections,
            "results": detailed_results
        }

    def clear_collection(self, collection_name: str) -> Dict[str, Any]:
        """특정 컬렉션의 모든 데이터를 삭제"""
        try:
            collection = self.vector_db.get_collection(collection_name)
            if collection:
                # 컬렉션 삭제
                self.vector_db.client.delete_collection(collection_name)
                logger.info(f"[OK] {collection_name} 컬렉션 삭제 완료")
                return {
                    "status": "success",
                    "message": f"{collection_name} 컬렉션이 삭제되었습니다."
                }
            else:
                return {
                    "status": "error",
                    "message": f"{collection_name} 컬렉션을 찾을 수 없습니다."
                }
        except Exception as e:
            logger.error(f"컬렉션 {collection_name} 삭제 실패: {e}")
            return {
                "status": "error",
                "message": f"컬렉션 삭제 중 오류 발생: {str(e)}"
            }

    async def index_pdf_documents(self) -> Dict[str, Any]:
        """PDF 문서들을 인덱싱"""
        try:
            from app.infrastructure.loaders.pdf_loader import load_pdf_documents

            # PDF 데이터 로드
            pdf_data = load_pdf_documents()
            if not pdf_data:
                return {"status": "no_data", "message": "PDF 파일이 없습니다."}

            # 문서 변환 (이미 전처리된 상태)
            documents = self.embedding_model.prepare_documents_for_indexing(pdf_data, "pdf_documents")

            # 배치 인덱싱
            indexed_count = await self.index_documents_batch(documents, "pdf_documents")

            return {
                "status": "success",
                "message": "PDF 문서 인덱싱 완료",
                "indexed_count": indexed_count
            }

        except Exception as e:
            logger.error(f"PDF 문서 인덱싱 실패: {e}")
            return {"status": "error", "message": f"인덱싱 실패: {str(e)}"}


# 전역 인덱싱 서비스 인스턴스
indexing_service = None


def get_indexing_service():
    """전역 인덱싱 서비스 인스턴스를 반환합니다."""
    global indexing_service
    if indexing_service is None:
        from app.infrastructure.db.vector.vector_db import get_vector_db
        from app.infrastructure.embedding.embedding_model import get_embedding_model

        vector_db = get_vector_db()
        embedding_model = get_embedding_model()
        indexing_service = IndexingService(vector_db, embedding_model)

    return indexing_service