from types import SimpleNamespace

import pytest

from app.security.authorization import Permission, ProjectRole, require_permission


def membership(role):
    return SimpleNamespace(role=role, is_active=True)


@pytest.mark.parametrize(
    ("role", "permission"),
    [
        (ProjectRole.OWNER, Permission.PROJECT_ADMIN),
        (ProjectRole.OPERATOR, Permission.ENVIRONMENT_DELETE),
        (ProjectRole.DEVELOPER, Permission.ENVIRONMENT_CREATE),
        (ProjectRole.VIEWER, Permission.ENVIRONMENT_READ),
    ],
)
def test_project_roles_grant_expected_permissions(role, permission):
    require_permission(membership(role), permission)


def test_viewer_cannot_create_environments():
    with pytest.raises(PermissionError):
        require_permission(membership(ProjectRole.VIEWER), Permission.ENVIRONMENT_CREATE)


def test_inactive_membership_has_no_permissions():
    inactive = SimpleNamespace(role=ProjectRole.OWNER, is_active=False)
    with pytest.raises(PermissionError):
        require_permission(inactive, Permission.ENVIRONMENT_READ)
