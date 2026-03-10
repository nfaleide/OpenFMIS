"""MVT tile endpoints — /tiles/{layer}/{z}/{x}/{y}.mvt"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.services.tiles import MAX_ZOOM, MIN_ZOOM, VALID_LAYERS, TileService

router = APIRouter(prefix="/tiles", tags=["tiles"])

MVT_CONTENT_TYPE = "application/vnd.mapbox-vector-tile"


@router.get(
    "/{layer}/{z}/{x}/{y}.mvt",
    responses={
        200: {"content": {MVT_CONTENT_TYPE: {}}},
        204: {"description": "Tile exists but contains no features"},
        404: {"description": "Unknown layer"},
    },
)
async def get_tile(
    layer: str,
    z: Annotated[int, Path(ge=MIN_ZOOM, le=MAX_ZOOM)],
    x: Annotated[int, Path(ge=0)],
    y: Annotated[int, Path(ge=0)],
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Response:
    """Serve a Mapbox Vector Tile for the requested layer and tile coordinates.

    Layers: fields · clu · plss_townships · plss_sections · analysis_zones

    Tiles use EPSG:3857 (Web Mercator) as required by the MVT spec.
    Add `Authorization: Bearer <token>` header to all requests.
    """
    if layer not in VALID_LAYERS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown layer '{layer}'. Valid layers: {sorted(VALID_LAYERS)}",
        )

    svc = TileService(db)
    mvt = await svc.get_tile(layer, z, x, y)

    if mvt is None:
        # Empty tile — return 204 so clients don't cache stale data
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return Response(
        content=mvt,
        media_type=MVT_CONTENT_TYPE,
        headers={
            "Cache-Control": "public, max-age=60",
            "Content-Encoding": "identity",
        },
    )


@router.get("/layers", response_model=list[str])
async def list_layers(
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[str]:
    """List available tile layers."""
    return sorted(VALID_LAYERS)
