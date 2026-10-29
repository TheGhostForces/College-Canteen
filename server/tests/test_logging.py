import logging

from app.core.logging import RedactQueryFilter, build_log_config


def test_access_log_drops_query_string():
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        "%s %s %s %s %s",
        ("127.0.0.1", "POST", "/auth/confirm?code=123456&email=private@example.com", "1.1", 422),
        None,
    )
    assert RedactQueryFilter().filter(record)
    assert record.args[2] == "/auth/confirm"
    assert "123456" not in record.getMessage()
    assert "private@example.com" not in record.getMessage()


def test_filter_keeps_normal_records():
    record = logging.LogRecord("canteen", logging.INFO, "", 0, "Started %s", ("scheduler",), None)
    assert RedactQueryFilter().filter(record)
    assert record.getMessage() == "Started scheduler"
    assert build_log_config()["handlers"]["access"]["filters"] == ["redact_query"]
