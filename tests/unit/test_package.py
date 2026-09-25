"""Smoke test: the package and every module package import cleanly."""

import importlib

import pytest

MODULES = [
    "companion",
    "companion.audio",
    "companion.config",
    "companion.dispatch",
    "companion.extraction",
    "companion.memory",
    "companion.observability",
    "companion.pipeline",
    "companion.providers",
    "companion.safety",
    "companion.scriptwriter",
    "companion.turn_taking",
]


@pytest.mark.parametrize("module_name", MODULES)
def test_module_imports(module_name: str) -> None:
    importlib.import_module(module_name)
