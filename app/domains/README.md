# Domains

새 기능은 도메인 중심으로 이곳에 추가한다. 도메인은 페르소나가 아니라 비즈니스 개념으로 나누고,
페르소나는 router prefix(`/student/*`, `/teacher/*`, `/admin/*`)와 응답 DTO 노출 정책으로 표현한다.

## 표준 패키지 구조

모든 도메인은 예외 없이 동일한 레이어 패키지 패턴을 따른다. (`__init__.py` 없는 namespace package 방식)

```
{domain}/
├── controller/   # HTTP 엔드포인트 (FastAPI APIRouter), 인증·입출력만
├── service/      # 비즈니스 로직
├── repository/   # MongoDB 등 저장소 접근
├── schema/       # API request/response Pydantic DTO
├── dependency/   # FastAPI DI 팩토리 함수
└── model/        # MongoDB 도큐먼트 모델
```

파일명은 generic 이름(`router.py`, `service.py`) 대신 역할이 드러나는 이름을 쓴다.
예: `controller/auth_router.py`, `service/learning_record_service.py`, `model/agent_models.py`.
역할별 라우터가 여럿이면 `teacher_router.py`/`student_router.py`처럼 나눈다.

## 도메인 목록

| 도메인 | 책임 |
|--------|------|
| `auth` | 회원가입/로그인/토큰, 역할(student·teacher·developer)·화이트리스트 |
| `content` | 단원·차시 카탈로그, Stage 1/2/3 학습 콘텐츠 |
| `progress` | 학습 기록(append-only) 저장, 약점 집계, 진척도 |
| `classroom` | 반(`classes`) 기반 교사-학생 매핑 |
| `instruction` | 교사 AI 맞춤 문제 생성·배정(`teacher_assignments`) |
| `agent` | 이로 챗봇(LangGraph), 약점 분석 |
| `developer` | 시드/인덱싱 등 운영 관리 API (`/admin/*`) |

## 위치 규칙

- RAG처럼 비즈니스 도메인보다 기술 기능에 가까운 코드는 `app/infrastructure`에 둔다.
- seed/fixture 성격의 공통 데이터 로더와 PDF 원본은 `app/common/data`에 둔다.
- 단일 헬퍼 모듈(예: `auth/whitelist.py`, `progress/util.py`)은 서브패키지 없이 도메인 루트 평면 모듈로 둔다.
