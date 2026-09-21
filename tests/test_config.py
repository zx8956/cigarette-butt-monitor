from app.core.config import load_config


def test_default_config_requires_explicit_external_storage():
    config = load_config()
    assert config.camera.id == "camera01"
    assert config.camera.name_contains == "4K USB Camera"
    assert config.analysis.rotation_degrees == 0
    assert config.capture.segment_minutes == 30
    assert config.long_recording_allowed is False
    assert config.storage.external_data_root is None
