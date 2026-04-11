# Pet Health Knowledge Base

Place markdown files here for RAG ingestion.

## Format

Each file can optionally have YAML frontmatter:

    ---
    title: 犬呕吐常见原因与处理
    url: https://source-url.com/article
    ---

    ## 症状描述
    ...

    ## 问诊问题
    1. 呕吐物颜色？
    2. 频率？

    ## 判断逻辑
    - 黄色液体 + 单次 → ...

## Ingest

    cd backend
    python -m app.rag.ingest --file knowledge/dog_vomiting.md --species dog --category 消化系统
    python -m app.rag.ingest --dir knowledge/ --species dog
    python -m app.rag.ingest --stats
