"""Tests for storage command construction."""

from cluster_tools import storage


def test_parse_du_top():
    out = "5000000\t/h/big\n2000000\t/h/med\n1000\t/h/small\n9999999\t/h\n"
    assert storage.parse_du_top(out, "/h", 2) == [(5000000, "/h/big"), (2000000, "/h/med")]


def test_humanize_bytes():
    assert storage.humanize_bytes(0) == "0B"
    assert storage.humanize_bytes(46137344).endswith("M")
    assert storage.humanize_bytes(5 * 1024**3).endswith("G")


def test_quota_cmd_path_only():
    assert storage.quota_cmd("/n/netscratch") == ["quota", "/n/netscratch"]


def test_quota_cmd_group():
    assert storage.quota_cmd("/n/holylfs06", group="kempner_dev") == [
        "quota",
        "-g",
        "kempner_dev",
        "/n/holylfs06",
    ]


def test_quota_cmd_user_verbose():
    assert storage.quota_cmd("/n/holystore01", user="mmsh", verbose=True) == [
        "quota",
        "-u",
        "mmsh",
        "-v",
        "/n/holystore01",
    ]
