"""Keep all business areas independent at the Python import level."""

from __future__ import annotations

import ast
from importlib.util import resolve_name
from pathlib import Path
import pytest


SOURCE = Path(__file__).resolve().parents[1] / "src" / "xianyu_radar"
FEATURES = {path.name for path in (SOURCE / "modules").iterdir()
            if path.is_dir() and (path / "__init__.py").is_file()}


def _feature_imports(path: Path) -> set[str]:
    imports = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                package = "xianyu_radar." + ".".join(path.parent.relative_to(SOURCE).parts)
                module = resolve_name("." * node.level + module, package)
            names = [module] + [f"{module}.{alias.name}" for alias in node.names]
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


@pytest.mark.parametrize("statement,feature", [
    ("from xianyu_radar.modules import products", "products"),
    ("from ..products import service", "products"),
    ("import xianyu_radar.modules.products.service as detail", "products"),
    ("from . import service", "scan"),
])
def test_feature_import_detection_covers_absolute_and_relative_forms(tmp_path, monkeypatch, statement, feature):
    source = tmp_path / "xianyu_radar"
    path = source / "modules" / "scan" / "example.py"
    path.parent.mkdir(parents=True)
    path.write_text(statement, encoding="utf-8")
    monkeypatch.setitem(_feature_imports.__globals__, "SOURCE", source)
    assert _feature_imports(path) == {feature}


def test_infrastructure_does_not_import_business_modules() -> None:
    for path in (SOURCE / "infrastructure").rglob("*.py"):
        imports = _feature_imports(path) & FEATURES
        assert not imports, f"{path} imports {sorted(imports)}"


def test_business_api_routes_enter_their_own_feature() -> None:
    aliases = {"discover": "discovery", "events": "scan"}
    for path in (SOURCE / "entrypoints" / "api" / "routes").glob("*.py"):
        if path.stem in {"__init__", "status"}:
            continue
        feature = aliases.get(path.stem, path.stem)
        assert feature in FEATURES, f"{path} has no declared feature"
        assert _feature_imports(path) == {feature}, path


@pytest.mark.parametrize("relative_path", [
    "modules/discovery/service.py",
    "modules/discovery/enrichment.py",
    "entrypoints/api/routes/discover.py",
])
def test_discovery_sql_stays_in_repository(relative_path):
    path = SOURCE / relative_path
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = [node.func.attr for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and node.func.attr in {"execute", "executemany", "executescript"}]
    assert not calls, f"{path} contains SQL calls: {calls}"
