from pathlib import Path

from quant_ranger._impl.logger import progress
from quant_ranger._impl.models import RepositoryRef
from quant_ranger._impl.testing import RecordingCheckout, RecordingLogger


def test_recording_logger_records_all_log_levels_separately() -> None:
    logger = RecordingLogger()

    logger.info("info")
    logger.debug("debug")
    logger.warning("warning")
    logger.error("error")

    assert logger.infos == ["info"]
    assert logger.debug_messages == ["debug"]
    assert logger.warnings == ["warning"]
    assert logger.errors == ["error"]


def test_recording_logger_can_capture_progress_output() -> None:
    logger = RecordingLogger(show_progress=True)

    assert list(progress([1, 2], logger=logger, description="Work", total=2)) == [1, 2]
    assert "Work" in logger.stream.getvalue()


def test_recording_checkout_reports_changed_files(tmp_path: Path) -> None:
    checkout = RecordingCheckout(
        tmp_path,
        RepositoryRef(owner="quantco", name="example"),
        changed_files=("file", "nested/other-file"),
    )

    assert checkout.changed_files() == ["file", "nested/other-file"]
    assert checkout.changed_files(staged=True) == ["file", "nested/other-file"]
    assert checkout.changed_files(path="file") == ["file"]
    assert checkout.changed_files(path="nested") == ["nested/other-file"]
    assert checkout.changed_files(path="nested/") == ["nested/other-file"]
    assert checkout.changed_files(path="nest") == []


def test_recording_checkout_can_lock_clean(
    tmp_path: Path,
) -> None:
    checkout = RecordingCheckout(
        tmp_path,
        RepositoryRef(owner="quantco", name="example"),
        clean=True,
        lock_clean=True,
    )
    checkout.add_all()

    assert checkout.is_clean()
