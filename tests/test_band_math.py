"""Tests for the BandMathEngine — formula parsing, validation, evaluation."""

import numpy as np
import pytest

from openfmis.services.band_math import (
    BUILTIN_INDICES,
    FormulaError,
    evaluate,
    extract_required_bands,
    validate_formula,
)

# ── Formula validation ───────────────────────────────────────────────────────


class TestValidateFormula:
    def test_simple_ndvi(self):
        bands = validate_formula("(nir - red) / (nir + red)")
        assert sorted(bands) == ["nir", "red"]

    def test_single_band(self):
        bands = validate_formula("nir")
        assert bands == ["nir"]

    def test_complex_evi(self):
        bands = validate_formula("2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)")
        assert sorted(bands) == ["blue", "nir", "red"]

    def test_with_function_call(self):
        bands = validate_formula("sqrt((2 * nir + 1) ** 2 - 8 * (nir - red))")
        assert sorted(bands) == ["nir", "red"]

    def test_invalid_syntax(self):
        with pytest.raises(FormulaError, match="Invalid formula syntax"):
            validate_formula("nir + * red")

    def test_unsafe_operation(self):
        with pytest.raises(FormulaError, match="Unsafe operation"):
            validate_formula("[1, 2, 3]")

    def test_unknown_function(self):
        with pytest.raises(FormulaError, match="Unknown function"):
            validate_formula("eval(nir)")

    def test_unknown_band_with_known_set(self):
        with pytest.raises(FormulaError, match="Unknown band"):
            validate_formula("nir - fake", known_bands={"nir", "red"})


class TestExtractRequiredBands:
    def test_extracts_band_names(self):
        bands = extract_required_bands("(vv + vh) / 2")
        assert sorted(bands) == ["vh", "vv"]

    def test_excludes_function_names(self):
        bands = extract_required_bands("sqrt(nir)")
        assert bands == ["nir"]


# ── Formula evaluation ───────────────────────────────────────────────────────


class TestEvaluate:
    def test_ndvi_basic(self):
        bands = {"nir": np.array([0.8, 0.6]), "red": np.array([0.2, 0.3])}
        result = evaluate("(nir - red) / (nir + red)", bands)
        np.testing.assert_allclose(result, [0.6, 0.333333], rtol=1e-4)

    def test_single_band_passthrough(self):
        bands = {"nir": np.array([0.5, 0.7])}
        result = evaluate("nir", bands)
        np.testing.assert_array_equal(result, [0.5, 0.7])

    def test_division_by_zero_returns_nan(self):
        bands = {"nir": np.array([0.0]), "red": np.array([0.0])}
        result = evaluate("(nir - red) / (nir + red)", bands)
        assert np.isnan(result[0])

    def test_with_parameters(self):
        bands = {"nir": np.array([0.8]), "red": np.array([0.2])}
        result = evaluate("(nir - red) * (1 + L) / (nir + red + L)", bands, {"L": 0.5})
        expected = (0.8 - 0.2) * 1.5 / (0.8 + 0.2 + 0.5)
        np.testing.assert_allclose(result, [expected], rtol=1e-6)

    def test_sqrt_function(self):
        bands = {"nir": np.array([4.0])}
        result = evaluate("sqrt(nir)", bands)
        np.testing.assert_allclose(result, [2.0])

    def test_abs_function(self):
        bands = {"nir": np.array([-0.5])}
        result = evaluate("abs(nir)", bands)
        np.testing.assert_allclose(result, [0.5])

    def test_unary_negation(self):
        bands = {"nir": np.array([0.5])}
        result = evaluate("-nir", bands)
        np.testing.assert_allclose(result, [-0.5])

    def test_power_operator(self):
        bands = {"nir": np.array([3.0])}
        result = evaluate("nir ** 2", bands)
        np.testing.assert_allclose(result, [9.0])

    def test_undefined_variable(self):
        bands = {"nir": np.array([0.5])}
        with pytest.raises(FormulaError, match="Undefined variable"):
            evaluate("nir + missing", bands)

    def test_2d_arrays(self):
        bands = {
            "nir": np.array([[0.8, 0.6], [0.4, 0.9]]),
            "red": np.array([[0.2, 0.3], [0.1, 0.1]]),
        }
        result = evaluate("(nir - red) / (nir + red)", bands)
        assert result.shape == (2, 2)
        np.testing.assert_allclose(result[0, 0], 0.6, rtol=1e-4)


# ── Builtin indices ──────────────────────────────────────────────────────────


class TestBuiltinIndices:
    def test_all_builtins_parse(self):
        """Every builtin formula must be valid."""
        for idx in BUILTIN_INDICES:
            bands = validate_formula(idx["formula"])
            assert len(bands) > 0 or idx["formula"] in ("vv", "vh"), (
                f"Builtin {idx['slug']} has no band references"
            )

    def test_all_builtins_have_required_fields(self):
        for idx in BUILTIN_INDICES:
            assert "slug" in idx
            assert "formula" in idx
            assert "category" in idx
            assert "display_name" in idx

    def test_builtin_count(self):
        assert len(BUILTIN_INDICES) >= 25

    def test_categories_present(self):
        categories = {idx["category"] for idx in BUILTIN_INDICES}
        assert "vegetation" in categories
        assert "water" in categories
        assert "sar" in categories
        assert "band" in categories
