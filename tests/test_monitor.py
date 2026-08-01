"""Tests for the monitor module."""

from clustertool import monitor


def test_parse_sample():
    raw = "85 40.0 90 55.5 30.2 62.1 100.5 200.0 N/A N/A 4"
    gpus, cpu, mem, net = monitor.parse_sample(raw)
    assert gpus == [("85", "40.0"), ("90", "55.5")]
    assert cpu == "30.2"
    assert mem == "62.1"
    assert net == ["100.5", "200.0", "N/A", "N/A"]


def test_parse_sample_reads_any_number_of_ports():
    """A node with one HCA and a node with eight both have to parse."""
    one = monitor.parse_sample("85 40.0 30.2 62.1 100.5 1")
    assert one == ([("85", "40.0")], "30.2", "62.1", ["100.5"])
    eight = monitor.parse_sample("85 40.0 30.2 62.1 " + " ".join(["1.0"] * 8) + " 8")
    assert eight[3] == ["1.0"] * 8
    assert eight[0] == [("85", "40.0")]


def test_parse_sample_with_no_infiniband():
    """An Ethernet-only node reports zero ports rather than four N/A columns."""
    assert monitor.parse_sample("85 40.0 30.2 62.1 0") == ([("85", "40.0")], "30.2", "62.1", [])


def test_port_count_takes_the_widest_host():
    """The table is drawn once, so its column count has to hold the busiest node."""
    assert monitor._port_count(["85 40.0 30.2 62.1 1.0 1", "85 40.0 30.2 62.1 1.0 2.0 2"]) == 2
    assert monitor._port_count(["", "garbage"]) == 0


def test_parse_sample_empty():
    assert monitor.parse_sample("") is None


def test_parse_sample_without_a_port_count():
    """A line from an older sampler has no trailing count and cannot be trusted."""
    assert monitor.parse_sample("85 40.0 30.2 62.1 100.5 N/A") is None


def test_colorize_thresholds():
    assert monitor._GREEN in monitor._colorize("10", 50, 80)
    assert monitor._YELLOW in monitor._colorize("60", 50, 80)
    assert monitor._RED in monitor._colorize("90", 50, 80)
    assert monitor._colorize("N/A", 50, 80) == "N/A"
