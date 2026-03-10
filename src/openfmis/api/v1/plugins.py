"""Plugin registry endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user, get_superuser
from openfmis.models.user import User
from openfmis.schemas.plugin import PluginOut, PluginRegister, PluginUpdate
from openfmis.services.plugin import PluginAlreadyExistsError, PluginNotFoundError, PluginService

router = APIRouter(prefix="/plugins", tags=["plugins"])


@router.get("", response_model=list[PluginOut])
async def list_plugins(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    active_only: bool = False,
) -> list[PluginOut]:
    """List all registered plugins (superuser sees all; others see active-only)."""
    svc = PluginService(db)
    plugins = await svc.list_plugins(active_only=active_only or not current_user.is_superuser)
    return [PluginOut.model_validate(p) for p in plugins]


@router.get("/{slug}", response_model=PluginOut)
async def get_plugin(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PluginOut:
    svc = PluginService(db)
    plugin = await svc.get_plugin(slug)
    if plugin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plugin not found")
    return PluginOut.model_validate(plugin)


@router.post("", response_model=PluginOut, status_code=status.HTTP_201_CREATED)
async def register_plugin(
    data: PluginRegister,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_superuser)],
) -> PluginOut:
    """Register a new plugin. Superuser only."""
    svc = PluginService(db)
    try:
        plugin = await svc.register(data)
        await db.commit()
    except PluginAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Plugin slug '{data.slug}' already registered",
        )
    return PluginOut.model_validate(plugin)


@router.patch("/{slug}", response_model=PluginOut)
async def update_plugin(
    slug: str,
    data: PluginUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_superuser)],
) -> PluginOut:
    """Update plugin metadata. Superuser only."""
    svc = PluginService(db)
    try:
        plugin = await svc.update(slug, data)
        await db.commit()
    except PluginNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plugin not found")
    return PluginOut.model_validate(plugin)


@router.post("/{slug}/activate", response_model=PluginOut)
async def activate_plugin(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_superuser)],
) -> PluginOut:
    svc = PluginService(db)
    try:
        plugin = await svc.set_active(slug, True)
        await db.commit()
    except PluginNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plugin not found")
    return PluginOut.model_validate(plugin)


@router.post("/{slug}/deactivate", response_model=PluginOut)
async def deactivate_plugin(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_superuser)],
) -> PluginOut:
    svc = PluginService(db)
    try:
        plugin = await svc.set_active(slug, False)
        await db.commit()
    except PluginNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plugin not found")
    return PluginOut.model_validate(plugin)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_plugin(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_superuser)],
) -> None:
    """Remove a plugin registration. Superuser only."""
    svc = PluginService(db)
    try:
        await svc.unregister(slug)
        await db.commit()
    except PluginNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plugin not found")
