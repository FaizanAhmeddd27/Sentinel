from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.user import User, UserRole, UserStatus
from app.models.audit import AuditLog
from app.dependencies.auth import get_current_user, require_roles
from app.schemas.user import (
    UserResponse,
    UserListResponse,
    UserRoleUpdate,
    UserStatusUpdate,
)
from typing import Optional
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/users", tags=["User Management"])


@router.get("", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: Optional[UserRole] = Query(None),
    status: Optional[UserStatus] = Query(None),
    search: Optional[str] = Query(None, description="Search by email or name"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.admin, UserRole.supervisor])),
):
    """List all users. Admin and Supervisor only."""
    query = select(User).order_by(User.created_at.desc())

    if role:
        query = query.where(User.role == role)
    if status:
        query = query.where(User.status == status)
    if search:
        query = query.where(
            (User.email.ilike(f"%{search}%")) |
            (User.full_name.ilike(f"%{search}%"))
        )

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    users = result.scalars().all()

    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.admin, UserRole.supervisor])),
):
    """Get a single user by ID."""
    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse.model_validate(user)


@router.patch("/{user_id}/role")
async def update_user_role(
    user_id: str,
    body: UserRoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.admin])),
):
    """Change a user's role. Admin only."""
    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent self-demotion
    if str(user.id) == str(current_user.id):
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    old_role = user.role
    user.role = body.role
    user.updated_at = datetime.now(timezone.utc)

    # Write audit log
    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        actor_role=current_user.role.value,
        action="user.role_changed",
        resource_type="user",
        resource_id=str(user.id),
        description=f"Role changed from {old_role.value} to {body.role.value}",
        before_state={"role": old_role.value},
        after_state={"role": body.role.value},
    )
    db.add(audit)
    await db.commit()

    return {
        "message": "Role updated",
        "user_id": user_id,
        "old_role": old_role,
        "new_role": body.role,
    }


@router.patch("/{user_id}/status")
async def update_user_status(
    user_id: str,
    body: UserStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.admin])),
):
    """Activate or deactivate a user. Admin only."""
    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if str(user.id) == str(current_user.id):
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    old_status = user.status
    user.status = body.status
    user.updated_at = datetime.now(timezone.utc)

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        actor_role=current_user.role.value,
        action="user.status_changed",
        resource_type="user",
        resource_id=str(user.id),
        description=f"Status changed from {old_status.value} to {body.status.value}",
        before_state={"status": old_status.value},
        after_state={"status": body.status.value},
    )
    db.add(audit)
    await db.commit()

    return {
        "message": "Status updated",
        "user_id": user_id,
        "new_status": body.status,
    }


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.admin])),
):
    """Remove a user. Admin only. Performs soft-delete (deactivates)."""
    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if str(user.id) == str(current_user.id):
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    # Soft delete — deactivate rather than destroy
    user.status = UserStatus.inactive
    user.updated_at = datetime.now(timezone.utc)

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        actor_role=current_user.role.value,
        action="user.deleted",
        resource_type="user",
        resource_id=str(user.id),
        description=f"User {user.email} soft-deleted (deactivated)",
        before_state={"status": "active", "email": user.email},
        after_state={"status": "inactive"},
    )
    db.add(audit)
    await db.commit()

    return {"message": "User deactivated", "user_id": user_id}