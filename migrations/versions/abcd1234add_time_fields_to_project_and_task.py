"""add_time_fields_to_project_and_task

Revision ID: abcd1234addt
Revises: 9b7e3d8f1c23
Create Date: 2026-01-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'abcd1234addt'
down_revision = '9b7e3d8f1c23'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.add_column(sa.Column('estimated_hours', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('spent_hours', sa.Float(), nullable=True))

    with op.batch_alter_table('task', schema=None) as batch_op:
        batch_op.add_column(sa.Column('estimated_hours', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('spent_hours', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('task', schema=None) as batch_op:
        batch_op.drop_column('spent_hours')
        batch_op.drop_column('estimated_hours')

    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.drop_column('spent_hours')
        batch_op.drop_column('estimated_hours')

