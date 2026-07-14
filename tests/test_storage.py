"""Tests for storage command construction."""

from cluster_tools import storage


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
