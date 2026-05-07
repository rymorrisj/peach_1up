"""add platform system fields

Revision ID: a3f1c8e20b47
Revises: e76d9b5bd889
Create Date: 2026-05-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3f1c8e20b47'
down_revision: Union[str, Sequence[str], None] = 'e76d9b5bd889'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('platforms', sa.Column('slug', sa.String(length=100), nullable=True))
    op.add_column('platforms', sa.Column('is_system', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('platforms', sa.Column('download_url', sa.String(length=500), nullable=True))
    op.add_column('platforms', sa.Column('supported_eras', sa.Text(), nullable=True))
    op.add_column('platforms', sa.Column('default_flags', sa.Text(), nullable=True))
    op.create_unique_constraint('uq_platforms_slug', 'platforms', ['slug'])


def downgrade() -> None:
    op.drop_constraint('uq_platforms_slug', 'platforms', type_='unique')
    op.drop_column('platforms', 'default_flags')
    op.drop_column('platforms', 'supported_eras')
    op.drop_column('platforms', 'download_url')
    op.drop_column('platforms', 'is_system')
    op.drop_column('platforms', 'slug')
