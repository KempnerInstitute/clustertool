"""Tests for the fabric (InfiniBand) helpers."""

from cluster_tools import fabric

REAL_TOPO = (
    "\tGPU0\tNIC0\tNIC1\tNIC2\tCPU Affinity\tNUMA Affinity\tGPU NUMA ID\n"
    "GPU0\t X \tNODE\tNODE\tNODE\t1\t0\t\tN/A\n"
    "NIC0\tNODE\t X \tNODE\tNODE\n"
)


def test_quality_score():
    assert fabric.quality_score("NV18") == 10
    assert fabric.quality_score("PIX") == 6
    assert fabric.quality_score("NODE") == 3
    assert fabric.quality_score("SYS") == 1
    assert fabric.quality_score("X") == 0
    assert fabric.quality_score("?") == 0


def test_parse_topo_real_node():
    assert fabric.parse_topo(REAL_TOPO) == {
        "GPU0": {"NIC0": "NODE", "NIC1": "NODE", "NIC2": "NODE"}
    }


def test_parse_topo_multi_gpu_column_alignment():
    raw = (
        "\tGPU0\tGPU1\tNIC0\tNIC1\tCPU Affinity\n"
        "GPU0\t X \tNV18\tPXB\tSYS\t0-47\n"
        "GPU1\tNV18\t X \tSYS\tPXB\t0-47\n"
    )
    assert fabric.parse_topo(raw) == {
        "GPU0": {"NIC0": "PXB", "NIC1": "SYS"},
        "GPU1": {"NIC0": "SYS", "NIC1": "PXB"},
    }


def test_parse_topo_no_nics_or_empty():
    assert fabric.parse_topo("\tGPU0\tGPU1\nGPU0\t X \tNV18\n") == {}
    assert fabric.parse_topo("") == {}


def test_affinity_rows_verdicts():
    matrix = {
        "GPU0": {"NIC0": "PXB", "NIC1": "SYS"},
        "GPU1": {"NIC0": "SYS", "NIC1": "SYS"},
        "GPU2": {"NIC0": "X", "NIC1": "X"},
    }
    verdicts = {row[0]: row[3] for row in fabric.affinity_rows(matrix)}
    assert verdicts == {"GPU0": "OK", "GPU1": "WARN", "GPU2": "FAIL"}


def test_parse_ibdev2netdev():
    out = "mlx5_0 port 1 ==> ib0 (Up)\nmlx5_1 port 1 ==> em1 (Down)\n"
    assert fabric.parse_ibdev2netdev(out) == [
        {"hca": "mlx5_0", "port": 1, "netdev": "ib0", "state": "Up"},
        {"hca": "mlx5_1", "port": 1, "netdev": "em1", "state": "Down"},
    ]


def test_parse_gpu_csv():
    out = "0, NVIDIA A100-SXM4-80GB, 00000000:19:00.0, 41, 71.5, 400, 81920, 1024, 1410, 1593\n"
    gpus = fabric.parse_gpu_csv(out)
    assert gpus[0]["index"] == 0
    assert gpus[0]["name"] == "NVIDIA A100-SXM4-80GB"
    assert gpus[0]["temp_c"] == 41.0
    assert gpus[0]["memory_total_mib"] == 81920
    assert fabric.parse_gpu_csv("short, row\n") == []


def test_read_hcas(tmp_path):
    port_dir = tmp_path / "mlx5_0" / "ports" / "1"
    (port_dir / "counters").mkdir(parents=True)
    (port_dir / "state").write_text("4: ACTIVE\n")
    (port_dir / "rate").write_text("400 Gb/sec (4X NDR)\n")
    (port_dir / "link_layer").write_text("InfiniBand\n")
    (port_dir / "counters" / "symbol_error").write_text("0\n")
    (port_dir / "counters" / "port_rcv_errors").write_text("3\n")
    hcas = fabric.read_hcas(str(tmp_path))
    assert len(hcas) == 1 and hcas[0]["name"] == "mlx5_0"
    port = hcas[0]["ports"][0]
    assert port["port"] == 1
    assert port["state"] == "4: ACTIVE"
    assert port["rate"] == "400 Gb/sec (4X NDR)"
    assert port["counters"] == {"port_rcv_errors": 3, "symbol_error": 0}


