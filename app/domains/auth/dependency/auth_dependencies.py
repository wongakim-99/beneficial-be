import os
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.common.security import TokenError, decode_access_token
from app.domains.auth.model.auth_models import User
from app.domains.auth.repository.auth_repository import AuthRepository
from app.domains.auth.service.auth_service import AuthService
from app.infrastructure.db.mongo.mongo_client import get_mongo_client

bearer_scheme = HTTPBearer(auto_error=False)

_ADMIN_USER_ID = "admin_hardcoded"


def get_auth_service() -> AuthService:
    return AuthService(AuthRepository(get_mongo_client()))


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 토큰이 필요합니다.",
        )

    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 인증 토큰입니다.",
        )

    # 하드코딩 관리자는 DB 조회 없이 토큰 클레임에서 바로 반환
    if payload.get("sub") == _ADMIN_USER_ID:
        now = datetime.now(timezone.utc)
        return User(
            user_id=_ADMIN_USER_ID,
            email=payload.get("email", os.getenv("ADMIN_EMAIL", "")),
            password_hash="",
            display_name="관리자",
            role="developer",
            created_at=now,
            updated_at=now,
        )

    user = auth_service.get_user(payload["sub"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다.",
        )
    return user


def get_current_student(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="학생 권한이 필요합니다.",
        )
    return current_user


def get_current_teacher(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role not in {"teacher", "developer"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="교사 권한이 필요합니다.",
        )
    return current_user


def get_current_developer(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != "developer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="개발자 권한이 필요합니다.",
        )
    return current_user
