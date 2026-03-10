"""PLSS models — Public Land Survey System townships and sections."""

from geoalchemy2 import Geometry
from sqlalchemy import Date, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from openfmis.models.base import Base


class PLSSTownship(Base):
    __tablename__ = "plss_townships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lndkey: Mapped[str | None] = mapped_column(String(50), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    primer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    town: Mapped[int | None] = mapped_column(Integer, nullable=True)
    twnfrt: Mapped[str | None] = mapped_column(String(10), nullable=True)
    twndir: Mapped[str | None] = mapped_column(String(1), nullable=True)
    range_: Mapped[int | None] = mapped_column("range_", Integer, nullable=True)
    rngdir: Mapped[str | None] = mapped_column(String(1), nullable=True)
    rngfrt: Mapped[str | None] = mapped_column(String(10), nullable=True)
    twndup: Mapped[str | None] = mapped_column(String(10), nullable=True)
    twntype: Mapped[str | None] = mapped_column(String(10), nullable=True)
    datecreate: Mapped[object | None] = mapped_column(Date, nullable=True)
    datemodifi: Mapped[object | None] = mapped_column(Date, nullable=True)
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fips_c: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # geoalchemy2 auto-creates a GIST index for Geometry columns
    geom: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=True
    )

    __table_args__ = (
        # Non-spatial indexes only — GIST is managed by geoalchemy2
        Index("idx_plss_twn_lndkey", "lndkey"),
        Index("idx_plss_twn_state", "state"),
        Index("idx_plss_twn_state_town_range", "state", "town", "twndir", "range_", "rngdir"),
    )

    def __repr__(self) -> str:
        return f"<PLSSTownship {self.label} {self.state}>"


class PLSSSection(Base):
    __tablename__ = "plss_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lndkey: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sectn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    secfrt: Mapped[str | None] = mapped_column(String(10), nullable=True)
    secdup: Mapped[str | None] = mapped_column(String(10), nullable=True)
    sectionkey: Mapped[str | None] = mapped_column(String(50), nullable=True)
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mtrs: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mc_density: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fips_c: Mapped[str | None] = mapped_column(String(100), nullable=True)
    geom: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=True
    )

    __table_args__ = (
        Index("idx_plss_sec_mtrs", "mtrs"),
        Index("idx_plss_sec_lndkey", "lndkey"),
        Index("idx_plss_sec_fips", "fips_c"),
    )

    def __repr__(self) -> str:
        return f"<PLSSSection {self.mtrs}>"
