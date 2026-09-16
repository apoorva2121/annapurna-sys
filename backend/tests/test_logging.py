"""PII must not reach the logs. Written in M00, before any real phone number exists."""

from __future__ import annotations

import io
import json
import logging

from app.core.logging import JsonFormatter, RedactingFilter, redact_text

PHONE = "9876543210"
EMAIL = "priya@example.com"


def _logger_writing_to_string() -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    # Installed on the handler, exactly as configure_logging does it.
    handler.addFilter(RedactingFilter())
    logger = logging.getLogger("test.redaction")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    return logger, stream


def test_phone_number_in_the_message_is_redacted() -> None:
    logger, stream = _logger_writing_to_string()
    logger.info("customer called from %s", PHONE)
    assert PHONE not in stream.getvalue()
    assert "[redacted]" in stream.getvalue()


def test_sensitive_keys_in_structured_fields_are_redacted() -> None:
    logger, stream = _logger_writing_to_string()
    logger.info(
        "customer.created",
        extra={
            "phone": PHONE,
            "email": EMAIL,
            "password": "hunter2",
            "gstin": "29ABCDE1234F1Z5",
            "customer_id": "cus_123",
        },
    )
    payload = json.loads(stream.getvalue())
    for key in ("phone", "email", "password", "gstin"):
        assert payload[key] == "[redacted]"
    # The identifier is the whole point: log the customer_id, never the phone.
    assert payload["customer_id"] == "cus_123"


def test_pii_nested_in_a_structure_is_redacted() -> None:
    logger, stream = _logger_writing_to_string()
    logger.info("order.placed", extra={"customer": {"phone": PHONE, "note": f"call {EMAIL}"}})
    output = stream.getvalue()
    assert PHONE not in output
    assert EMAIL not in output


def test_indian_phone_formats_are_all_caught() -> None:
    for variant in ("9876543210", "+91 98765 43210", "+919876543210", "98765-43210"):
        assert variant not in redact_text(f"reached them on {variant} today")


def test_a_harmless_number_is_not_mangled() -> None:
    # Over-redaction destroys the logs' usefulness; an order total is not a phone number.
    assert "1240.00" in redact_text("order total 1240.00")
