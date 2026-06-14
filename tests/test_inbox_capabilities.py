"""Tests de expansión de capacidades para bandeja PM."""

from app.domain.capabilities import (
    QUERY_APPROVE,
    REPORT_APPROVE,
    WORKBENCH_INBOX_PM,
    resolve_capability_keys,
)


def test_inbox_pm_expands_record_read_caps():
    expanded = resolve_capability_keys([WORKBENCH_INBOX_PM])
    assert "record.report.read" in expanded
    assert "record.query.read" in expanded
    assert "record.feature.read" in expanded


def test_query_and_report_ops_imply_read():
    query_expanded = resolve_capability_keys([QUERY_APPROVE])
    assert "record.query.read" in query_expanded
    report_expanded = resolve_capability_keys([REPORT_APPROVE])
    assert "record.report.read" in report_expanded
