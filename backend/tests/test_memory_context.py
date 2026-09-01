from app.memory import KnowledgeSnippet, MemorySnippet, RetrievedContext
from app.memory.render import render_retrieved_context


def test_retrieved_context_render_separates_memory_and_knowledge():
    context = RetrievedContext(
        behavioral_memories=[
            MemorySnippet(
                kind="behavioral",
                content="维尼 2026-06-01 呕吐",
                date="2026-06-01",
                entity_id="event-1",
            )
        ],
        cognitive_memories=[
            MemorySnippet(
                kind="cognitive",
                content="维尼对肠胃不适比较敏感，用户偏好先观察饮水和精神状态。",
            )
        ],
        knowledge_snippets=[
            KnowledgeSnippet(
                title="Dog Vomiting",
                content="Repeated vomiting can require vet care.",
                url="https://example.com",
            )
        ],
    )

    rendered = render_retrieved_context(context, lang="zh")

    assert "## Relevant Pet/User Memory" in rendered
    assert "维尼 2026-06-01 呕吐" in rendered
    assert "## Long-Term Pet/User Memory" in rendered
    assert "肠胃不适比较敏感" in rendered
    assert "## Trusted Pet Health Knowledge" in rendered
    assert "Dog Vomiting" in rendered
    assert "https://example.com" in rendered


def test_empty_retrieved_context_renders_empty_string():
    assert render_retrieved_context(RetrievedContext(), lang="en") == ""


def test_renderer_limits_snippets():
    context = RetrievedContext(
        behavioral_memories=[
            MemorySnippet(kind="behavioral", content=f"memory {i}") for i in range(5)
        ],
        knowledge_snippets=[
            KnowledgeSnippet(title=f"Knowledge {i}", content=f"content {i}") for i in range(5)
        ],
    )

    rendered = render_retrieved_context(context, lang="en", limit=3)

    assert "memory 0" in rendered
    assert "memory 2" in rendered
    assert "memory 3" not in rendered
    assert "Knowledge 2" in rendered
    assert "Knowledge 3" not in rendered
