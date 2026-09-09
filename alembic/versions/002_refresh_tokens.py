"""add refresh_tokens table

Revision ID: 002_refresh_tokens
Revises: 001_initial
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa

revision = "002_refresh_tokens"
down_revision = "001_initial"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            jti UUID NOT NULL UNIQUE,
            revoked BOOLEAN DEFAULT false,
            created_at TIMESTAMPTZ DEFAULT now(),
            expira_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
        CREATE INDEX IF NOT EXISTS idx_refresh_tokens_jti ON refresh_tokens(jti);
        ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;
        CREATE POLICY p_refresh_tokens_all ON refresh_tokens FOR ALL USING (true);
    """)

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS refresh_tokens;")
