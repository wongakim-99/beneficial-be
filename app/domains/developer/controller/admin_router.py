"""
관리자용 API.

평소 startup은 lightweight 이므로, 시드/인덱싱/가상 질문 생성은 여기서 호출한다.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.common.init.initialization import get_initialization_service
from app.domains.developer.service.indexing_service import get_indexing_service
from app.domains.developer.dependency.monitoring_dependencies import get_monitoring_service
from app.domains.developer.service.monitoring_service import MonitoringService
from app.domains.developer.schema.monitoring_schemas import (
    TraceLog,
    TracesResponse,
    UsageStatsResponse,
)
from app.domains.auth.dependency.auth_dependencies import get_current_developer

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_developer)],
)


# ----------------------------------------------------------------------
# 시스템 상태
# ----------------------------------------------------------------------

@router.get("/system-status")
async def get_system_status():
    """ChromaDB 컬렉션 상태와 문서 수를 조회합니다."""
    try:
        return get_initialization_service().get_system_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상태 확인 실패: {str(e)}")


# ----------------------------------------------------------------------
# 초기화 / 시드 / 인덱싱
# ----------------------------------------------------------------------

@router.post("/initialize-all")
async def initialize_all():
    """최초 배포 시 1회 호출. 시드 + 벡터 인덱싱 + BM25 + 가상 질문 생성까지 전부 수행합니다."""
    try:
        return await get_initialization_service().full_initialization()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"전체 초기화 실패: {str(e)}")


@router.post("/seed-data")
async def seed_data():
    """MongoDB에 카드/문제 시드 데이터를 적재합니다. (Stage 1/2/3 포함)"""
    try:
        result = get_initialization_service().seed_mongo_collections()
        if result.get("status") != "success":
            raise HTTPException(status_code=500, detail=result.get("message", "시드 적재 실패"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"시드 적재 실패: {str(e)}")


@router.post("/rebuild-vector-index")
async def rebuild_vector_index():
    """ChromaDB 모든 컬렉션(card_check, korean_word_problems, pdf_documents)을 재인덱싱하고 BM25도 다시 빌드합니다."""
    try:
        result = await get_initialization_service().rebuild_vector_index()
        if result.get("status") != "success":
            raise HTTPException(status_code=500, detail=result.get("message", "벡터 인덱싱 실패"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"벡터 인덱싱 실패: {str(e)}")


@router.post("/rebuild-bm25")
async def rebuild_bm25():
    """ChromaDB 전체 문서를 기반으로 BM25 인메모리 인덱스를 재구축합니다."""
    try:
        result = get_initialization_service().rebuild_bm25_index()
        if result.get("status") != "success":
            raise HTTPException(status_code=500, detail=result.get("message", "BM25 재구축 실패"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"BM25 재구축 실패: {str(e)}")


@router.post("/build-hypothetical-questions")
async def build_hypothetical_questions_endpoint():
    """OpenAI를 호출해 가상 질문을 생성하고 ChromaDB에 저장합니다. (API 비용 발생)"""
    try:
        result = await get_initialization_service().build_hypothetical_questions_index()
        if result.get("status") != "success":
            raise HTTPException(status_code=500, detail=result.get("message", "가상 질문 생성 실패"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"가상 질문 생성 실패: {str(e)}")


# ----------------------------------------------------------------------
# 부분 인덱싱
# ----------------------------------------------------------------------

@router.post("/indexing/pdf")
async def reindex_pdf():
    """PDF 문서만 재인덱싱합니다."""
    try:
        return await get_indexing_service().index_pdf_documents()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF 재인덱싱 실패: {str(e)}")


# ----------------------------------------------------------------------
# 사용량 모니터링
# ----------------------------------------------------------------------

@router.get("/usage/stats", response_model=UsageStatsResponse)
async def get_usage_stats(
    days: int = Query(7, ge=1, le=90, description="집계 기간(일)"),
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
):
    """최근 N일 에이전트/채팅 호출 사용량 통계를 조회합니다."""
    return UsageStatsResponse(**monitoring_service.get_usage_stats(days))


@router.get("/usage/traces", response_model=TracesResponse)
async def get_usage_traces(
    endpoint: Optional[str] = Query(None, description="엔드포인트 필터 (agent_chat, chat_rag)"),
    user_id: Optional[str] = Query(None, description="사용자 필터"),
    limit: int = Query(50, ge=1, le=200, description="최대 조회 수"),
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
):
    """최근 호출 트레이스 로그를 시간 역순으로 조회합니다."""
    traces = monitoring_service.get_recent_traces(
        endpoint=endpoint,
        user_id=user_id,
        limit=limit,
    )
    return TracesResponse(
        traces=[TraceLog(**trace) for trace in traces],
        total_count=len(traces),
    )


@router.get("/indexing/status")
async def get_indexing_status():
    """인덱싱 상태 (system-status와 동일, 호환용)."""
    try:
        indexing_service = get_indexing_service()
        vector_db = indexing_service.vector_db
        status = {}
        for collection_name in ["korean_word_problems", "card_check", "pdf_documents"]:
            collection = vector_db.get_collection(collection_name)
            if collection:
                status[collection_name] = {
                    "document_count": collection.count(),
                    "status": "available",
                }
            else:
                status[collection_name] = {
                    "document_count": 0,
                    "status": "not_available",
                }
        return {"status": "success", "indexing_status": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상태 확인 실패: {str(e)}")
