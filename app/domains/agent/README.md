# Agent Domain

학생 상태(약점 프로파일 + 최근 대화)를 바탕으로 어떤 도움을 줄지 결정하는 AI Agent("이로")를 담당한다.
RAG는 이 도메인의 중심이 아니라, 필요할 때 호출하는 도구다.

## 패키지 구조

```
agent/
  controller/agent_router.py        # /agent/*, /chat/*(legacy) API
  service/agent_service.py          # ChatSessionService, AgentService, ChatService
  service/graph.py                  # LangGraph 그래프 조립 (build_agent_graph)
  repository/chat_session_repository.py  # ChatSession 저장/조회
  schema/agent_schemas.py           # 요청/응답 DTO
  model/agent_models.py             # ChatSession, ChatMessage, AgentDecision
```

## API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/agent/chat` | LangGraph 기반 에이전트 대화 (이로) |
| GET | `/agent/session/{session_id}` | 세션 메시지 조회 |
| DELETE | `/agent/session/{session_id}` | 세션 삭제 |
| GET | `/agent/profile/me` | 약점 프로파일 조회 (학생은 403 차단, 교사·개발자만) |
| POST | `/chat/` | (legacy) RAG 직답 |
| GET | `/chat/status` | (legacy) 챗 상태 |

학생용 약점 노출은 정책상 막혀 있고(`role == "student"`이면 403), 약점 데이터는 교사용 경로에서 제공한다.

## LangGraph 흐름

`build_agent_graph`가 아래 노드를 조립한다.

```
load_context → decide_action →(조건부) rag_search → generate_response → save_turn
```

- **load_context**: 세션 로드/생성, 사용자 메시지 저장, 약점 프로파일·최근 대화 로드
- **decide_action**: 메시지 의도 판단 → `AgentDecision` 생성 (RAG 사용 여부 포함)
- **rag_search**: (필요 시) `RagService` 호출해 관련 문서 검색
- **generate_response**: 시스템 프롬프트 + (선택적) RAG context로 LLM 응답 생성
- **save_turn**: assistant 메시지를 세션에 저장
