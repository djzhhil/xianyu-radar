"""Keep the five business areas independent at the Python import level."""

from __future__ import annotations

import ast
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "src" / "xianyu_radar"
FEATURES = {"auth", "discovery", "pool", "scan", "candidates"}


def _feature_imports(path: Path) -> set[str]:
    imports = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        else:
            continue
        for name in names:
            parts = name.split(".")
            if parts[:2] == ["xianyu_radar", "modules"] and len(parts) >= 3:
                imports.add(parts[2])
    return imports


def test_business_modules_do_not_import_each_other() -> None:
    for feature in FEATURES:
        for path in (SOURCE / "modules" / feature).rglob("*.py"):
            other_features = (_feature_imports(path) & FEATURES) - {feature}
            assert not other_features, f"{path} imports {sorted(other_features)}"


def test_business_api_routes_enter_their_own_feature() -> None:
    routes = {
        "auth": "auth",
        "discover": "discovery",
        "pool": "pool",
        "scan": "scan",
        "events": "scan",
        "candidates": "candidates",
    }
    for route, feature in routes.items():
        path = SOURCE / "entrypoints" / "api" / "routes" / f"{route}.py"
        assert _feature_imports(path) == {feature}, path
