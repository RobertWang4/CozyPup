"""add memweaver memory tables

Revision ID: 20260613_01
Revises: a221d46e0058
Create Date: 2026-06-13 14:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy.vector
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260613_01"
down_revision: Union[str, Sequence[str], None] = "a221d46e0058"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    memorynodetype = postgresql.ENUM(
        "behavioral", "cognitive", "knowledge", name="memorynodetype", create_type=False
    )
    memoryedgetype = postgresql.ENUM(
        "semantic", "temporal", "hierarchy", name="memoryedgetype", create_type=False
    )
    memorynodetype.create(op.get_bind(), checkfirst=True)
    memoryedgetype.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "memory_nodes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("pet_id", sa.UUID(), nullable=True),
        sa.Column("node_type", memorynodetype, nullable=False),
        sa.Column("source_kind", sa.String(length=50), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1536), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["pet_id"], ["pets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_type", "source_kind", "source_id", name="uq_memory_nodes_source"),
    )
    op.create_index("ix_memory_nodes_user_id", "memory_nodes", ["user_id"])
    op.create_index("ix_memory_nodes_pet_id", "memory_nodes", ["pet_id"])
    op.create_index("ix_memory_nodes_node_type", "memory_nodes", ["node_type"])
    op.create_index("ix_memory_nodes_occurred_at", "memory_nodes", ["occurred_at"])
    op.execute("""
        CREATE INDEX ix_memory_nodes_vector ON memory_nodes
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    op.create_table(
        "memory_edges",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_node_id", sa.UUID(), nullable=False),
        sa.Column("target_node_id", sa.UUID(), nullable=False),
        sa.Column("edge_type", memoryedgetype, nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_node_id"], ["memory_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_node_id"], ["memory_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_node_id", "target_node_id", "edge_type", name="uq_memory_edges_pair_type"),
    )
    op.create_index("ix_memory_edges_source_node_id", "memory_edges", ["source_node_id"])
    op.create_index("ix_memory_edges_target_node_id", "memory_edges", ["target_node_id"])

    op.execute("""
        INSERT INTO memory_nodes (
            id,
            user_id,
            pet_id,
            node_type,
            source_kind,
            source_id,
            title,
            content,
            embedding,
            metadata_json,
            occurred_at,
            created_at,
            updated_at
        )
        SELECT
            e.id,
            CASE
                WHEN e.source_type::text = 'knowledge_base' THEN NULL
                ELSE e.user_id
            END AS user_id,
            e.pet_id,
            CASE
                WHEN e.source_type::text = 'knowledge_base' THEN 'knowledge'
                WHEN e.source_type::text = 'daily_summary' THEN 'cognitive'
                ELSE 'behavioral'
            END::memorynodetype AS node_type,
            CASE
                WHEN e.source_type::text = 'knowledge_base' THEN 'knowledge_article'
                ELSE e.source_type::text
            END AS source_kind,
            CASE
                WHEN e.source_type::text = 'knowledge_base' THEN e.id
                ELSE e.source_id
            END AS source_id,
            COALESCE(
                e.metadata_json->>'title',
                e.metadata_json->>'event_id',
                e.source_type::text,
                ''
            ) AS title,
            e.content,
            e.embedding,
            (
                COALESCE(e.metadata_json::jsonb, '{}'::jsonb)
                || jsonb_build_object(
                    'legacy_source_type', e.source_type::text,
                    'legacy_source_id', e.source_id::text,
                    'legacy_embedding_id', e.id::text
                )
            )::json AS metadata_json,
            e.created_at,
            e.created_at,
            e.created_at
        FROM embeddings e
        ON CONFLICT ON CONSTRAINT uq_memory_nodes_source DO NOTHING
    """)

    op.drop_table("embeddings")
    op.drop_table("knowledge_articles")


def downgrade() -> None:
    sourcetype = sa.Enum(
        "chat_turn",
        "daily_summary",
        "calendar_event",
        "knowledge_base",
        name="sourcetype",
        create_type=False,
    )

    op.create_table(
        "knowledge_articles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("species", sa.String(length=20), nullable=False),
        sa.Column("url", sa.String(length=2000), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "embeddings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("pet_id", sa.UUID(), nullable=True),
        sa.Column("source_type", sourcetype, nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1536), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["pet_id"], ["pets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("""
        CREATE INDEX ix_embeddings_vector ON embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)
    op.create_index("ix_embeddings_user_source", "embeddings", ["user_id", "source_type"])
    op.create_index(
        "ix_embeddings_user_pet",
        "embeddings",
        ["user_id", "pet_id"],
        postgresql_where=sa.text("pet_id IS NOT NULL"),
    )

    op.drop_index("ix_memory_edges_target_node_id", table_name="memory_edges")
    op.drop_index("ix_memory_edges_source_node_id", table_name="memory_edges")
    op.drop_table("memory_edges")
    op.execute("DROP INDEX IF EXISTS ix_memory_nodes_vector")
    op.drop_index("ix_memory_nodes_occurred_at", table_name="memory_nodes")
    op.drop_index("ix_memory_nodes_node_type", table_name="memory_nodes")
    op.drop_index("ix_memory_nodes_pet_id", table_name="memory_nodes")
    op.drop_index("ix_memory_nodes_user_id", table_name="memory_nodes")
    op.drop_table("memory_nodes")
    sa.Enum(name="memoryedgetype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="memorynodetype").drop(op.get_bind(), checkfirst=True)
