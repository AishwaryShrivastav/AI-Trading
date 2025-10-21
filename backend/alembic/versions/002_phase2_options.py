"""Phase 2 - Options: create option_chains and option_strategies tables

Revision ID: 002_phase2_options
Revises: 001_phase2_guardrails
Create Date: 2025-10-21
"""

from alembic import op
import sqlalchemy as sa


revision = '002_phase2_options'
down_revision = '001_phase2_guardrails'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'option_chains',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('symbol', sa.String(length=20), nullable=False, index=True),
        sa.Column('exchange', sa.String(length=10), server_default='NSE'),
        sa.Column('expiry', sa.Date(), nullable=False, index=True),
        sa.Column('strike', sa.Float(), nullable=False, index=True),
        sa.Column('ce_ltp', sa.Float()),
        sa.Column('ce_oi', sa.Integer()),
        sa.Column('ce_iv', sa.Float()),
        sa.Column('pe_ltp', sa.Float()),
        sa.Column('pe_oi', sa.Integer()),
        sa.Column('pe_iv', sa.Float()),
        sa.Column('spot_price', sa.Float()),
        sa.Column('atm_iv', sa.Float()),
        sa.Column('pcr', sa.Float()),
        sa.Column('ts', sa.DateTime(), index=True)
    )
    op.create_index('ix_option_chains_symbol_expiry_strike', 'option_chains', ['symbol', 'expiry', 'strike'])

    op.create_table(
        'option_strategies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.Integer(), index=True),
        sa.Column('strategy_type', sa.String(length=50)),
        sa.Column('underlying', sa.String(length=20), index=True),
        sa.Column('exchange', sa.String(length=10), server_default='NSE'),
        sa.Column('expiry', sa.Date()),
        sa.Column('legs', sa.JSON()),
        sa.Column('net_premium', sa.Float()),
        sa.Column('max_profit', sa.Float()),
        sa.Column('max_loss', sa.Float()),
        sa.Column('breakeven_upper', sa.Float()),
        sa.Column('breakeven_lower', sa.Float()),
        sa.Column('margin_required', sa.Float()),
        sa.Column('pop', sa.Float()),
        sa.Column('pnl_scenarios', sa.JSON()),
        sa.Column('status', sa.String(length=20), index=True),
        sa.Column('created_at', sa.DateTime(), index=True),
        sa.Column('executed_at', sa.DateTime())
    )


def downgrade():
    op.drop_table('option_strategies')
    op.drop_index('ix_option_chains_symbol_expiry_strike', table_name='option_chains')
    op.drop_table('option_chains')


