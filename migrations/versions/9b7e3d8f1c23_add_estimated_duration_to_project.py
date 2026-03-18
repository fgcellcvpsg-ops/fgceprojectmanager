"""add_estimated_duration_to_project

Revision ID: 9b7e3d8f1c23
Revises: 14410d864504
Create Date: 2026-01-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '9b7e3d8f1c23'
down_revision = '14410d864504'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.add_column(sa.Column('estimated_duration', sa.String(length=50), nullable=True))


def downgrade():
    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.drop_column('estimated_duration')

