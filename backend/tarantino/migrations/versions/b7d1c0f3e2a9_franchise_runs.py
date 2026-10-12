"""franchise runs

Revision ID: b7d1c0f3e2a9
Revises: 92f4c400d69d
Create Date: 2026-10-12 20:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'b7d1c0f3e2a9'
down_revision = '92f4c400d69d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('franchise',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('collection_id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(), nullable=True),
    sa.Column('any_order', sa.Boolean(), nullable=False),
    sa.Column('order', sa.JSON(), nullable=False),
    sa.Column('excluded', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_franchise')),
    sa.UniqueConstraint('collection_id', name=op.f('uq_franchise_collection_id'))
    )
    op.create_table('franchise_run',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('collection_id', sa.String(length=32), nullable=False),
    sa.Column('started_parts', sa.JSON(), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('last_advanced_at', sa.DateTime(), nullable=False),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_franchise_run')),
    sa.UniqueConstraint('collection_id', name=op.f('uq_franchise_run_collection_id'))
    )
    op.create_table('library_collection',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('synced_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_library_collection'))
    )
    with op.batch_alter_table('programme_entry', schema=None) as batch_op:
        batch_op.add_column(sa.Column('marathon', sa.JSON(), nullable=False, server_default='[]'))
        batch_op.add_column(sa.Column('last_started_at', sa.DateTime(), nullable=True))
    op.execute('UPDATE programme_entry SET last_started_at = first_started_at')

    with op.batch_alter_table('cassette', schema=None) as batch_op:
        batch_op.add_column(sa.Column('target', sa.String(length=16), nullable=False, server_default='room'))
        batch_op.alter_column('room_id', existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM cassette WHERE target != 'room'")
    with op.batch_alter_table('cassette', schema=None) as batch_op:
        batch_op.alter_column('room_id', existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column('target')
    with op.batch_alter_table('programme_entry', schema=None) as batch_op:
        batch_op.drop_column('last_started_at')
        batch_op.drop_column('marathon')
    op.drop_table('library_collection')
    op.drop_table('franchise_run')
    op.drop_table('franchise')
