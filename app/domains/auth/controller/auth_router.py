from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status

from app.domains.auth.dependency.auth_dependencies import get_auth_service, get_current_user
from app.domains.auth.model.auth_models import User
from app.domains.auth.schema.auth_schemas import (
    AuthTokenResponse,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    SignupRequest,
    UserResponse,
)
from app.domains.auth.service.auth_service import (
    AuthError,
    AuthService,
    DuplicateUserError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    REFRESH_TOKEN_EXPIRE_DAYS,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(request: SignupRequest, auth_service: AuthService = Depends(get_auth_service)):
    try:
        user = auth_service.signup(
            email=request.email,
            password=request.password,
            display_name=request.display_name,
            role=request.role,
            school_name=request.school_name,
        )
        return _to_user_response(user)
    except DuplicateUserError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/login", response_model=AuthTokenResponse)
def login(
    request_body: LoginRequest,
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
):
    try:
        token_pair = auth_service.login(
            email=request_body.email,
            password=request_body.password,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    _set_refresh_cookie(response, token_pair["refresh_token"])
    return _to_token_response(token_pair)


@router.post("/refresh", response_model=AuthTokenResponse)
def refresh(
    request: Request,
    response: Response,
    request_body: RefreshRequest | None = None,
    refresh_token_cookie: str | None = Cookie(default=None, alias="refresh_token"),
    auth_service: AuthService = Depends(get_auth_service),
):
    refresh_token = (request_body.refresh_token if request_body else None) or refresh_token_cookie
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="refresh token이 필요합니다.",
        )

    try:
        token_pair = auth_service.refresh(
            refresh_token=refresh_token,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
    except InvalidRefreshTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    _set_refresh_cookie(response, token_pair["refresh_token"])
    return _to_token_response(token_pair)


@router.post("/logout", response_model=MessageResponse)
def logout(
    response: Response,
    request_body: RefreshRequest | None = None,
    refresh_token_cookie: str | None = Cookie(default=None, alias="refresh_token"),
    auth_service: AuthService = Depends(get_auth_service),
):
    refresh_token = (request_body.refresh_token if request_body else None) or refresh_token_cookie
    if refresh_token:
        auth_service.logout(refresh_token)
    response.delete_cookie("refresh_token", path="/auth")
    return MessageResponse(message="로그아웃되었습니다.")


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return _to_user_response(current_user)


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
    )


def _to_token_response(token_pair: dict) -> AuthTokenResponse:
    return AuthTokenResponse(
        access_token=token_pair["access_token"],
        refresh_token=token_pair["refresh_token"],
        expires_in=token_pair["expires_in"],
        user=_to_user_response(token_pair["user"]),
    )


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/auth",
    )
