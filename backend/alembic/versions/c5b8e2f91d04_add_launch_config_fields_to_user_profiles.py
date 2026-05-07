"""add launch config fields to user_profiles

Revision ID: c5b8e2f91d04
Revises: a3f1c8e20b47
Create Date: 2026-05-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c5b8e2f91d04'
down_revision: Union[str, Sequence[str], None] = 'a3f1c8e20b47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user_profiles', sa.Column('platform_slug', sa.String(length=100), nullable=True))
    op.add_column('user_profiles', sa.Column('era', sa.String(length=50), nullable=True))
    op.add_column('user_profiles', sa.Column('custom_flags', sa.Text(), nullable=True))
    op.add_column('user_profiles', sa.Column('rom_pack_path', sa.String(length=500), nullable=True))
    op.add_column('user_profiles', sa.Column('custom_script', sa.Text(), nullable=True))
    op.add_column('user_profiles', sa.Column('notes', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('user_profiles', 'notes')
    op.drop_column('user_profiles', 'custom_script')
    op.drop_column('user_profiles', 'rom_pack_path')
    op.drop_column('user_profiles', 'custom_flags')
    op.drop_column('user_profiles', 'era')
    op.drop_column('user_profiles', 'platform_slug')
