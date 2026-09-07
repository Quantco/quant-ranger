from pathlib import Path
from zipfile import ZipFile

import pytest


def test_built_wheel_contains_frontend() -> None:
    wheels = list(Path("dist").glob("quant_ranger-*.whl"))
    if not wheels:
        pytest.skip("wheel has not been built")
    assert len(wheels) == 1

    with ZipFile(wheels[0]) as wheel:
        files = set(wheel.namelist())

    frontend = "quant_ranger/_frontend/"
    assert f"{frontend}index.html" in files
    assert any(name.startswith(f"{frontend}assets/favicon-") for name in files)
    assert any(
        name.startswith(f"{frontend}assets/") and name.endswith(".css")
        for name in files
    )
    assert any(
        name.startswith(f"{frontend}assets/") and name.endswith(".js") for name in files
    )
