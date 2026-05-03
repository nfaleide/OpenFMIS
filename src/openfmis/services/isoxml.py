"""ISOXML (ISO 11783-10) parser and importer.

Parses ISOXML TaskData documents containing field boundaries (partfields),
treatment zones, and task (prescription) data.  Supports importing into
OpenFMIS as Fields and CropYear/Prescription records.

Reference: ISO 11783 Part 10 — Task controller and management information
system data interchange.
"""

from __future__ import annotations

import io
import logging
import zipfile
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree as ET

from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry import mapping as shapely_mapping

from openfmis.exceptions import ValidationError

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ISOPartfield:
    """Parsed Partfield (field boundary) from ISOXML."""

    id: str  # PFD-nnn
    designator: str
    area: float  # m²
    polygons: list[dict[str, Any]]  # GeoJSON geometries
    customer_ref: str | None = None
    farm_ref: str | None = None


@dataclass
class ISOTreatmentZone:
    """Parsed TreatmentZone from ISOXML."""

    code: int
    designator: str
    variables: dict[str, float]  # DDI hex → value
    polygons: list[dict[str, Any]]  # GeoJSON geometries


@dataclass
class ISOTask:
    """Parsed Task element from ISOXML."""

    id: str  # TSK-nnn
    designator: str
    status: int  # 1=planned, 2=running, 4=completed
    partfield_ref: str | None = None
    treatment_zones: list[ISOTreatmentZone] = field(default_factory=list)


@dataclass
class ISOProduct:
    """Parsed Product element."""

    id: str  # PDT-nnn
    designator: str


@dataclass
class ISOCustomer:
    """Parsed Customer element."""

    id: str  # CTR-nnn
    last_name: str
    first_name: str = ""


@dataclass
class ISOFarm:
    """Parsed Farm element."""

    id: str  # FRM-nnn
    designator: str
    customer_ref: str | None = None


@dataclass
class ISOXMLData:
    """Complete parsed ISOXML document."""

    customers: list[ISOCustomer] = field(default_factory=list)
    farms: list[ISOFarm] = field(default_factory=list)
    partfields: list[ISOPartfield] = field(default_factory=list)
    products: list[ISOProduct] = field(default_factory=list)
    tasks: list[ISOTask] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_isoxml(content: bytes | str) -> ISOXMLData:
    """Parse an ISOXML TaskData document.

    Accepts either raw XML bytes/string or a ZIP archive containing
    TASKDATA.XML.

    Args:
        content: XML bytes/string or ZIP bytes.

    Returns:
        ISOXMLData with parsed elements.

    Raises:
        ValidationError: If the content cannot be parsed.
    """
    if isinstance(content, str):
        content = content.encode("utf-8")

    # Check if it's a ZIP (ISOXML can be packaged as ZIP with TASKDATA.XML)
    if zipfile.is_zipfile(io.BytesIO(content)):
        content = _extract_taskdata_xml(content)

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValidationError(f"Invalid ISOXML: {exc}") from exc

    if root.tag != "ISO11783_TaskData":
        raise ValidationError(f"Expected ISO11783_TaskData root element, got '{root.tag}'")

    result = ISOXMLData()

    # Parse customers (CTR)
    for elem in root.findall("CTR"):
        result.customers.append(
            ISOCustomer(
                id=elem.get("A", ""),
                last_name=elem.get("B", ""),
                first_name=elem.get("C", ""),
            )
        )

    # Parse farms (FRM)
    for elem in root.findall("FRM"):
        result.farms.append(
            ISOFarm(
                id=elem.get("A", ""),
                designator=elem.get("B", ""),
                customer_ref=elem.get("I"),
            )
        )

    # Parse products (PDT)
    for elem in root.findall("PDT"):
        result.products.append(ISOProduct(id=elem.get("A", ""), designator=elem.get("B", "")))

    # Parse partfields (PFD)
    for elem in root.findall("PFD"):
        pf = _parse_partfield(elem, result)
        if pf is not None:
            result.partfields.append(pf)

    # Parse tasks (TSK)
    for elem in root.findall("TSK"):
        task = _parse_task(elem, result)
        if task is not None:
            result.tasks.append(task)

    return result


def _extract_taskdata_xml(zip_content: bytes) -> bytes:
    """Extract TASKDATA.XML from an ISOXML ZIP archive."""
    with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
        # Look for TASKDATA.XML (case-insensitive)
        for name in zf.namelist():
            if name.upper().endswith("TASKDATA.XML"):
                return zf.read(name)
        raise ValidationError("ZIP archive does not contain TASKDATA.XML")


