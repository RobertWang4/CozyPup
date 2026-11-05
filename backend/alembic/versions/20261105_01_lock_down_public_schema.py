"""lock down public schema from the Supabase Data API

Every public table had RLS off and full grants to `anon` / `authenticated`,
so anyone holding the project's anon key could read/write them through
PostgREST (e.g. users.password_hash, users.is_admin). Nothing uses the Data
API: the backend connects as `postgres` (table owner, BYPASSRLS), so this
does not affect it.

- enable RLS on every public table (no policies -> API roles see nothing)
- revoke all table/sequence privileges from anon/authenticated
- stop default privileges from re-granting them on tables created later

Revision ID: 20261105_01
Revises: 20260912_01
Create Date: 2026-11-05
"""
from alembic import op

revision = "20261105_01"
down_revision = "20260912_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        DECLARE t text;
        BEGIN
          FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
            EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
          END LOOP;
        END $$;
    """)
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated")
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated")
    op.execute("ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated")
    op.execute("ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated")


def downgrade() -> None:
    op.execute("ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated")
    op.execute("ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated")
    op.execute("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated")
    op.execute("GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated")
    op.execute("""
        DO $$
        DECLARE t text;
        BEGIN
          FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
            EXECUTE format('ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY', t);
          END LOOP;
        END $$;
    """)
