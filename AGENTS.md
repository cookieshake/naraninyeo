Agents Developer Guide

본 문서는 에이전트(LLM 연동, 파이프라인 스텝 등) 개발 시 로컬에서 테스트/검증하는 최소 흐름을 요약합니다.

Prerequisites
- Docker 데몬 실행 중 (테스트 컨테이너 자동 사용)
- flox, uv 설치 완료

Local Testing
- 테스트 실행:
  - `flox activate -- uv run pytest`
- 타입 체크:
  - `flox activate -- uv run pyright`
- 린트 검사:
  - `flox activate -- uvx ruff check`
- 자동 포맷/간단 수정:
  - `flox activate -- uvx ruff check --fix`

참고 사항
- 첫 실행 시 테스트 컨테이너 이미지(MongoDB, Qdrant, Llama.cpp)가 자동으로 풀(Pull)됩니다.
- 별도의 API 키 설정 없이 통합 테스트가 동작하도록 구성되어 있습니다.
- 특정 테스트만 실행하려면 파일 경로 또는 패턴을 지정하세요. 예) `flox activate -- uv run pytest naraninyeo/tests/integration/test_new_message_handler.py -q`

Code Style
- `naraninyeo/assistant` 패키지의 모듈 간 import 시에는 반드시 절대 경로(`from naraninyeo.assistant...`)를 사용하세요.
- `naraninyeo/assistant/__init__.py`는 얇은 상태를 유지하고, 필요한 심볼은 각 모듈에서 직접 import 해서 사용하세요.
- `naraninyeo/assistant` 모듈들에 `__all__` 목록을 새로 추가하지 말고 필요한 이름을 직접 import 해 사용하세요.
- `core`/`services` 같은 모호한 패키지 이름을 다시 추가하지 말고, 도메인을 설명하는 명확한 모듈명을 사용하세요.
