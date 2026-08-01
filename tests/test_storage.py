"""Tests for storage command construction."""

from clustertool import storage


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
    assert storage.quota_cmd("/n/holystore01", user="auser", verbose=True) == [
        "quota",
        "-u",
        "auser",
        "-v",
        "/n/holystore01",
    ]


def test_parse_quota_row_nfs():
    out = "Filesystem Used Quota Files FQuota\n/n/netscratch/kempner_dev 1.5T 10T 1200000 5000000\n"
    assert storage.parse_quota_row(out) == ("1.5T", "10T", "15%", "24%")


def test_parse_quota_row_lustre():
    out = "/n/holylfs06/LABS/kempner_dev 800G 2T 2T none 500000 1000000 1000000 none\n"
    assert storage.parse_quota_row(out) == ("800G", "2T", "39%", "50%")


def test_parse_quota_row_no_cap_is_dash():
    out = "/n/x 500G - 100 -\n"
    assert storage.parse_quota_row(out) == ("500G", "-", "-", "-")


def test_parse_quota_row_none():
    assert storage.parse_quota_row("no filesystem line here\n") is None
    assert storage.parse_quota_row("/short row\n") is None


def test_parse_quota_row_ignores_a_df_table():
    out = (
        "command: df -h /n/home14/mmsh\n"
        "Filesystem Size Used Avail Use% Mounted on\n"
        "/dev/mapper/vg-home 1.8T 1.2T 500G 71% /home\n"
    )
    assert storage.parse_quota_row(out) is None


def test_parse_quota_row_over_quota_asterisk():
    out = "/n/holylfs06/LABS/kempner_dev 2.1T* 2T 2T none 500000 1000000 1000000 none\n"
    assert storage.parse_quota_row(out) == ("2.1T*", "2T", "105%", "50%")


def test_percent_value():
    assert storage.percent_value("90%") == 90.0
    assert storage.percent_value("-") == -1.0


def test_lab_targets_skips_slurm_groups_and_dedups():
    groups = ["kempner_dev", "slurm_group_x", "kempner_dev"]
    roots = ["/n/netscratch", "/n/holylfs06/LABS"]
    targets = storage.lab_targets(groups, roots, is_dir=lambda p: p.endswith("kempner_dev"))
    assert targets == [
        ("/n/netscratch/kempner_dev", "kempner_dev"),
        ("/n/holylfs06/LABS/kempner_dev", "kempner_dev"),
    ]


def test_fleet_targets(tmp_path):
    (tmp_path / "kempner_dev").mkdir()
    (tmp_path / "kempner_eng").mkdir()
    (tmp_path / "other_lab").mkdir()
    (tmp_path / "kempner_file").write_text("x")
    targets = storage.fleet_targets(str(tmp_path), "kempner")
    assert targets == [
        (str(tmp_path / "kempner_dev"), "kempner_dev"),
        (str(tmp_path / "kempner_eng"), "kempner_eng"),
    ]


def test_user_groups(monkeypatch):
    from clustertool import process

    monkeypatch.setattr(process, "run", lambda cmd: "kempner_dev kempner_shared\n")
    assert storage.user_groups("alice") == ["kempner_dev", "kempner_shared"]
