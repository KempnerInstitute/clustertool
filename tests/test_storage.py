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
        "command: df -h /n/home14/alice\n"
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


def test_parse_quota_row_takes_the_record_with_the_most_usage():
    """The tool prints a block per record; the unused one must not win by order."""
    out = (
        "Disk quotas for grp mallet_lab (gid 402716):\n"
        "Filesystem\tused\tquota\tfiles\tquota\n"
        "/n/holylabs\t0.0B\t4.0Ti\t3\t10000000\n"
        "Disk quotas for grp mallet_lab (gid 402716):\n"
        "Filesystem\tused\tquota\tfiles\tquota\n"
        "/n/holylabs\t42.0Ti\t100.0Ti\t3225130\t100000000\n"
    )
    assert storage.parse_quota_row(out) == ("42.0Ti", "100.0Ti", "42%", "3%")


def test_parse_quota_row_rejoins_a_wrapped_mount_point():
    """lfs quota puts a long mount point on its own line, leaving the numbers below."""
    out = (
        "     Filesystem    used   quota   limit   grace   files   quota   limit   grace\n"
        "/n/holylfs06/LABS\n"
        "                 45.27T     75T     75T       - 16117322  55574528 55574528       -\n"
    )
    assert storage.parse_quota_row(out) == ("45.27T", "75T", "60%", "29%")


def test_to_bytes_handles_lower_case_and_large_units():
    assert storage._to_bytes("20k") == 20 * 1024
    assert storage._to_bytes("1.5t") == 1.5 * 1024**4
    assert storage._to_bytes("1.0Ei") == 1024**6
    assert storage._to_bytes("2.0Y") == 2 * 1024**8


def test_parse_quota_row_unreadable_file_count_is_not_zero_percent():
    """A suffixed count must read as unknown, not as no files used."""
    out = "/n/netscratch 1.0Ti 50.0Ti 3099k 100000000\n"
    assert storage.parse_quota_row(out) == ("1.0Ti", "50.0Ti", "2%", "-")


def test_data_rows_rejoins_a_wrapped_mount_point():
    """lfs puts the mount point on its own line once it outgrows the column."""
    out = "/n/very/long/path\n        45.31T 75T 75T - 16119595 55574528 55574528 -\n"
    assert storage._data_rows(out) == [
        ["/n/very/long/path", "45.31T", "75T", "75T", "-", "16119595", "55574528", "55574528", "-"]
    ]


def test_data_rows_does_not_join_a_note_to_a_wrapped_mount_point():
    """lfs prints notes of its own between rows, and joining one would invent a row."""
    out = "/n/very/long/path\nuid 1 is using default block quota setting\n"
    assert storage._data_rows(out) == []


def test_data_rows_keeps_a_value_marked_over_quota():
    """lfs marks a value that is over its quota with a trailing star."""
    out = "/n/very/long/path\n        45.31T* 75T 75T none 1 2 3 -\n"
    assert storage._data_rows(out)[0][1] == "45.31T*"


def test_inode_count_over_quota_is_still_a_percentage():
    """lfs stars the used cell of the inode group too, per man lfs-quota."""
    row = "   /n/holylfs06  4.101T*  4T  4T 6d23h 3508976* 2936012 2936012 6d23h"
    assert storage.parse_quota_row(row) == ("4.101T*", "4T", "103%", "120%")
