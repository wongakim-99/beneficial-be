import re
import secrets
from datetime import timedelta
from typing import Any, Dict, Optional

from app.common.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    utc_now,
    verify_password,
)
from app.domains.auth.model.auth_models import User
from app.domains.auth.repository.auth_repository import AuthRepository
from app.domains.auth.whitelist import is_developer_email, is_teacher_email


ACCESS_TOKEN_EXPIRE_SECONDS = 30 * 60
REFRESH_TOKEN_EXPIRE_DAYS = 14
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(ValueError):
    pass


class DuplicateUserError(AuthError):
    pass


class InvalidCredentialsError(AuthError):
    pass


class InvalidRefreshTokenError(AuthError):
    pass


class AuthService:
    def __init__(self, repository: AuthRepository):
        self.repository = repository

    def signup(self, email: str, password: str, display_name: str, role: str = "student", school_name: Optional[str] = None) -> User:
        normalized_email = self._normalize_email(email)
        self._validate_password(password)

        if self.repository.find_user_by_email(normalized_email):
            raise DuplicateUserError("이미 가입된 이메일입니다.")

        resolved_role = role if role in {"student", "teacher"} else "student"

        now = utc_now()
        user = User(
            user_id=f"user_{secrets.token_urlsafe(16)}",
            email=normalized_email,
            password_hash=hash_password(password),
            display_name=display_name.strip(),
            role=resolved_role,
            school_name=school_name.strip() if school_name else None,
            created_at=now,
            updated_at=now,
        )
        self.repository.create_user(
            user.model_dump() if hasattr(user, "model_dump") else user.dict()
        )
        return user

    def login(
        self,
        email: str,
        password: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_email = self._normalize_email(email)
        user_doc = self.repository.find_user_by_email(normalized_email)
        if not user_doc or not verify_password(password, user_doc.get("password_hash", "")):
            raise InvalidCredentialsError("이메일 또는 비밀번호가 올바르지 않습니다.")

        return self._issue_token_pair(user_doc, user_agent, ip_address)

    def refresh(
        self,
        refresh_token: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        refresh_hash = hash_refresh_token(refresh_token)
        session = self.repository.find_refresh_session_by_hash(refresh_hash)
        now = utc_now()

        if (
            not session
            or session.get("revoked_at") is not None
            or session.get("expires_at") < now
        ):
            raise InvalidRefreshTokenError("refresh token이 유효하지 않습니다.")

        user_doc = self.repository.find_user_by_id(session["user_id"])
        if not user_doc:
            raise InvalidRefreshTokenError("사용자를 찾을 수 없습니다.")

        self.repository.revoke_refresh_session(session["session_id"], now)
        return self._issue_token_pair(user_doc, user_agent, ip_address)

    def logout(self, refresh_token: str) -> None:
        session = self.repository.find_refresh_session_by_hash(
            hash_refresh_token(refresh_token)
        )
        if session and session.get("revoked_at") is None:
            self.repository.revoke_refresh_session(session["session_id"], utc_now())

    def get_user(self, user_id: str) -> Optional[User]:
        user_doc = self.repository.find_user_by_id(user_id)
        if not user_doc:
            return None
        return User(**self._apply_role_policy(user_doc))

    @staticmethod
    def _apply_role_policy(user_doc: Dict[str, Any]) -> Dict[str, Any]:
        role = _normalize_role(user_doc.get("role", "student"))
        email = user_doc.get("email")

        if is_developer_email(email):
            role = "developer"
        elif is_teacher_email(email) and role != "developer":
            role = "teacher"

        return {**user_doc, "role": role}

    def _issue_token_pair(
        self,
        user_doc: Dict[str, Any],
        user_agent: Optional[str],
        ip_address: Optional[str],
    ) -> Dict[str, Any]:
        user_doc = self._apply_role_policy(user_doc)
        access_token = create_access_token(
            subject=user_doc["user_id"],
            expires_delta=timedelta(seconds=ACCESS_TOKEN_EXPIRE_SECONDS),
            extra_claims={
                "email": user_doc["email"],
                "role": user_doc.get("role", "student"),
            },
        )
        refresh_token = create_refresh_token()
        now = utc_now()
        self.repository.create_refresh_session(
            {
                "session_id": f"rt_{secrets.token_urlsafe(16)}",
                "user_id": user_doc["user_id"],
                "refresh_token_hash": hash_refresh_token(refresh_token),
                "user_agent": user_agent,
                "ip_address": ip_address,
                "expires_at": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
                "revoked_at": None,
                "created_at": now,
            }
        )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": ACCESS_TOKEN_EXPIRE_SECONDS,
            "user": User(**user_doc),
        }

    def _normalize_email(self, email: str) -> str:
        normalized = email.strip().lower()
        if not EMAIL_PATTERN.match(normalized):
            raise AuthError("이메일 형식이 올바르지 않습니다.")
        return normalized

    def _validate_password(self, password: str) -> None:
        if len(password) < 8:
            raise AuthError("비밀번호는 8자 이상이어야 합니다.")


def _normalize_role(role: str | None) -> str:
    if role == "admin":
        return "developer"
    if role in {"student", "teacher", "developer"}:
        return role
    return "student"
