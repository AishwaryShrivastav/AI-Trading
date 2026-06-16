"""Step 3 - Backtesting: create backtest_results table

Revision ID: 004_backtest_results
Revises: 003_paper_mode
Create Date: 2026-06-16
"""

from alembic import op
import sqlalchemy as sa


revision = '004_backtest_results'
down_revision = '003_paper_mode'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if 'backtest_results' in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        'backtest_results',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('strategy', sa.String(length=50), nullable=False, index=True),
        sa.Column('symbol', sa.String(length=20), nullable=False, index=True),
        sa.Column('exchange', sa.String(length=10), server_default='NSE'),
        sa.Column('interval', sa.String(length=10), server_default='1D'),
        sa.Column('start_date', sa.String(length=40)),
        sa.Column('end_date', sa.String(length=40)),
        sa.Column('num_trades', sa.Integer(), server_default='0'),
        sa.Column('win_rate', sa.Float()),
        sa.Column('total_return_pct', sa.Float()),
        sa.Column('cagr', sa.Float()),
        sa.Column('sharpe', sa.Float()),
        sa.Column('max_drawdown', sa.Float()),
        sa.Column('avg_hold_days', sa.Float()),
        sa.Column('params', sa.JSON()),
        sa.Column('trades', sa.JSON()),
        sa.Column('created_at', sa.DateTime()),
    )


def downgrade():
    op.drop_table('backtest_results')
