"""Test configuration for the samsung_frame_art test suite.

The pip distribution of Home Assistant does not ship the built frontend
(the ``hass_frontend`` package). The frontend component is only needed here so
panels can be registered, so we provide a minimal stub whose static root is an
empty temporary directory.

The ``hass_config_dir`` override and the state purge live here (conftest
level) so they apply to every test module.
"""

import pathlib
import shutil
import sys
import tempfile
import types

import pytest

if "hass_frontend" not in sys.modules:
    _stub_dir = pathlib.Path(tempfile.mkdtemp(prefix="hass_frontend_stub_"))
    (_stub_dir / "static").mkdir(parents=True, exist_ok=True)
    _stub = types.ModuleType("hass_frontend")
    _stub.where = lambda: _stub_dir  # type: ignore[attr-defined, return-value]
    _stub.__file__ = str(_stub_dir / "__init__.py")
    sys.modules["hass_frontend"] = _stub


@pytest.fixture
def hass_config_dir(hass_tmp_config_dir) -> str:
    """Every test gets its own config directory (overrides the plugin default)."""
    return hass_tmp_config_dir


@pytest.fixture(autouse=True)
def _purge_integration_state(hass_config_dir):
    """Remove integration state so tests never observe another test's data.

    Belt and braces: the per-test config directory should already be clean,
    but if the config dir is ever shared (fixture override not applied), this
    keeps tests deterministic.
    """
    root = pathlib.Path(hass_config_dir)
    for name in ("samsung_frame_art", "frame_art"):
        target = root / name
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
    yield
