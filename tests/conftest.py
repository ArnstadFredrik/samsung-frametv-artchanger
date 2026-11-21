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


@pytest.fixture(autouse=True)
def _purge_integration_state(request):
    """Remove integration state so tests never observe another test's data.

    Newer pytest-homeassistant-custom-component versions serve every test from
    the shared ``testing_config`` directory regardless of ``hass_config_dir``
    overrides, so we purge the integration's directories after Home Assistant
    is up and before the test body runs.
    """
    if "hass" not in request.fixturenames:
        yield
        return

    hass = request.getfixturevalue("hass")
    root = pathlib.Path(hass.config.config_dir)
    for name in ("samsung_frame_art", "frame_art"):
        target = root / name
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
    yield
