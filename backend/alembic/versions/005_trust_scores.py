"""Step 7: strategy_trust_scores and weekly_reflections tables.

Revision ID: 005_trust_scores
Revises: 004_backtest_results
"""
from alembic import op
import sqlalchemy as sa

revision = '005_trust_scores'
down_revision = '004_backtest_results'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'strategy_trust_scores',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('strategy', sa.String(50), nullable=False, unique=True, index=True),
        sa.Column('trust_score', sa.Float, default=0.5),
        sa.Column('rolling_win_rate', sa.Float),
        sa.Column('rolling_return_pct', sa.Float),
        sa.Column('trade_count', sa.Integer, default=0),
        sa.Column('last_day_score', sa.Float),
        sa.Column('last_updated', sa.DateTime),
        sa.Column('details', sa.JSON),
    )
    op.create_table(
        'weekly_reflections',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('week_start', sa.DateTime, nullable=False, index=True),
        sa.Column('week_end', sa.DateTime, nullable=False),
        sa.Column('performance_data', sa.JSON),
        sa.Column('reflection', sa.JSON),
        sa.Column('status', sa.String(20), default='PENDING_REVIEW', index=True),
        sa.Column('applied_suggestions', sa.JSON),
        sa.Column('reviewed_at', sa.DateTime),
        sa.Column('reviewed_by', sa.String(50)),
        sa.Column('created_at', sa.DateTime, index=True),
    )


def downgrade():
    op.drop_table('weekly_reflections')
    op.drop_table('strategy_trust_scores')
