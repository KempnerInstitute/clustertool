"""Tests for storage command construction."""

from cluster_tools import storage


def test_vast_quota_cmd():
    assert storage.vast_quota_cmd("kempner_dev") == ["quota", "/n/netscratch/kempner_dev"]


def test_lustre_quota_cmd():
    assert storage.lustre_quota_cmd("kempner_dev") == [
        "lfs",
        "quota",
        "-hg",
        "kempner_dev",
        "/n/holylfs06",
    ]


def test_lustre_quota_cmd_user():
    assert storage.lustre_quota_cmd("mmsh", "/n/holystore01", user=True) == [
        "lfs",
        "quota",
        "-hu",
        "mmsh",
        "/n/holystore01",
    ]
