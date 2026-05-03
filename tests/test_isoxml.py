"""ISOXML (ISO 11783-10) parser + import tests."""

import io
import zipfile

import pytest

from openfmis.exceptions import ValidationError
from openfmis.services.isoxml import (
    ISOXMLData,
    isoxml_to_field_data,
    parse_isoxml,
)

# ── Sample ISOXML documents ─────────────────────────────────────────────

MINIMAL_ISOXML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ISO11783_TaskData VersionMajor="4" VersionMinor="0"
  ManagementSoftwareManufacturer="Test"
  ManagementSoftwareVersion="1.0"
  DataTransferOrigin="1">
</ISO11783_TaskData>
"""

ISOXML_WITH_PARTFIELD = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ISO11783_TaskData VersionMajor="4" VersionMinor="0"
  ManagementSoftwareManufacturer="Test"
  ManagementSoftwareVersion="1.0"
  DataTransferOrigin="1">
  <CTR A="CTR-1" B="Smith" C="John"/>
  <FRM A="FRM-1" B="Home Farm" I="CTR-1"/>
  <PFD A="PFD-1" C="North 40" D="161874" F="CTR-1" G="FRM-1">
    <PLN A="1" B="Boundary">
      <LSG A="1">
        <PNT A="2" C="40.80000000" D="-96.80000000"/>
        <PNT A="2" C="40.81000000" D="-96.80000000"/>
        <PNT A="2" C="40.81000000" D="-96.79000000"/>
        <PNT A="2" C="40.80000000" D="-96.79000000"/>
        <PNT A="2" C="40.80000000" D="-96.80000000"/>
      </LSG>
    </PLN>
  </PFD>
</ISO11783_TaskData>
"""

ISOXML_WITH_TASK = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ISO11783_TaskData VersionMajor="4" VersionMinor="0"
  ManagementSoftwareManufacturer="Test"
  ManagementSoftwareVersion="1.0"
  DataTransferOrigin="1">
  <PDT A="PDT-1" B="Urea 46-0-0"/>
  <PFD A="PFD-1" C="North 40" D="161874">
    <PLN A="1" B="Boundary">
      <LSG A="1">
        <PNT A="2" C="40.80000000" D="-96.80000000"/>
        <PNT A="2" C="40.81000000" D="-96.80000000"/>
        <PNT A="2" C="40.81000000" D="-96.79000000"/>
        <PNT A="2" C="40.80000000" D="-96.79000000"/>
        <PNT A="2" C="40.80000000" D="-96.80000000"/>
      </LSG>
    </PLN>
  </PFD>
  <TSK A="TSK-1" B="N Application" E="PFD-1" G="1">
    <TZN A="1" B="Low">
      <PDV A="0071" B="120000" C="PDT-1"/>
      <PLN A="1" B="Low Zone">
        <LSG A="1">
          <PNT A="2" C="40.80000000" D="-96.80000000"/>
          <PNT A="2" C="40.80500000" D="-96.80000000"/>
          <PNT A="2" C="40.80500000" D="-96.79000000"/>
          <PNT A="2" C="40.80000000" D="-96.79000000"/>
          <PNT A="2" C="40.80000000" D="-96.80000000"/>
        </LSG>
      </PLN>
    </TZN>
    <TZN A="2" B="High">
      <PDV A="0071" B="200000" C="PDT-1"/>
    </TZN>
  </TSK>
</ISO11783_TaskData>
"""

ISOXML_MULTI_PARTFIELD = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<ISO11783_TaskData VersionMajor="4" VersionMinor="0"
  ManagementSoftwareManufacturer="Test"
  ManagementSoftwareVersion="1.0"
  DataTransferOrigin="1">
  <PFD A="PFD-1" C="Field A" D="100000">
    <PLN A="1" B="Boundary">
      <LSG A="1">
        <PNT A="2" C="40.80000000" D="-96.80000000"/>
        <PNT A="2" C="40.81000000" D="-96.80000000"/>
        <PNT A="2" C="40.81000000" D="-96.79000000"/>
        <PNT A="2" C="40.80000000" D="-96.79000000"/>
        <PNT A="2" C="40.80000000" D="-96.80000000"/>
      </LSG>
    </PLN>
  </PFD>
  <PFD A="PFD-2" C="Field B" D="80000">
    <PLN A="1" B="Boundary">
      <LSG A="1">
        <PNT A="2" C="40.82000000" D="-96.80000000"/>
        <PNT A="2" C="40.83000000" D="-96.80000000"/>
        <PNT A="2" C="40.83000000" D="-96.79000000"/>
        <PNT A="2" C="40.82000000" D="-96.79000000"/>
        <PNT A="2" C="40.82000000" D="-96.80000000"/>
      </LSG>
    </PLN>
  </PFD>
</ISO11783_TaskData>
"""


# ── Parser tests ─────────────────────────────────────────────────────────


