"""Add temp_user_id and align reports table

Revision ID: 00792392f95e
Revises: eb0182b8c49e
Create Date: 2025-03-17 19:03:42.212742

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '00792392f95e'
down_revision: Union[str, None] = 'eb0182b8c49e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    # Add new columns to reports table
    op.add_column('reports', sa.Column('temp_user_id', sa.String(length=255), nullable=True))
    op.add_column('reports', sa.Column('assessment_id', sa.Integer(), nullable=True))
    op.add_column('reports', sa.Column('status', sa.String(length=50), nullable=True, server_default='PENDING'))
    op.add_column('reports', sa.Column('report_url', sa.String(length=255), nullable=True))
    op.add_column('reports', sa.Column('updated_at', sa.DateTime(), nullable=True))

    # Alter existing columns to be nullable
    op.alter_column('reports', 'user_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.alter_column('reports', 'title',
               existing_type=sa.VARCHAR(length=255),
               nullable=True)
    op.alter_column('reports', 'content',
               existing_type=sa.TEXT(),
               nullable=True)
    op.alter_column('reports', 'care_recommendation',
               existing_type=postgresql.ENUM('HOME_CARE', 'SEE_DOCTOR', 'URGENT_CARE', name='carerecommendationenum'),
               nullable=True)
    op.alter_column('reports', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)

    # Add foreign key constraint for assessment_id
    op.create_foreign_key(None, 'reports', 'symptom_logs', ['assessment_id'], ['id'])

def downgrade() -> None:
    """Downgrade schema."""
    # Remove foreign key
    op.drop_constraint(None, 'reports', type_='foreignkey')

    # Revert altered columns back to NOT NULL
    op.alter_column('reports', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=False)
    op.alter_column('reports', 'care_recommendation',
               existing_type=postgresql.ENUM('HOME_CARE', 'SEE_DOCTOR', 'URGENT_CARE', name='carerecommendationenum'),
               nullable=False)
    op.alter_column('reports', 'content',
               existing_type=sa.TEXT(),
               nullable=False)
    op.alter_column('reports', 'title',
               existing_type=sa.VARCHAR(length=255),
               nullable=False)
    op.alter_column('reports', 'user_id',
               existing_type=sa.INTEGER(),
               nullable=False)

    # Drop added columns
    op.drop_column('reports', 'updated_at')
    op.drop_column('reports', 'report_url')
    op.drop_column('reports', 'status')
    op.drop_column('reports', 'assessment_id')
    op.drop_column('reports', 'temp_user_id')
