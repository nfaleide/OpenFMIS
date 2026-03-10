"""BandMathEngine — safe evaluation of user-defined spectral index formulas.

Formulas are strings like "(nir - red) / (nir + red)" parsed via Python's ast
module, restricted to arithmetic operations only. No eval(), no code injection.
"""

from __future__ import annotations

import ast
import operator
from typing import Any

import numpy as np

# Allowed AST node types (arithmetic only)
_SAFE_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Call,  # only for whitelisted functions
)

_SAFE_FUNCTIONS = {
    "abs": np.abs,
    "sqrt": np.sqrt,
    "log": np.log,
    "log10": np.log10,
    "exp": np.exp,
    "min": np.minimum,
    "max": np.maximum,
    "clip": np.clip,
    "where": np.where,
}

_BINOP_MAP = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}

_UNARYOP_MAP = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


class FormulaError(Exception):
    """Raised when a formula is invalid or contains unsafe operations."""

    pass


def validate_formula(formula: str, known_bands: set[str] | None = None) -> list[str]:
    """Validate a formula string. Returns the list of band names referenced.

    Raises FormulaError if the formula is invalid or contains unsafe operations.
    """
    tree = _parse(formula)
    bands = set()
    _collect_names(tree.body, bands)

    if known_bands is not None:
        unknown = bands - known_bands - set(_SAFE_FUNCTIONS.keys())
        if unknown:
            raise FormulaError(f"Unknown band names: {unknown}")

    return sorted(bands - set(_SAFE_FUNCTIONS.keys()))


def extract_required_bands(formula: str) -> list[str]:
    """Extract band names referenced in a formula (no validation against known bands)."""
    tree = _parse(formula)
    bands = set()
    _collect_names(tree.body, bands)
    return sorted(bands - set(_SAFE_FUNCTIONS.keys()))


def evaluate(
    formula: str,
    bands: dict[str, np.ndarray],
    parameters: dict[str, float] | None = None,
) -> np.ndarray:
    """Evaluate a formula against band arrays. Returns the computed index array.

    Parameters (e.g. {"L": 0.5} for SAVI) are injected as additional names.
    Division by zero produces NaN.
    """
    tree = _parse(formula)

    namespace: dict[str, Any] = {}
    for name, arr in bands.items():
        namespace[name] = arr.astype(np.float64)
    if parameters:
        for name, val in parameters.items():
            namespace[name] = np.float64(val)

    return _eval_node(tree.body, namespace)


# ── Builtin index definitions ────────────────────────────────────────────────

