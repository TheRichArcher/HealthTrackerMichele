"""Add username field to User model

Revision ID: add_username_field
Revises: bd64caab1b9b  # This is correctly set now
Create Date: 2025-03-13 19:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = 'add_username_field'
down_revision = 'bd64caab1b9b'  # Correct previous revision ID
branch_labels = None
depends_on = None

def upgrade():
    """Add the username column if it doesn't already exist and populate usernames for existing users."""
    conn = op.get_bind()
    inspector = inspect(conn)

    # Check if 'username' column already exists
    columns = [col['name'] for col in inspector.get_columns('users')]
    if 'username' not in columns:
        op.add_column('users', sa.Column('username', sa.String(50), nullable=True))

    # Assign default usernames for users who don't have one
    users = conn.execute('SELECT id, email FROM users WHERE username IS NULL').fetchall()
    for user_id, email in users:
        username = email.split('@')[0]
        base_username = username
        count = 1
        
        # Ensure uniqueness by appending a number if needed
        while conn.execute(f"SELECT id FROM users WHERE username = '{username}'").fetchone():
            username = f"{base_username}{count}"
            count += 1

        conn.execute(f"UPDATE users SET username = '{username}' WHERE id = {user_id}")

    # Add unique constraint on username
    op.create_unique_constraint('uq_users_username', 'users', ['username'])

def downgrade():
    """Remove the username column and its unique constraint."""
    op.drop_constraint('uq_users_username', 'users', type_='unique')
    op.drop_column('users', 'username')
