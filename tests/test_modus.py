"""Modus XML soil-test parser tests — parse_modus_xml + modus_to_soil_event_data."""

import pytest

from openfmis.services.modus import (
    ModusParseError,
    ModusParseResult,
    modus_to_soil_event_data,
    parse_modus_xml,
)

# ── Sample XML fixtures ──────────────────────────────────────────────────


SIMPLE_MODUS_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<ModusResult>
  <LabName>Ward Labs</LabName>
  <ReportDate>2024-05-15</ReportDate>
  <Samples>
    <Sample>
      <SampleID>S001</SampleID>
      <Depth>6</Depth>
      <Results>
        <Result>
          <AnalyteName>pH</AnalyteName>
          <Value>6.8</Value>
        </Result>
        <Result>
          <AnalyteName>P</AnalyteName>
          <Value>42</Value>
          <Unit>ppm</Unit>
        </Result>
        <Result>
          <AnalyteName>K</AnalyteName>
          <Value>280</Value>
          <Unit>ppm</Unit>
        </Result>
        <Result>
          <AnalyteName>OM</AnalyteName>
          <Value>3.2</Value>
          <Unit>%</Unit>
        </Result>
      </Results>
    </Sample>
  </Samples>
</ModusResult>
"""

NAMESPACED_MODUS_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<ModusResult xmlns="http://www.aggateway.org/Modus">
  <LabName>AgSource</LabName>
  <ReportDate>2024-06-01T10:30:00</ReportDate>
  <Samples>
    <Sample>
      <SampleID>NS-001</SampleID>
      <Depth>8</Depth>
      <DepthUnit>inches</DepthUnit>
      <Latitude>40.82</Latitude>
      <Longitude>-96.85</Longitude>
      <Results>
        <Result>
          <AnalyteName>pH</AnalyteName>
          <Value>7.1</Value>
        </Result>
        <Result>
          <AnalyteName>PHOSPHORUS</AnalyteName>
          <Value>35</Value>
          <Unit>ppm</Unit>
        </Result>
        <Result>
          <AnalyteName>CEC</AnalyteName>
          <Value>18.5</Value>
          <Unit>meq/100g</Unit>
        </Result>
      </Results>
    </Sample>
  </Samples>
</ModusResult>
"""

MULTI_SAMPLE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<ModusResult>
  <LabName>Midwest Labs</LabName>
  <ReportDate>2024-07-10</ReportDate>
  <Samples>
    <Sample>
      <SampleID>A1</SampleID>
      <Depth>0-6</Depth>
      <Results>
        <Result>
          <AnalyteName>pH</AnalyteName>
          <Value>6.5</Value>
        </Result>
        <Result>
          <AnalyteName>P</AnalyteName>
          <Value>28</Value>
          <Unit>ppm</Unit>
        </Result>
      </Results>
    </Sample>
    <Sample>
      <SampleID>A2</SampleID>
      <Depth>6-24</Depth>
      <Results>
        <Result>
          <AnalyteName>NO3</AnalyteName>
          <Value>12</Value>
          <Unit>ppm</Unit>
        </Result>
        <Result>
          <AnalyteName>SO4</AnalyteName>
          <Value>8</Value>
          <Unit>ppm</Unit>
        </Result>
      </Results>
    </Sample>
  </Samples>
</ModusResult>
"""

BELOW_DETECTION_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<ModusResult>
  <LabName>TestLab</LabName>
  <ReportDate>2024-01-01</ReportDate>
  <Samples>
    <Sample>
      <SampleID>BDL-1</SampleID>
      <Results>
        <Result>
          <AnalyteName>Zn</AnalyteName>
          <Value>&lt;0.5</Value>
          <Unit>ppm</Unit>
        </Result>
        <Result>
          <AnalyteName>B</AnalyteName>
          <Value>0.8</Value>
          <Unit>ppm</Unit>
        </Result>
      </Results>
    </Sample>
  </Samples>
</ModusResult>
"""

EMPTY_SAMPLE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<ModusResult>
  <LabName>EmptyLab</LabName>
  <Samples>
    <Sample>
      <SampleID>EMPTY</SampleID>
      <Results/>
    </Sample>
  </Samples>
