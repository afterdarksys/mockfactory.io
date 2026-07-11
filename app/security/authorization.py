from enum import Enum


class ProjectRole(str, Enum):
    OWNER = "owner"
    OPERATOR = "operator"
    DEVELOPER = "developer"
    VIEWER = "viewer"


class Permission(str, Enum):
    PROJECT_ADMIN = "project:admin"
    ENVIRONMENT_CREATE = "environment:create"
    ENVIRONMENT_READ = "environment:read"
    ENVIRONMENT_UPDATE = "environment:update"
    ENVIRONMENT_DELETE = "environment:delete"
    SECRET_READ = "secret:read"
    AUDIT_READ = "audit:read"


ROLE_PERMISSIONS = {
    ProjectRole.OWNER: set(Permission),
    ProjectRole.OPERATOR: {
        Permission.ENVIRONMENT_CREATE,
        Permission.ENVIRONMENT_READ,
        Permission.ENVIRONMENT_UPDATE,
        Permission.ENVIRONMENT_DELETE,
        Permission.SECRET_READ,
        Permission.AUDIT_READ,
    },
    ProjectRole.DEVELOPER: {
        Permission.ENVIRONMENT_CREATE,
        Permission.ENVIRONMENT_READ,
        Permission.ENVIRONMENT_UPDATE,
        Permission.SECRET_READ,
    },
    ProjectRole.VIEWER: {Permission.ENVIRONMENT_READ},
}


def require_permission(membership, permission: Permission) -> None:
    if not membership or not membership.is_active:
        raise PermissionError("Active project membership required")
    role = ProjectRole(membership.role)
    if permission not in ROLE_PERMISSIONS[role]:
        raise PermissionError(f"Permission required: {permission.value}")
