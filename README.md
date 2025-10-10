# Naraninyeo 프로젝트 둘러보기

나란잉여 에이전트 코드는 크게 **도메인 로직을 담은 `naraninyeo/assistant` 패키지**와 **환경설정을 담당하는 `naraninyeo/settings.py`**, 그리고 **엔트리포인트인 `main.py`**로 나뉜다. 아래 안내를 참고하면 각 파일이 어떤 역할을 맡는지 빠르게 파악할 수 있다.

## 주요 디렉터리/파일 역할
- `main.py`  
  실행 시 필요한 의존성을 구성하고 전체 봇을 구동한다.
- `naraninyeo/app/pipeline.py`  
  파이프라인 상태·스텝·엔진을 정의하여 대화 흐름을 연결한다.
- `naraninyeo/app/context.py` / `naraninyeo/app/reply.py`  
  답변 컨텍스트 구성과 LLM 스트리밍 응답 생성을 담당한다.
- `naraninyeo/assistant/retrieval`  
  검색 계획 수립, 실행기, 네이버/Wiki/대화 기록 전략을 모듈별로 제공한다.
- `naraninyeo/assistant/message_repository.py`  
  MongoDB와 Qdrant를 이용해 메시지를 저장·검색하는 구현체를 제공한다.
- `naraninyeo/assistant/llm_toolkit.py`  
  설정값을 읽어 LLM 제공자를 선택하고, 프롬프트 템플릿과 연결된 `LLMTool`을 만들어낸다.
- `naraninyeo/settings.py`  
  `.env` 값과 기본값을 합쳐 실행 환경에 필요한 설정을 관리한다.

## 개발자가 자주 하는 일
1. **메시지 저장 방식 수정**  
   `message_repository.py`에서 MongoDB 쿼리나 Qdrant 연동을 손본다.
2. **LLM 스펙 변경**  
   `settings.py`에서 모델 이름·타임아웃을 바꾼 뒤 `llm_toolkit.py`가 해당 값을 읽어 사용한다.
3. **새로운 플러그인/전략 추가**  
   `settings.py`의 `PLUGINS`, `ENABLED_RETRIEVAL_STRATEGIES`에 모듈 경로나 이름을 추가하고 관련 모듈을 `naraninyeo/assistant`에 배치한다.

## 로컬 테스트 빠른 흐름
- 테스트: `flox activate -- uv run pytest`
- 타입 체크: `flox activate -- uv run pyright`
- 린트: `flox activate -- uvx ruff check`
- 자동 수정: `flox activate -- uvx ruff check --fix`

> 첫 실행 시 필요한 컨테이너 이미지(MongoDB, Qdrant, Llama.cpp)가 자동으로 내려받아지며, 추가 API 키 없이 통합 테스트가 동작하도록 구성되어 있다. 특정 테스트만 돌리고 싶다면 `flox activate -- uv run pytest 경로 -q` 형식으로 실행하면 된다.

## 전체 흐름을 한눈에 보기
1. 사용자가 보낸 메시지가 `message_repository.py`를 통해 MongoDB/Qdrant에 저장된다.
2. `context.ReplyContextBuilder`가 대화 히스토리·메모리를 모아 `pipeline.ChatPipeline`으로 전달한다.
3. `assistant/retrieval` 패키지의 플래너·실행기가 필요한 검색 전략을 실행하고, `reply.ReplyGenerator`가 최종 응답을 스트리밍으로 생성한다.

이 README로 기본 구조를 파악한 뒤, 세부 구현은 각 모듈 내 주석을 참고하며 살펴보면 된다.
