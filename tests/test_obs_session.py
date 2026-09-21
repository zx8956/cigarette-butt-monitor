from app.capture.obs_session import storage_ready


def test_local_directory_is_not_accepted_as_external_mount(tmp_path):
    assert not storage_ready(tmp_path)
