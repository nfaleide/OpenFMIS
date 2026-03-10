"""CLU model — USDA Common Land Units."""

from geoalchemy2 import Geometry
from sqlalchemy import Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from openfmis.models.base import Base


class CLU(Base):
    __tablename__ = "clu"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    county_fips: Mapped[str | None] = mapped_column(String(5), nullable=True)
    calcacres: Mapped[float | None] = mapped_column(Float, nullable=True)
    # geoalchemy2 auto-creates a GIST index for Geometry columns
    geom: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=True
    )

    __table_args__ = (Index("idx_clu_state_county", "state", "county_fips"),)

    def __repr__(self) -> str:
        return f"<CLU {self.state} {self.county_fips} {self.calcacres}ac>"
