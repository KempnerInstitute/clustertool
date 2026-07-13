"""Tests for the monitor module."""

from cluster_tools import monitor


def test_parse_sample():
    raw = "85 40.0 90 55.5 30.2 62.1 100.5 200.0 N/A N/A"
    gpus, cpu, mem, net = monitor.parse_sample(raw)
    assert gpus == [("85", "40.0"), ("90", "55.5")]
    assert cpu == "30.2"
    assert mem == "62.1"
    assert net == ["100.5", "200.0", "N/A", "N/A"]


def test_parse_sample_empty():
    assert monitor.parse_sample("") is None


def test_colorize_thresholds():
    assert monitor._GREEN in monitor._colorize("10", 50, 80)
    assert monitor._YELLOW in monitor._colorize("60", 50, 80)
    assert monitor._RED in monitor._colorize("90", 50, 80)
    assert monitor._colorize("N/A", 50, 80) == "N/A"
