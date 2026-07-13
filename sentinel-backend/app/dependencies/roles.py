"""
Role-based access control helpers.
All role enforcement is centralized here.

Usage in routes:
    from app.dependencies.roles import (
        AdminOnly,
        AdminOrSupervisor,
        AnyAuthenticatedUser,
        ReadOnlyForCompliance,
    )

    @router.get("/admin-only-route")
    async def my_route(current_user: User = Depends(AdminOnly)):
        ...
"""

from fastapi import Depends
from app.dependencies.auth import get_current_user, require_roles
from app.models.user import User, UserRole

# Pre-built role dependency instances
AdminOnly = Depends(require_roles([UserRole.admin]))

AdminOrSupervisor = Depends(
    require_roles([UserRole.admin, UserRole.supervisor])
)

AnyAuthenticatedUser = Depends(get_current_user)

AnalystAndAbove = Depends(
    require_roles([UserRole.admin, UserRole.supervisor, UserRole.analyst])
)

ComplianceAndAbove = Depends(
    require_roles([UserRole.admin, UserRole.supervisor, UserRole.compliance])
)


class ReadOnlyForCompliance:
    """
    Dependency that allows compliance officers read access only.
    Raise 403 if they try to mutate (POST/PATCH/DELETE).
    """
    def __init__(self, allow_methods: list = None):
        self.allow_methods = allow_methods or ["GET", "HEAD", "OPTIONS"]

    async def __call__(
        self,
        request,
        current_user: User = Depends(get_current_user),
    ) -> User:
        from fastapi import HTTPException
        if (
            current_user.role == UserRole.compliance
            and request.method not in self.allow_methods
        ):
            raise HTTPException(
                status_code=403,
                detail="Compliance Officers have read-only access. "
                       "Cannot perform write operations.",
            )
        return current_user