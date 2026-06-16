"""Step 1 - Paper trading: add is_paper flag to orders/positions (v1 + v2)

Revision ID: 003_paper_mode
Revises: 002_phase2_options
Create Date: 2026-06-16
"""

from alembic import op
import sqlalchemy as sa


revision = '003_paper_mode'
down_revision = '002_phase2_options'
branch_labels = None
depends_on = None


_TABLES = ['orders', 'positions', 'orders_v2', 'positions_v2']


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return True  # nothing to do if table doesn't exist yet
    return column in {c['name'] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    for table in _TABLES:
        if not _has_column(bind, table, 'is_paper'):
            op.add_column(
                table,
                sa.Column('is_paper', sa.Boolean(), nullable=False, server_default=sa.false()),
            )
            op.create_index(f'ix_{table}_is_paper', table, ['is_paper'])


def downgrade():
    for table in _TABLES:
        try:
            op.drop_index(f'ix_{table}_is_paper', table_name=table)
        except Exception:
            pass
        try:
            op.drop_column(table, 'is_paper')
        except Exception:
            pass
