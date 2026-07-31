"""Tests for the fabric (InfiniBand) helpers."""

from cluster_tools import fabric

# Real nvidia-smi topo -m from a Kempner a100 node (holygpu8a19503).
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