def test_read_hcas_missing_root():
    assert fabric.read_hcas("/nonexistent-ib-root-xyz") == []


def _counter_snap(counters):
    return {"ib": {"hcas": [{"name": "mlx5_0", "ports": [{"port": 1, "counters": counters}]}]}}


def test_counter_deltas_flags_error_growth():
    before = _counter_snap({"symbol_error": 0, "port_rcv_data": 100})
    after = _counter_snap({"symbol_error": 5, "port_rcv_data": 999})
    rows, any_error = fabric.counter_deltas(before, after)
    assert any_error is True
    by_counter = {row[1]: row for row in rows}
    assert by_counter["symbol_error"][4] == 5 and by_counter["symbol_error"][5] is True
    assert by_counter["port_rcv_data"][5] is False


def test_counter_deltas_benign_only():
    before = _counter_snap({"symbol_error": 0, "port_rcv_data": 100})
    after = _counter_snap({"symbol_error": 0, "port_rcv_data": 999})
    rows, any_error = fabric.counter_deltas(before, after)
    assert any_error is False
    assert [row[1] for row in rows] == ["port_rcv_data"]


def test_counter_deltas_identical():
    snap = _counter_snap({"symbol_error": 0})
    assert fabric.counter_deltas(snap, snap) == ([], False)


def _verify_snap(gpu_name="A100", rate="200 Gb/sec", driver="575.57.08"):
    return {
        "gpus": [{"index": 0, "name": gpu_name, "pci_bus_id": "00:19.0"}],
        "ib": {
            "hcas": [
                {
                    "name": "mlx5_0",
                    "ports": [
                        {
                            "port": 1,
                            "state": "4: ACTIVE",
                            "phys_state": "5: LinkUp",
                            "rate": rate,
                            "link_layer": "InfiniBand",
                        }
                    ],
                }
            ]
        },
        "ibdev2netdev": [{"hca": "mlx5_0", "port": 1, "netdev": "ib0", "state": "Up"}],
        "topology": {"raw": "\tGPU0\tNIC0\nGPU0\t X \tNODE\n"},
        "system": {"uname": "Linux h 5.14.0 x", "nvidia_driver": driver},
    }


def test_compare_snapshots_match():
    snap = _verify_snap()
    assert fabric.compare_snapshots(snap, snap) == {"hardware": [], "informational": []}


def test_compare_snapshots_rate_drift():
    findings = fabric.compare_snapshots(
        _verify_snap(rate="200 Gb/sec"), _verify_snap(rate="100 Gb/sec")
    )
    assert any("rate" in item for item in findings["hardware"])
    assert findings["informational"] == []


def test_compare_snapshots_gpu_drift():
    findings = fabric.compare_snapshots(
        _verify_snap(gpu_name="A100"), _verify_snap(gpu_name="H100")
    )
    assert any("gpu inventory" in item for item in findings["hardware"])


def test_compare_snapshots_driver_is_informational():
    findings = fabric.compare_snapshots(_verify_snap(driver="575"), _verify_snap(driver="576"))
    assert findings["hardware"] == []
    assert any("driver" in item for item in findings["informational"])


def test_render_drift_verdict():
    assert "MATCH" in fabric.render_drift({"hardware": [], "informational": []}, False)
    assert "DRIFT" in fabric.render_drift({"hardware": ["x"], "informational": []}, False)
    assert "MATCH" in fabric.render_drift({"hardware": [], "informational": ["d"]}, False)
    assert "DRIFT" in fabric.render_drift({"hardware": [], "informational": ["d"]}, True)
