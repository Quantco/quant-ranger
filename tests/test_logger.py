from io import StringIO

from rich.syntax import Syntax

from quant_ranger._impl.logger import ConsoleLogger, PrefixLogger, progress
from quant_ranger._impl.testing import RecordingLogger


def _output_lines(stream: StringIO) -> list[str]:
    return [line.rstrip() for line in stream.getvalue().splitlines()]


def test_console_logger_writes_plain_messages_to_stream() -> None:
    stream = StringIO()
    logger = ConsoleLogger(stream=stream, force_terminal=False)

    logger.info("[bold]info[/bold]")
    logger.warning("careful")
    logger.error("broken")

    assert _output_lines(stream) == [
        "INFO     [bold]info[/bold]",
        "WARNING  careful",
        "ERROR    broken",
    ]


def test_console_logger_aligns_multiline_messages() -> None:
    stream = StringIO()
    logger = ConsoleLogger(stream=stream, force_terminal=False)

    logger.error("summary\ndetail")
    logger.warning("first\nsecond")
    logger.info("one\ntwo")

    assert _output_lines(stream) == [
        "ERROR    summary",
        "         detail",
        "WARNING  first",
        "         second",
        "INFO     one",
        "         two",
    ]


def test_console_logger_debug_writes_only_when_debug() -> None:
    stream = StringIO()
    logger = ConsoleLogger(stream=stream, force_terminal=False)

    logger.debug("hidden")
    ConsoleLogger(stream=stream, force_terminal=False, debug=True).debug("details")

    assert _output_lines(stream) == ["DEBUG    details"]


def test_console_logger_renders_rich_tracebacks() -> None:
    stream = StringIO()
    logger = PrefixLogger(
        "[repo] ",
        ConsoleLogger(stream=stream, force_terminal=False),
    )

    try:
        raise RuntimeError("boom")
    except RuntimeError as error:
        logger.exception("failure", error)

    output = stream.getvalue()
    assert "ERROR    [repo] failure" in output
    assert "Traceback (most recent call last)" in output
    assert "RuntimeError: boom" in output


def test_console_logger_info_panel_uses_rich_panel() -> None:
    stream = StringIO()
    logger = ConsoleLogger(stream=stream, force_terminal=True)

    logger.info_panel(
        "Pull request diff",
        Syntax("+added", "diff"),
    )

    output = stream.getvalue()
    assert "info: Pull request diff" in output
    assert "+added" in output
    assert "╭" in output


def test_console_logger_progress_flag_tracks_terminal_detection() -> None:
    assert ConsoleLogger(stream=StringIO(), force_terminal=False).show_progress is False
    assert ConsoleLogger(stream=StringIO(), force_terminal=True).show_progress is True


def test_prefix_logger_forwards_messages_and_progress_flag() -> None:
    base_logger = RecordingLogger(show_progress=True)
    logger = PrefixLogger("[repo] ", base_logger)

    logger.info("info")
    logger.info_panel(
        "title",
        Syntax("content", "diff"),
    )
    logger.warning("warning")
    logger.error("error")
    logger.debug("debug")

    assert logger.console is base_logger.console
    assert logger.show_progress is True
    assert base_logger.infos == ["[repo] info"]
    assert base_logger.panels[0][0] == "[repo] title"
    assert base_logger.debug_messages == ["[repo] debug"]
    assert base_logger.warnings == ["[repo] warning"]
    assert base_logger.errors == ["[repo] error"]


def test_prefix_logger_keeps_prefix_separate_from_multiline_message() -> None:
    base_logger = RecordingLogger()
    logger = PrefixLogger("[repo] ", base_logger)

    logger.error("summary\ndetail line one\ndetail line two")
    logger.info("")

    assert base_logger.errors == ["[repo] summary\ndetail line one\ndetail line two"]
    assert base_logger.infos == ["[repo] "]


def test_prefix_logger_combines_nested_prefixes() -> None:
    base_logger = RecordingLogger()
    logger = PrefixLogger("[repo] ", PrefixLogger("[owner] ", base_logger))

    logger.info("message")

    assert base_logger.infos == ["[owner] [repo] message"]


def test_progress_yields_values_without_rich_progress_when_disabled() -> None:
    logger = RecordingLogger(show_progress=False)

    assert list(progress([1, 2, 3], logger=logger, description="Work")) == [1, 2, 3]
    assert logger.stream.getvalue() == ""


def test_progress_yields_values_with_rich_progress_when_enabled() -> None:
    logger = RecordingLogger(show_progress=True)

    assert list(progress([1, 2], logger=logger, description="Work", total=2)) == [1, 2]
    assert "Work" in logger.stream.getvalue()
