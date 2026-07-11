"""Add organizations, projects, audit events, scoped keys, and node identities."""
from alembic import op
import sqlalchemy as sa

revision = "20260711_security"
down_revision = "add_ai_usage_001"
branch_labels = None
depends_on = None


def upgrade():
    organization_role = sa.Enum("OWNER", "ADMIN", "MEMBER", name="organizationrole")
    project_role = sa.Enum("OWNER", "OPERATOR", "DEVELOPER", "VIEWER", name="projectrole")
    organization_role.create(op.get_bind(), checkfirst=True)
    project_role.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(63), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("slug", sa.String(63), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("organization_id", "slug"),
    )
    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", organization_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("organization_id", "user_id"),
    )
    op.create_table(
        "project_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", project_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("project_id", "user_id"),
    )
    op.create_table(
        "node_agents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("node_id", sa.String(128), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("credential_hash", sa.String(64), nullable=False),
        sa.Column("certificate_fingerprint", sa.String(128), unique=True),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("credential_expires_at", sa.DateTime()),
        sa.Column("last_seen_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id")),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id")),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64)),
        sa.Column("resource_id", sa.String(255)),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("request_id", sa.String(128)),
        sa.Column("operation_id", sa.String(128)),
        sa.Column("source_address", sa.String(64)),
        sa.Column("details", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.add_column("api_keys", sa.Column("project_id", sa.Integer(), nullable=True))
    op.add_column("api_keys", sa.Column("scopes", sa.JSON(), nullable=False, server_default="[]"))
    op.create_foreign_key("fk_api_keys_project", "api_keys", "projects", ["project_id"], ["id"])


def downgrade():
    op.drop_constraint("fk_api_keys_project", "api_keys", type_="foreignkey")
    op.drop_column("api_keys", "scopes")
    op.drop_column("api_keys", "project_id")
    op.drop_table("audit_events")
    op.drop_table("node_agents")
    op.drop_table("project_memberships")
    op.drop_table("organization_memberships")
    op.drop_table("projects")
    op.drop_table("organizations")
    sa.Enum(name="projectrole").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="organizationrole").drop(op.get_bind(), checkfirst=True)
