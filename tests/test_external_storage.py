from pathlib import Path

import pytest

from app.storage.external import validate_external_root


def test_formal_storage_rejects_system_disk(tmp_path: Path):
    with pytest.raises(ValueError):
        validate_external_root(tmp_path)