</ModusResult>
"""

ALT_STRUCTURE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<ModusResult>
  <Laboratory>AltLab</Laboratory>
  <DateReceived>03/15/2024</DateReceived>
  <SampleList>
    <Sample>
      <SampleNumber>ALT-1</SampleNumber>
      <SampleDepth>6</SampleDepth>
      <DateSampled>2024-03-10</DateSampled>
      <AnalyteResults>
        <Analyte>
          <Name>POTASSIUM</Name>
          <Value>310</Value>
          <Units>ppm</Units>
        </Analyte>
        <Analyte>
          <Name>ORGANIC MATTER</Name>
          <Value>4.1</Value>
          <Units>percent</Units>
        </Analyte>
      </AnalyteResults>
    </Sample>
  </SampleList>
</ModusResult>
"""

NON_NUMERIC_VALUE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<ModusResult>
  <Samples>
    <Sample>
      <SampleID>BAD</SampleID>
      <Results>
        <Result>
          <AnalyteName>pH</AnalyteName>
          <Value>not-a-number</Value>
        </Result>
        <Result>
          <AnalyteName>P</AnalyteName>
          <Value>25</Value>
          <Unit>ppm</Unit>
        </Result>
      </Results>
    </Sample>
  </Samples>
</ModusResult>
"""


# ── Parser tests ─────────────────────────────────────────────────────────


def test_parse_simple_modus():
    result = parse_modus_xml(SIMPLE_MODUS_XML)
    assert result.lab_name == "Ward Labs"
    assert result.report_date is not None
    assert result.report_date.year == 2024
    assert result.report_date.month == 5
    assert result.sample_count == 1

    sample = result.samples[0]
    assert sample["sample_id"] == "S001"
    assert sample["depth"] == 6.0
    assert len(sample["analytes"]) == 4

    params = {a["parameter"] for a in sample["analytes"]}
    assert params == {"pH", "P", "K", "OM"}


def test_parse_namespaced_modus():
    result = parse_modus_xml(NAMESPACED_MODUS_XML)
    assert result.lab_name == "AgSource"
    assert result.sample_count == 1

    sample = result.samples[0]
    assert sample["sample_id"] == "NS-001"
    assert sample["depth"] == 8.0
    assert sample["depth_unit"] == "inches"
    assert sample["latitude"] == pytest.approx(40.82)
    assert sample["longitude"] == pytest.approx(-96.85)

    params = {a["parameter"] for a in sample["analytes"]}
    assert "pH" in params
    assert "P" in params  # PHOSPHORUS → P
    assert "CEC" in params


def test_parse_multi_sample():
    result = parse_modus_xml(MULTI_SAMPLE_XML)
    assert result.lab_name == "Midwest Labs"
    assert result.sample_count == 2

    s1, s2 = result.samples
    assert s1["sample_id"] == "A1"
    assert s1["depth"] == pytest.approx(3.0)  # midpoint of 0-6
    assert s2["sample_id"] == "A2"
    assert s2["depth"] == pytest.approx(15.0)  # midpoint of 6-24


def test_parse_below_detection_limit():
    result = parse_modus_xml(BELOW_DETECTION_XML)
    assert result.sample_count == 1
    analytes = result.samples[0]["analytes"]
    zn = next(a for a in analytes if a["parameter"] == "Zn")
    assert zn["value"] == pytest.approx(0.5)  # "<0.5" → 0.5


def test_parse_empty_sample_warns():
    result = parse_modus_xml(EMPTY_SAMPLE_XML)
    assert result.sample_count == 0
    assert any("no analyte results" in w.lower() for w in result.warnings)


def test_parse_alt_structure():
    """Tests alternative element names: Laboratory, SampleList, Analyte, etc."""
    result = parse_modus_xml(ALT_STRUCTURE_XML)
    assert result.lab_name == "AltLab"
    assert result.report_date is not None
    assert result.report_date.month == 3
    assert result.sample_count == 1

    sample = result.samples[0]
    assert sample["sample_id"] == "ALT-1"
    assert sample["date"] is not None

    params = {a["parameter"]: a for a in sample["analytes"]}
    assert params["K"]["value"] == pytest.approx(310.0)
    assert params["OM"]["value"] == pytest.approx(4.1)
    assert params["OM"]["unit"] == "%"  # "percent" → "%"


def test_parse_non_numeric_warns():
    result = parse_modus_xml(NON_NUMERIC_VALUE_XML)
    assert result.sample_count == 1
    assert any("non-numeric" in w.lower() for w in result.warnings)
    # Should still parse the valid analyte
    assert len(result.samples[0]["analytes"]) == 1
    assert result.samples[0]["analytes"][0]["parameter"] == "P"


def test_parse_invalid_xml():
    with pytest.raises(ModusParseError, match="Invalid XML"):
        parse_modus_xml("<not-valid>xml<<<")


def test_parse_no_samples_warns():
    xml = '<?xml version="1.0"?><ModusResult><LabName>X</LabName></ModusResult>'
    result = parse_modus_xml(xml)
    assert result.sample_count == 0
    assert any("no <sample>" in w.lower() for w in result.warnings)


def test_parse_bytes_input():
    result = parse_modus_xml(SIMPLE_MODUS_XML.encode("utf-8"))
    assert result.sample_count == 1


def test_analyte_normalization():
    """Verify various analyte code aliases map to canonical names."""
    xml = """\
    <ModusResult><Samples><Sample><SampleID>N1</SampleID><Results>
      <Result><AnalyteName>ZINC</AnalyteName><Value>1.2</Value></Result>
      <Result><AnalyteName>MANGANESE</AnalyteName><Value>10</Value></Result>
      <Result><AnalyteName>IRON</AnalyteName><Value>25</Value></Result>
      <Result><AnalyteName>COPPER</AnalyteName><Value>0.8</Value></Result>
      <Result><AnalyteName>BORON</AnalyteName><Value>0.5</Value></Result>
      <Result><AnalyteName>CALCIUM</AnalyteName><Value>2000</Value></Result>
      <Result><AnalyteName>MAGNESIUM</AnalyteName><Value>300</Value></Result>
      <Result><AnalyteName>SODIUM</AnalyteName><Value>15</Value></Result>
      <Result><AnalyteName>BUFFER PH</AnalyteName><Value>6.6</Value></Result>
    </Results></Sample></Samples></ModusResult>
    """
    result = parse_modus_xml(xml)
    params = {a["parameter"] for a in result.samples[0]["analytes"]}
    assert params == {"Zn", "Mn", "Fe", "Cu", "B", "Ca", "Mg", "Na", "Buffer pH"}


def test_unit_normalization():
    """Verify unit aliases normalize correctly."""
    xml = """\
    <ModusResult><Samples><Sample><SampleID>U1</SampleID><Results>
      <Result><AnalyteName>P</AnalyteName><Value>30</Value><Unit>mg/kg</Unit></Result>
      <Result><AnalyteName>K</AnalyteName><Value>200</Value><Unit>PPM</Unit></Result>
      <Result><AnalyteName>CEC</AnalyteName><Value>15</Value><Unit>cmol/kg</Unit></Result>
    </Results></Sample></Samples></ModusResult>
    """
    result = parse_modus_xml(xml)
    units = {a["parameter"]: a["unit"] for a in result.samples[0]["analytes"]}
    assert units["P"] == "ppm"  # mg/kg → ppm
    assert units["K"] == "ppm"  # PPM → ppm
    assert units["CEC"] == "meq/100g"  # cmol/kg → meq/100g


# ── Conversion tests ─────────────────────────────────────────────────────


def test_modus_to_soil_event_data_basic():
    result = parse_modus_xml(SIMPLE_MODUS_XML)
    events = modus_to_soil_event_data(result)
    assert len(events) == 1

    evt = events[0]
    assert evt.lab_name == "Ward Labs"
    assert evt.sample_date is not None
    assert len(evt.test_entries) == 4

    ph = next(e for e in evt.test_entries if e.parameter == "pH")
    assert ph.value == pytest.approx(6.8)
    assert ph.depth == pytest.approx(6.0)


def test_modus_to_soil_event_data_multi():
    result = parse_modus_xml(MULTI_SAMPLE_XML)
    events = modus_to_soil_event_data(result)
    assert len(events) == 2
    assert events[0].test_entries[0].depth == pytest.approx(3.0)
    assert events[1].test_entries[0].depth == pytest.approx(15.0)


def test_modus_to_soil_event_data_empty():
    result = ModusParseResult()
    events = modus_to_soil_event_data(result)
    assert events == []


# ── API-level tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_import_modus(
    client,
    auth_headers,
    test_field,
    test_group,
):
    """POST /api/v1/import/modus with valid XML creates soil test events."""
    import io

    resp = await client.post(
        "/api/v1/import/modus",
        headers=auth_headers,
        data={
            "field_id": str(test_field.id),
            "crop_year": "2024",
        },
        files={"file": ("soil_results.xml", io.BytesIO(SIMPLE_MODUS_XML.encode()), "text/xml")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["events_created"] == 1
    assert data["samples_parsed"] == 1
    assert data["warnings"] == []


@pytest.mark.asyncio
async def test_api_import_modus_invalid_xml(
    client,
    auth_headers,
    test_field,
):
    """POST /api/v1/import/modus with invalid XML returns 422."""
    import io

    resp = await client.post(
        "/api/v1/import/modus",
        headers=auth_headers,
        data={
            "field_id": str(test_field.id),
            "crop_year": "2024",
        },
        files={"file": ("bad.xml", io.BytesIO(b"<not>valid<<<"), "text/xml")},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_api_import_modus_multi_sample(
    client,
    auth_headers,
    test_field,
):
    """Multi-sample XML creates multiple events."""
    import io

    resp = await client.post(
        "/api/v1/import/modus",
        headers=auth_headers,
        data={
            "field_id": str(test_field.id),
            "crop_year": "2024",
        },
        files={"file": ("multi.xml", io.BytesIO(MULTI_SAMPLE_XML.encode()), "text/xml")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["events_created"] == 2
    assert data["samples_parsed"] == 2


# ── Modus export tests ──────────────────────────────────────��───────────


def test_generate_modus_submit_basic():
    from openfmis.services.modus import generate_modus_submit

    xml = generate_modus_submit(
        submitter_name="John Doe",
        lab_name="Ward Labs",
        field_name="North 40",
        sample_points=[
            {"sample_id": "S001", "latitude": 40.82, "longitude": -96.85},
            {"sample_id": "S002", "latitude": 40.83, "longitude": -96.86},
        ],
        sample_depth=6.0,
    )
    assert "<?xml version=" in xml
    assert "ModusSubmit" in xml
    assert "Ward Labs" in xml
    assert "John Doe" in xml
    assert "North 40" in xml
    assert "S001" in xml
    assert "S002" in xml
    assert "40.82" in xml
    assert "-96.85" in xml
    assert "<Depth>6.0</Depth>" in xml

    # Should be parseable XML (ModusSubmit isn't ModusResult so no samples)
    parse_modus_xml(xml)


def test_generate_modus_submit_custom_analyses():
    from openfmis.services.modus import generate_modus_submit

    xml = generate_modus_submit(
        submitter_name="Jane",
        lab_name="AgSource",
        field_name="South 80",
        sample_points=[{"sample_id": "T1"}],
        requested_analyses=["pH", "P", "K"],
    )
    assert "pH" in xml
    assert "Phosphorus" in xml
    assert "Potassium" in xml
    # Should NOT have the full default panel
    assert "Organic Matter" not in xml


def test_generate_modus_submit_default_panel():
    from openfmis.services.modus import generate_modus_submit

    xml = generate_modus_submit(
        submitter_name="Test",
        lab_name="Lab",
        field_name="Field",
        sample_points=[{"sample_id": "X1"}],
    )
    # Default panel includes standard analytes
    assert "Phosphorus" in xml
    assert "Potassium" in xml
    assert "Organic Matter" in xml
    assert "CEC" in xml


def test_generate_modus_submit_no_depth():
    from openfmis.services.modus import generate_modus_submit

    xml = generate_modus_submit(
        submitter_name="Test",
        lab_name="Lab",
        field_name="Field",
        sample_points=[{"sample_id": "X1"}],
    )
    assert "<Depth>" not in xml


def test_generate_modus_submit_no_coordinates():
    from openfmis.services.modus import generate_modus_submit

    xml = generate_modus_submit(
        submitter_name="Test",
        lab_name="Lab",
        field_name="Field",
        sample_points=[{"sample_id": "X1"}],
    )
    assert "<Latitude>" not in xml
    assert "<Longitude>" not in xml


def test_modus_submit_roundtrip():
    """Generate a ModusSubmit, then parse the sample points from it."""
    from openfmis.services.modus import generate_modus_submit

    xml = generate_modus_submit(
        submitter_name="Roundtrip",
        lab_name="Lab",
        field_name="Field",
        sample_points=[
            {"sample_id": "R1", "latitude": 41.0, "longitude": -97.0},
            {"sample_id": "R2", "latitude": 41.1, "longitude": -97.1},
        ],
        sample_depth=8.0,
    )
    # Parse with defusedxml to verify well-formed XML
    from defusedxml import ElementTree

    root = ElementTree.fromstring(xml)
    assert root.tag.endswith("ModusSubmit") or root.tag == "ModusSubmit"

    # Find samples
    ns = ""
    if "{" in root.tag:
        ns = root.tag.split("}")[0] + "}"

    samples = root.findall(f".//{ns}Sample")
    assert len(samples) == 2

    s1_id = samples[0].find(f"{ns}SampleID")
    assert s1_id is not None
    assert s1_id.text == "R1"
