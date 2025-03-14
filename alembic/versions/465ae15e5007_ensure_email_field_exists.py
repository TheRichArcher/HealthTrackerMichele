"""Ensure email field exists and update care_recommendation ENUM

Revision ID: 465ae15e5007
Revises: add_username_field
Create Date: 2025-03-13 21:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Revision identifiers, used by Alembic.
revision = '465ae15e5007'
down_revision = 'add_username_field'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Ensure 'email' column exists in 'users' table
    columns = [col['name'] for col in inspector.get_columns('users')]
    if 'email' not in columns:
        op.add_column('users', sa.Column('email', sa.String(120), unique=True, nullable=True))

        # Assign placeholder emails for users with NULL email
        conn.execute(
            "UPDATE users SET email = CONCAT('user', id, '@placeholder.com') WHERE email IS NULL"
        )

        # Make email column non-nullable after populating it
        op.alter_column('users', 'email', nullable=False)

    # Modify care_recommendation ENUM type in 'reports' table
    old_enum_name = 'care_recommendation_enum'
    new_enum_name = 'carerecommendationenum'

    # Create the new ENUM type
    new_enum = postgresql.ENUM('HOME_CARE', 'SEE_DOCTOR', 'URGENT_CARE', name=new_enum_name)
    new_enum.create(op.get_bind(), checkfirst=True)

    # Temporarily change the column type to TEXT before altering ENUM
    op.execute("ALTER TABLE reports ALTER COLUMN care_recommendation TYPE TEXT;")

    # Convert text values before altering the column type back to ENUM
    op.execute(f"""
        ALTER TABLE reports ALTER COLUMN care_recommendation 
        TYPE {new_enum_name} 
        USING CASE 
            WHEN care_recommendation = 'You can likely manage this at home.' THEN 'HOME_CARE'::{new_enum_name}
            WHEN care_recommendation = 'Consider seeing a doctor soon.' THEN 'SEE_DOCTOR'::{new_enum_name}
            WHEN care_recommendation = 'You should seek urgent care.' THEN 'URGENT_CARE'::{new_enum_name}
            ELSE NULL 
        END;
    """)

    # Drop old ENUM type
    op.execute(f"DROP TYPE {old_enum_name} CASCADE;")


def downgrade():
    conn = op.get_bind()

    # Revert the 'email' column changes
    op.alter_column('users', 'email', nullable=True)
    op.drop_column('users', 'email')

    # Revert care_recommendation ENUM type back to original
    old_enum_name = 'care_recommendation_enum'
    new_enum_name = 'carerecommendationenum'

    # Create the old ENUM type again
    old_enum = postgresql.ENUM(
        'You can likely manage this at home.',
        'Consider seeing a doctor soon.',
        'You should seek urgent care.',
        name=old_enum_name
    )
    old_enum.create(op.get_bind(), checkfirst=True)

    # Temporarily change the column type to TEXT before altering ENUM
    op.execute("ALTER TABLE reports ALTER COLUMN care_recommendation TYPE TEXT;")

    # Convert the values back before changing the column type
    op.execute(f"""
        ALTER TABLE reports ALTER COLUMN care_recommendation 
        TYPE {old_enum_name} 
        USING CASE 
            WHEN care_recommendation = 'HOME_CARE' THEN 'You can likely manage this at home.'::{old_enum_name}
            WHEN care_recommendation = 'SEE_DOCTOR' THEN 'Consider seeing a doctor soon.'::{old_enum_name}
            WHEN care_recommendation = 'URGENT_CARE' THEN 'You should seek urgent care.'::{old_enum_name}
            ELSE NULL 
        END;
    """)

    # Drop new ENUM type
    op.execute(f"DROP TYPE {new_enum_name} CASCADE;")