def _parse_partfield(elem: ET.Element, data: ISOXMLData) -> ISOPartfield | None:
    """Parse a PFD (Partfield) element."""
    pfd_id = elem.get("A", "")
    designator = elem.get("C", elem.get("B", ""))
    area_str = elem.get("D", "0")
    customer_ref = elem.get("F")
    farm_ref = elem.get("G")

    try:
        area = float(area_str)
    except ValueError:
        area = 0.0

    polygons = []
    for pln in elem.findall("PLN"):
        geojson = _parse_polygon(pln)
        if geojson is not None:
            polygons.append(geojson)

    if not polygons and not designator:
        data.warnings.append(f"Partfield {pfd_id}: no geometry or name — skipped")
        return None

    return ISOPartfield(
        id=pfd_id,
        designator=designator,
        area=area,
        polygons=polygons,
        customer_ref=customer_ref,
        farm_ref=farm_ref,
    )


def _parse_task(elem: ET.Element, data: ISOXMLData) -> ISOTask | None:
    """Parse a TSK (Task) element."""
    tsk_id = elem.get("A", "")
    designator = elem.get("B", "")
    status_str = elem.get("G", "1")

    try:
        status = int(status_str)
    except ValueError:
        status = 1

    partfield_ref = elem.get("E")

    zones: list[ISOTreatmentZone] = []
    for tzn in elem.findall("TZN"):
        zone = _parse_treatment_zone(tzn)
        if zone is not None:
            zones.append(zone)

    return ISOTask(
        id=tsk_id,
        designator=designator,
        status=status,
        partfield_ref=partfield_ref,
        treatment_zones=zones,
    )


def _parse_treatment_zone(elem: ET.Element) -> ISOTreatmentZone | None:
    """Parse a TZN (TreatmentZone) element."""
    code_str = elem.get("A", "0")
    designator = elem.get("B", "")

    try:
        code = int(code_str)
    except ValueError:
        code = 0

    # Process data variables (PDV)
    variables: dict[str, float] = {}
    for pdv in elem.findall("PDV"):
        ddi = pdv.get("A", "")
        value_str = pdv.get("B", "0")
        try:
            variables[ddi] = float(value_str)
        except ValueError:
            pass

    # Polygons
    polygons = []
    for pln in elem.findall("PLN"):
        geojson = _parse_polygon(pln)
        if geojson is not None:
            polygons.append(geojson)

    return ISOTreatmentZone(
        code=code,
        designator=designator,
        variables=variables,
        polygons=polygons,
    )


def _parse_polygon(pln: ET.Element) -> dict[str, Any] | None:
    """Parse a PLN (Polygon) element into GeoJSON geometry."""
    rings: list[list[tuple[float, float]]] = []

    for lsg in pln.findall("LSG"):
        coords: list[tuple[float, float]] = []
        for pnt in lsg.findall("PNT"):
            lat_str = pnt.get("C", "")
            lon_str = pnt.get("D", "")
            try:
                lat = float(lat_str)
                lon = float(lon_str)
                coords.append((lon, lat))  # GeoJSON is [lon, lat]
            except ValueError:
                continue

        if len(coords) >= 3:
            # Ensure ring is closed
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            rings.append(coords)

    if not rings:
        return None

    # First ring is exterior, rest are holes
    exterior = rings[0]
    holes = rings[1:] if len(rings) > 1 else []

    poly = Polygon(exterior, holes)
    if not poly.is_valid:
        from shapely.validation import make_valid

        poly = make_valid(poly)

    if poly.is_empty:
        return None

    return shapely_mapping(poly)


# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------


@dataclass
class ISOXMLImportResult:
    """Summary of ISOXML import."""

    fields_created: int = 0
    tasks_imported: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)


def isoxml_to_field_data(
    data: ISOXMLData,
) -> list[dict[str, Any]]:
    """Convert parsed ISOXML partfields to field creation dicts.

    Returns a list of dicts suitable for creating Field records:
    ``{name, geometry_geojson, area_m2, isoxml_id}``.
    """
    fields: list[dict[str, Any]] = []

    for pf in data.partfields:
        if not pf.polygons:
            continue

        # Merge multiple polygons into a MultiPolygon
        if len(pf.polygons) == 1:
            geojson = pf.polygons[0]
        else:
            from shapely.geometry import shape as shapely_shape

            polys = [shapely_shape(g) for g in pf.polygons]
            multi = MultiPolygon(polys)
            geojson = shapely_mapping(multi)

        fields.append(
            {
                "name": pf.designator or f"Field {pf.id}",
                "geometry_geojson": geojson,
                "area_m2": pf.area,
                "isoxml_id": pf.id,
                "customer_ref": pf.customer_ref,
                "farm_ref": pf.farm_ref,
            }
        )

    return fields
