# Naraninyeo (나란잉여)

나란잉여는 LLM(Large Language Model)을 활용하여 대화형 AI 기능을 제공하는 비동기 파이썬 애플리케이션입니다. Kafka 메시지 큐 또는 로컬 CLI를 통해 메시지를 처리하고, 상황에 맞는 풍부한 컨텍스트를 생성하여 지능적인 응답을 제공합니다.

## 주요 특징

- **모듈식 아키텍처**: `서비스(Service)`와 `어댑터(Adapter)` 패턴을 기반으로 한 깔끔한 아키텍처를 적용하여 각 컴포넌트의 독립성과 테스트 용이성을 높였습니다.
- **비동기 처리**: `asyncio`와 `aiokafka` 등을 사용하여 모든 I/O 작업을 비동기적으로 처리하여 높은 성능을 보장합니다.
- **풍부한 컨텍스트 생성**: LLM이 응답을 생성하기 전, 다음과 같은 다각적인 컨텍스트를 준비합니다.
    - **최근 대화 기록**: 현재 대화의 흐름을 파악합니다.
    - **유사 대화 검색**: Vector-based search를 통해 과거의 관련성 높은 대화를 참고합니다.
    - **동적 외부 검색**: LLM이 직접 검색 계획(`Search Plan`)을 수립하고, 웹, 뉴스, 블로그 등 필요한 정보를 동적으로 검색하여 응답에 활용합니다.
- **다중 진입점(Entrypoint)**:
    - **Kafka 컨슈머**: 실시간 메시지 스트림 처리를 위한 Kafka 연동을 지원합니다.
    - **CLI 클라이언트**: 개발 및 테스트를 위한 로컬 커맨드라인 인터페이스를 제공합니다.
- **의존성 주입**: `Dishka` 라이브러리를 사용하여 의존성을 관리하고 컴포넌트 간의 결합도를 낮춥니다.
- **관찰 가능성(Observability)**: OpenTelemetry를 통해 분산 추적(Tracing) 및 메트릭 수집을 지원합니다.

## 프로젝트 구조

```
naraninyeo/
├── adapters/         # 외부 시스템과의 연동을 담당하는 어댑터
│   ├── agents/       # LLM 에이전트 관련 로직 (e.g., Search Planner)
│   ├── clients.py    # 외부 API 클라이언트 (LLM, Embedding, etc.)
│   ├── database.py   # 데이터베이스 연결 관리
│   ├── repositories.py # 데이터 영속성 계층 (CRUD)
│   └── search_client.py # 외부 검색 엔진 클라이언트
├── core/             # 핵심 설정(Settings) 및 공통 로직
├── entrypoints/      # 애플리케이션 진입점 (Kafka, CLI)
│   ├── kafka_consumer.py
│   └── cli_client.py
├── models/           # 데이터 모델 (Pydantic)
├── services/         # 핵심 비즈니스 로직
│   └── conversation_service.py # 대화 처리 오케스트레이션
├── di.py             # 의존성 주입(Dishka) 설정
└── main.py           # 메인 실행 파일
```

## 실행 방법

### 1. 사전 준비

프로젝트 실행에 필요한 환경 변수를 설정해야 합니다. `.env` 파일을 생성하고 아래 내용을 채워주세요. (실제 값으로 대체해야 합니다)

```env
# Kafka 설정
KAFKA_BOOTSTRAP_SERVERS="localhost:9092"
KAFKA_TOPIC="chat-messages"
KAFKA_GROUP_ID="naraninyeo"

# LLM 및 Embedding 모델 설정 (e.g., Google Gemini)
GOOGLE_API_KEY="your_google_api_key"
EMBEDDING_MODEL_NAME="text-embedding-004"
LLM_MODEL_NAME="gemini-1.5-flash-preview-0514"

# 데이터베이스 설정 (MongoDB)
MONGO_URI="mongodb://localhost:27017/"
MONGO_DB_NAME="naraninyeo"

# 봇 정보
BOT_AUTHOR_NAME="나란잉여"
BOT_AUTHOR_ID="naraninyeo-bot"

# 외부 검색 API (Tavily)
TAVILY_API_KEY="your_tavily_api_key"

# (선택) OpenTelemetry 설정
# OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
```

### 2. 의존성 설치

이 프로젝트는 `uv`를 사용하여 의존성을 관리합니다.

```bash
# uv가 설치되어 있지 않다면: pip install uv
uv pip install -e .
```

### 3. 애플리케이션 실행

애플리케이션은 두 가지 모드로 실행할 수 있습니다.

#### CLI 모드 (로컬 테스트용)

커맨드라인에서 직접 챗봇과 대화할 수 있습니다.

```bash
python main.py cli
```
- 봇에게 응답을 요청하려면 메시지 앞에 `/`를 붙여주세요. (예: `/오늘 날씨 어때?`)
- 일반 메시지는 대화 기록으로 저장만 됩니다.

#### Kafka 컨슈머 모드

지정된 Kafka 토픽의 메시지를 구독하여 처리합니다.

```bash
python main.py kafka
```

## 핵심 컴포넌트

- **ConversationService**: 메시지 저장, 응답 여부 판단, 컨텍스트 수집, 응답 생성 등 대화의 전체 흐름을 관리하는 핵심 서비스입니다.
- **Adapters**: `LLMClient`, `EmbeddingClient`, `SearchClient`, `MessageRepository` 등 외부 시스템과의 상호작용을 추상화하는 역할을 합니다. 이를 통해 비즈니스 로직의 변경 없이 외부 시스템을 쉽게 교체할 수 있습니다.
- **LLM Agents**: 단순한 LLM 호출을 넘어, `SearchPlan`을 생성하는 등 더 능동적인 작업을 수행하는 에이전트 로직을 포함합니다.
