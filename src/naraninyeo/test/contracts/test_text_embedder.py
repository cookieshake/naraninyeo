"""
TextEmbedder 계약 테스트

스펙: core/interfaces.py TextEmbedder Protocol
구현체: infrastructure/adapter/llamacpp_gemma_embedder.py LlamaCppGemmaEmbedder
연동: testcontainer llama.cpp 서버
"""

import math

import pytest

from naraninyeo.core.interfaces import TextEmbedder


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x**2 for x in a))
    norm_b = math.sqrt(sum(x**2 for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@pytest.mark.asyncio
async def test_embed_docs_returns_list_of_vectors(text_embedder: TextEmbedder):
    """embed_docs()는 float 벡터 목록을 반환한다."""
    result = await text_embedder.embed_docs(["안녕하세요"])

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], list)
    assert len(result[0]) > 0
    assert all(isinstance(v, float) for v in result[0])


@pytest.mark.asyncio
async def test_embed_queries_returns_list_of_vectors(text_embedder: TextEmbedder):
    """embed_queries()는 float 벡터 목록을 반환한다."""
    result = await text_embedder.embed_queries(["검색어"])

    assert isinstance(result, list)
    assert len(result) == 1
    assert len(result[0]) > 0


@pytest.mark.asyncio
async def test_embed_docs_output_count_matches_input(text_embedder: TextEmbedder):
    """입력 개수 = 출력 개수."""
    docs = ["첫 번째 문서", "두 번째 문서", "세 번째 문서"]
    result = await text_embedder.embed_docs(docs)

    assert len(result) == len(docs)


@pytest.mark.asyncio
async def test_embed_queries_output_count_matches_input(text_embedder: TextEmbedder):
    """입력 개수 = 출력 개수."""
    queries = ["쿼리1", "쿼리2"]
    result = await text_embedder.embed_queries(queries)

    assert len(result) == len(queries)


@pytest.mark.asyncio
async def test_embed_docs_empty_list(text_embedder: TextEmbedder):
    """빈 리스트 입력 시 빈 리스트를 반환한다."""
    result = await text_embedder.embed_docs([])

    assert result == []


@pytest.mark.asyncio
async def test_embed_queries_empty_list(text_embedder: TextEmbedder):
    """빈 리스트 입력 시 빈 리스트를 반환한다."""
    result = await text_embedder.embed_queries([])

    assert result == []


@pytest.mark.asyncio
async def test_similar_docs_have_high_cosine_similarity(text_embedder: TextEmbedder):
    """의미적으로 유사한 문장은 높은 코사인 유사도를 가진다."""
    results = await text_embedder.embed_docs(
        [
            "삼성전자 주가가 올랐다",
            "삼성전자 주식이 상승했다",
            "오늘 날씨가 매우 맑다",
        ]
    )

    similar_score = cosine_similarity(results[0], results[1])
    unrelated_score = cosine_similarity(results[0], results[2])

    assert similar_score > unrelated_score, (
        f"유사 문장 유사도({similar_score:.3f})가 무관 문장 유사도({unrelated_score:.3f})보다 높아야 함"
    )


@pytest.mark.asyncio
async def test_all_vectors_have_same_dimension(text_embedder: TextEmbedder):
    """모든 임베딩 벡터는 동일한 차원을 가진다."""
    docs = ["문서1", "문서2", "문서3"]
    results = await text_embedder.embed_docs(docs)

    dimensions = [len(v) for v in results]
    assert len(set(dimensions)) == 1, f"벡터 차원이 일치하지 않음: {dimensions}"