class TestParseISOXML:
    def test_minimal(self):
        data = parse_isoxml(MINIMAL_ISOXML)
        assert isinstance(data, ISOXMLData)
        assert len(data.partfields) == 0
        assert len(data.tasks) == 0

    def test_partfield_with_polygon(self):
        data = parse_isoxml(ISOXML_WITH_PARTFIELD)
        assert len(data.partfields) == 1

        pf = data.partfields[0]
        assert pf.id == "PFD-1"
        assert pf.designator == "North 40"
        assert pf.area == 161874.0
        assert len(pf.polygons) == 1
        assert pf.customer_ref == "CTR-1"
        assert pf.farm_ref == "FRM-1"

    def test_customer_and_farm(self):
        data = parse_isoxml(ISOXML_WITH_PARTFIELD)
        assert len(data.customers) == 1
        assert data.customers[0].last_name == "Smith"
        assert len(data.farms) == 1
        assert data.farms[0].designator == "Home Farm"

    def test_task_with_zones(self):
        data = parse_isoxml(ISOXML_WITH_TASK)
        assert len(data.tasks) == 1

        task = data.tasks[0]
        assert task.id == "TSK-1"
        assert task.designator == "N Application"
        assert task.partfield_ref == "PFD-1"
        assert len(task.treatment_zones) == 2

        z1 = task.treatment_zones[0]
        assert z1.code == 1
        assert z1.designator == "Low"
        assert z1.variables["0071"] == 120000.0
        assert len(z1.polygons) == 1

    def test_product(self):
        data = parse_isoxml(ISOXML_WITH_TASK)
        assert len(data.products) == 1
        assert data.products[0].designator == "Urea 46-0-0"

    def test_multiple_partfields(self):
        data = parse_isoxml(ISOXML_MULTI_PARTFIELD)
        assert len(data.partfields) == 2

    def test_string_input(self):
        data = parse_isoxml(ISOXML_WITH_PARTFIELD.decode("utf-8"))
        assert len(data.partfields) == 1

    def test_zip_input(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("TASKDATA.XML", ISOXML_WITH_PARTFIELD)
        data = parse_isoxml(buf.getvalue())
        assert len(data.partfields) == 1

    def test_zip_missing_taskdata(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("readme.txt", "no taskdata here")
        with pytest.raises(ValidationError, match="TASKDATA.XML"):
            parse_isoxml(buf.getvalue())

    def test_invalid_xml(self):
        with pytest.raises(ValidationError, match="Invalid ISOXML"):
            parse_isoxml(b"<not valid xml")

    def test_wrong_root_element(self):
        with pytest.raises(ValidationError, match="Expected ISO11783"):
            parse_isoxml(b"<Root><Child/></Root>")

    def test_polygon_coordinates(self):
        data = parse_isoxml(ISOXML_WITH_PARTFIELD)
        geojson = data.partfields[0].polygons[0]
        assert geojson["type"] == "Polygon"
        coords = geojson["coordinates"][0]
        # First point should be lon=-96.8, lat=40.8
        assert abs(coords[0][0] - (-96.8)) < 0.001
        assert abs(coords[0][1] - 40.8) < 0.001


# ── Field data conversion ────────────────────────────────────────────────


class TestISOXMLToFieldData:
    def test_basic(self):
        data = parse_isoxml(ISOXML_WITH_PARTFIELD)
        fields = isoxml_to_field_data(data)
        assert len(fields) == 1
        assert fields[0]["name"] == "North 40"
        assert fields[0]["isoxml_id"] == "PFD-1"
        assert fields[0]["geometry_geojson"]["type"] == "Polygon"

    def test_multiple_fields(self):
        data = parse_isoxml(ISOXML_MULTI_PARTFIELD)
        fields = isoxml_to_field_data(data)
        assert len(fields) == 2
        assert fields[0]["name"] == "Field A"
        assert fields[1]["name"] == "Field B"

    def test_area_preserved(self):
        data = parse_isoxml(ISOXML_WITH_PARTFIELD)
        fields = isoxml_to_field_data(data)
        assert fields[0]["area_m2"] == 161874.0

    def test_empty_partfield_skipped(self):
        """Partfields without geometry should be excluded."""
        data = ISOXMLData(
            partfields=[],
        )
        fields = isoxml_to_field_data(data)
        assert len(fields) == 0


# ── API test ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_import_isoxml(client, auth_headers, test_group, test_region):
    resp = await client.post(
        "/api/v1/import/isoxml",
        files={
            "file": (
                "taskdata.xml",
                ISOXML_WITH_PARTFIELD,
                "application/xml",
            )
        },
        data={
            "group_id": str(test_group.id),
            "region_id": str(test_region.id),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["fields_created"] == 1
    assert len(data["field_ids"]) == 1


@pytest.mark.asyncio
async def test_api_import_isoxml_invalid(client, auth_headers, test_group, test_region):
    resp = await client.post(
        "/api/v1/import/isoxml",
        files={
            "file": (
                "bad.xml",
                b"<not valid xml",
                "application/xml",
            )
        },
        data={
            "group_id": str(test_group.id),
            "region_id": str(test_region.id),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422
