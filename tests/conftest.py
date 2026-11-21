"""Test configuration for the samsung_frame_art test suite.

The pip distribution of Home Assistant does not ship the built frontend
(the ``hass_frontend`` package). The frontend component is only needed here so
panels can be registered, so we provide a minimal stub whose static root is an
empty temporary directory.
"""

import pathlib
import sys
import tempfile
import types

if "hass_frontend" not in sys.modules:
    _stub_dir = pathlib.Path(tempfile.mkdtemp(prefix="hass_frontend_stub_"))
    (_stub_dir / "static").mkdir(parents=True, exist_ok=True)
    _stub = types.ModuleType("hass_frontend")
    _stub.where = lambda: _stub_dir  # type: ignore[attr-defined, return-value]
    _stub.__file__ = str(_stub_dir / "__init__.py")
    sys.modules["hass_frontend"] = _stub
