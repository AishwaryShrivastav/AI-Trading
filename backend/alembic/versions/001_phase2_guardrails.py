"""Phase 2 - Guardrails: create earnings_calendar and symbol_master tables

Revision ID: 001_phase2_guardrails
Revises: 
Create Date: 2025-10-21
"""

from alembic import op
import sqlalchemy as sa


revision = '001_phase2_guardrails'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # earnings_calendar
    op.create_table(
        'earnings_calendar',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('symbol', sa.String(length=20), nullable=False, index=True),
        sa.Column('event_date', sa.Date(), nullable=False, index=True),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('source', sa.String(length=100)),
        sa.Column('created_at', sa.DateTime()),
    )
    op.create_index('ix_earnings_calendar_symbol_date', 'earnings_calendar', ['symbol', 'event_date'])

    # symbol_master
    op.create_table(
        'symbol_master',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('symbol', sa.String(length=20), nullable=False, unique=True, index=True),
        sa.Column('company_name', sa.String(length=200)),
        sa.Column('sector', sa.String(length=100), index=True),
        sa.Column('industry', sa.String(length=100)),
        sa.Column('exchange', sa.String(length=10), server_default='NSE'),
        sa.Column('isin', sa.String(length=20)),
        sa.Column('updated_at', sa.DateTime()),
    )

    # Optional performance indexes against existing tables (if present)
    try:
        op.create_index('ix_events_symbol_created_at', 'events', ['symbols', 'event_timestamp'])
    except Exception:
        pass
    try:
        op.create_index('ix_market_data_cache_symbol_ts', 'market_data_cache', ['symbol', 'timestamp'])
    except Exception:
        pass


def downgrade():
    try:
        op.drop_index('ix_market_data_cache_symbol_ts', table_name='market_data_cache')
    except Exception:
        pass
    try:
        op.drop_index('ix_events_symbol_created_at', table_name='events')
    except Exception:
        pass
    op.drop_table('symbol_master')
    op.drop_index('ix_earnings_calendar_symbol_date', table_name='earnings_calendar')
    op.drop_table('earnings_calendar')