BUILTIN_INDICES: list[dict] = [
    # Vegetation
    {
        "slug": "ndvi",
        "display_name": "NDVI",
        "formula": "(nir - red) / (nir + red)",
        "category": "vegetation",
        "description": "Normalized Difference Vegetation Index",
    },
    {
        "slug": "gndvi",
        "display_name": "GNDVI",
        "formula": "(nir - green) / (nir + green)",
        "category": "vegetation",
        "description": "Green NDVI — chlorophyll content",
    },
    {
        "slug": "evi",
        "display_name": "EVI",
        "formula": "2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)",
        "category": "vegetation",
        "description": "Enhanced Vegetation Index",
    },
    {
        "slug": "savi",
        "display_name": "SAVI",
        "formula": "(nir - red) * (1 + L) / (nir + red + L)",
        "category": "vegetation",
        "parameters": {"L": 0.5},
        "description": "Soil Adjusted Vegetation Index",
    },
    {
        "slug": "osavi",
        "display_name": "OSAVI",
        "formula": "(nir - red) / (nir + red + 0.16)",
        "category": "vegetation",
        "description": "Optimized SAVI (L=0.16)",
    },
    {
        "slug": "msavi2",
        "display_name": "MSAVI2",
        "formula": "(2 * nir + 1 - sqrt((2 * nir + 1) ** 2 - 8 * (nir - red))) / 2",
        "category": "vegetation",
        "description": "Modified SAVI v2 — self-adjusting soil factor",
    },
    {
        "slug": "ndre",
        "display_name": "NDRE",
        "formula": "(nir - rededge1) / (nir + rededge1)",
        "category": "vegetation",
        "description": "Normalized Difference Red-Edge — nitrogen status",
    },
    {
        "slug": "vari",
        "display_name": "VARI",
        "formula": "(green - red) / (green + red - blue)",
        "category": "vegetation",
        "description": "Visible Atmospherically Resistant Index",
    },
    {
        "slug": "cigreen",
        "display_name": "CI Green",
        "formula": "(nir / green) - 1",
        "category": "vegetation",
        "description": "Chlorophyll Index Green",
    },
    {
        "slug": "cirededge",
        "display_name": "CI Red-Edge",
        "formula": "(nir / rededge1) - 1",
        "category": "vegetation",
        "description": "Chlorophyll Index Red-Edge",
    },
    {
        "slug": "mcari",
        "display_name": "MCARI",
        "formula": "((rededge1 - red) - 0.2 * (rededge1 - green)) * (rededge1 / red)",
        "category": "vegetation",
        "description": "Modified Chlorophyll Absorption Ratio Index",
    },
    {
        "slug": "tci",
        "display_name": "TCI",
        "formula": "1.2 * (rededge1 - green) - 1.5 * (red - green) * sqrt(rededge1 / red)",
        "category": "vegetation",
        "description": "Triangular Chlorophyll Index",
    },
    {
        "slug": "wdrvi",
        "display_name": "WDRVI",
        "formula": "(0.1 * nir - red) / (0.1 * nir + red)",
        "category": "vegetation",
        "description": "Wide Dynamic Range VI — high-biomass areas",
    },
    {
        "slug": "arvi",
        "display_name": "ARVI",
        "formula": "(nir - (2 * red - blue)) / (nir + (2 * red - blue))",
        "category": "vegetation",
        "description": "Atmospherically Resistant VI",
    },
    {
        "slug": "sipi",
        "display_name": "SIPI",
        "formula": "(nir - blue) / (nir - red)",
        "category": "vegetation",
        "description": "Structure Insensitive Pigment Index",
    },
    {
        "slug": "lai_proxy",
        "display_name": "LAI Proxy",
        "formula": "3.618 * ((2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1))) - 0.118",
        "category": "vegetation",
        "description": "Leaf Area Index proxy from EVI",
    },
    # Straight band passthrough
    {
        "slug": "nir",
        "display_name": "NIR",
        "formula": "nir",
        "category": "band",
        "description": "Straight near-infrared reflectance",
    },
    {
        "slug": "red",
        "display_name": "Red",
        "formula": "red",
        "category": "band",
        "description": "Red band reflectance",
    },
    {
        "slug": "green",
        "display_name": "Green",
        "formula": "green",
        "category": "band",
        "description": "Green band reflectance",
    },
    {
        "slug": "blue",
        "display_name": "Blue",
        "formula": "blue",
        "category": "band",
        "description": "Blue band reflectance",
    },
    {
        "slug": "rededge1",
        "display_name": "Red Edge 1",
        "formula": "rededge1",
        "category": "band",
        "description": "Red Edge Band 5 reflectance",
    },
    # Water / moisture
    {
        "slug": "ndwi",
        "display_name": "NDWI",
        "formula": "(green - nir) / (green + nir)",
        "category": "water",
        "description": "Normalized Difference Water Index",
    },
    {
        "slug": "ndmi",
        "display_name": "NDMI",
        "formula": "(nir - swir16) / (nir + swir16)",
        "category": "water",
        "description": "Normalized Difference Moisture Index",
    },
    # Fire / burn
    {
        "slug": "nbr",
        "display_name": "NBR",
        "formula": "(nir - swir22) / (nir + swir22)",
        "category": "fire",
        "description": "Normalized Burn Ratio",
    },
    # Soil
    {
        "slug": "bsi",
        "display_name": "BSI",
        "formula": "((swir16 + red) - (nir + blue)) / ((swir16 + red) + (nir + blue))",
        "category": "soil",
        "description": "Bare Soil Index",
    },
    # SAR
    {
        "slug": "vv",
        "display_name": "VV Polarization",
        "formula": "vv",
        "category": "sar",
        "description": "VV backscatter (Sentinel-1)",
    },
    {
        "slug": "vh",
        "display_name": "VH Polarization",
        "formula": "vh",
        "category": "sar",
        "description": "VH backscatter (Sentinel-1)",
    },
    {
        "slug": "vv_vh_ratio",
        "display_name": "VV/VH Ratio",
        "formula": "vv / vh",
        "category": "sar",
        "description": "VV to VH polarization ratio",
    },
    {
        "slug": "rvi_sar",
        "display_name": "RVI (SAR)",
        "formula": "(4 * vh) / (vv + vh)",
        "category": "sar",
        "description": "Radar Vegetation Index",
    },
]


# ── Internal AST parsing ─────────────────────────────────────────────────────


def _parse(formula: str) -> ast.Expression:
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"Invalid formula syntax: {exc}")
    _validate_nodes(tree)
    return tree


def _validate_nodes(node: ast.AST) -> None:
    """Recursively check that the AST contains only safe node types."""
    if not isinstance(node, _SAFE_NODES):
        raise FormulaError(
            f"Unsafe operation in formula: {type(node).__name__}. "
            f"Only arithmetic expressions are allowed."
        )
    # For Call nodes, only allow whitelisted function names
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise FormulaError("Only named function calls are allowed")
        if node.func.id not in _SAFE_FUNCTIONS:
            raise FormulaError(
                f"Unknown function '{node.func.id}'. Allowed: {sorted(_SAFE_FUNCTIONS.keys())}"
            )
    for child in ast.iter_child_nodes(node):
        _validate_nodes(child)


def _collect_names(node: ast.AST, names: set[str]) -> None:
    """Collect all Name references in the AST."""
    if isinstance(node, ast.Name):
        names.add(node.id)
    for child in ast.iter_child_nodes(node):
        _collect_names(child, names)


def _eval_node(node: ast.AST, namespace: dict[str, Any]) -> Any:
    """Recursively evaluate an AST node against the namespace."""
    if isinstance(node, ast.Constant):
        return np.float64(node.value)

    if isinstance(node, ast.Name):
        if node.id in namespace:
            return namespace[node.id]
        raise FormulaError(f"Undefined variable: '{node.id}'")

    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, namespace)
        right = _eval_node(node.right, namespace)
        op_func = _BINOP_MAP.get(type(node.op))
        if op_func is None:
            raise FormulaError(f"Unsupported operator: {type(node.op).__name__}")
        if isinstance(node.op, ast.Div):
            # Safe division: zero denominator → NaN
            if isinstance(right, np.ndarray):
                return np.where(right == 0, np.nan, left / right)
            elif right == 0:
                return np.nan
        return op_func(left, right)

    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, namespace)
        op_func = _UNARYOP_MAP.get(type(node.op))
        if op_func is None:
            raise FormulaError(f"Unsupported unary operator: {type(node.op).__name__}")
        return op_func(operand)

    if isinstance(node, ast.Call):
        func = _SAFE_FUNCTIONS[node.func.id]
        args = [_eval_node(arg, namespace) for arg in node.args]
        return func(*args)

    raise FormulaError(f"Cannot evaluate node type: {type(node).__name__}")
