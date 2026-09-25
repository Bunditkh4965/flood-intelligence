"""configure public impact eligibility and optimize its time-window filter"""

from alembic import op

revision = "20260925_0006"
down_revision = "20260925_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO system_configurations (key, value)
        VALUES ('PUBLIC_IMPACT_VERIFICATION_STATUSES', 'VERIFIED,PENDING_REVIEW')
        ON CONFLICT (key) DO NOTHING
    """)
    op.execute("""
        CREATE INDEX ix_flood_reports_public_impact_eligibility
        ON flood_reports (verification_status, reported_at DESC)
        WHERE source = 'PUBLIC' AND status = 'ACTIVE'
    """)


def downgrade() -> None:
    op.drop_index("ix_flood_reports_public_impact_eligibility", table_name="flood_reports")
    op.execute("DELETE FROM system_configurations WHERE key = 'PUBLIC_IMPACT_VERIFICATION_STATUSES'")
