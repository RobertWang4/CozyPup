from app.rag.base import BaseRetriever, RetrievalResult


class TestRetrievalResult:
    def test_create(self):
        r = RetrievalResult(
            content="test content",
            source_type="chat_turn",
            source_id="abc-123",
            score=0.85,
            metadata={"date": "2026-03-22"},
        )
        assert r.content == "test content"
        assert r.score == 0.85

    def test_sort_by_score(self):
        results = [
            RetrievalResult("a", "chat_turn", "1", 0.5, {}),
            RetrievalResult("b", "chat_turn", "2", 0.9, {}),
            RetrievalResult("c", "chat_turn", "3", 0.7, {}),
        ]
        sorted_results = sorted(results, key=lambda r: r.score, reverse=True)
        assert [r.content for r in sorted_results] == ["b", "c", "a"]
