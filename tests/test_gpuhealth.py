"""Tests for the gpuhealth module. Offline: built-in fixtures, no GPU needed."""

import json

import pytest

from clustertool import gpuhealth as gh

_THROTTLE = (
    "sw_power_cap",
    "sw_thermal_slowdown",
    "hw_thermal_slowdown",
    "hw_slowdown",
    "hw_power_brake_slowdown",
)


def _throttle_block(
    power_cap=False, sw_thermal=False, hw_thermal=False, hw_slowdown=False, power_brake=False
):
    states = dict(
        zip(
            _THROTTLE,
            (power_cap, sw_thermal, hw_thermal, hw_slowdown, power_brake),
            strict=True,
        )
    )
    body = ""
    for name, active in states.items():
        state = "Active" if active else "Not Active"
        tag = f"clocks_throttle_reason_{name}"
        body += f"<{tag}>{state}</{tag}>"
    return f"<clocks_throttle_reasons>{body}</clocks_throttle_reasons>"


def _ecc_section(tag, correctable=0, uncorrectable=0):
    return (
        f"<{tag}><sram_correctable>0</sram_correctable>"
        f"<sram_uncorrectable>0</sram_uncorrectable>"
        f"<dram_correctable>{correctable}</dram_correctable>"
        f"<dram_uncorrectable>{uncorrectable}</dram_uncorrectable></{tag}>"
    )


def _gpu(
    index=0,
    serial="1650000000001",
    ecc="Enabled",
    vol_corr=0,
    vol_unc=0,
    agg_unc=0,
    remap_pending="No",
    remap_failure="No",
    temp="41 C",
    slow="92 C",
    replay=0,
    old_power=False,
    power_draw="71.50 W",
    power_limit="700.00 W",
    **throttle,
):
    parts = [
        '<gpu id="00000000:19:00.0">',
        "<product_name>NVIDIA H100 80GB HBM3</product_name>",
        f"<serial>{serial}</serial>",
        f"<minor_number>{index}</minor_number>",
        f"<ecc_mode><current_ecc>{ecc}</current_ecc></ecc_mode>",
    ]
    if ecc == "Enabled":
        parts.append("<ecc_errors>")
        parts.append(_ecc_section("volatile", vol_corr, vol_unc))
        parts.append(_ecc_section("aggregate", 0, agg_unc))
        parts.append("</ecc_errors>")
        parts.append(
            f"<remapped_rows><remapped_row_pending>{remap_pending}</remapped_row_pending>"
            f"<remapped_row_failure>{remap_failure}</remapped_row_failure></remapped_rows>"
        )
    parts.append(
        f"<temperature><gpu_temp>{temp}</gpu_temp>"
        f"<gpu_temp_slow_threshold>{slow}</gpu_temp_slow_threshold></temperature>"
    )
    parts.append(_throttle_block(**throttle))
    if old_power:
        parts.append(
            f"<power_readings><power_draw>{power_draw}</power_draw>"
            f"<power_limit>{power_limit}</power_limit></power_readings>"
        )
    else:
        parts.append(
            f"<gpu_power_readings><power_draw>{power_draw}</power_draw>"
            f"<current_power_limit>{power_limit}</current_power_limit></gpu_power_readings>"
        )
    parts.append(f"<pci><replay_counter>{replay}</replay_counter></pci>")
    parts.append("</gpu>")
    return "".join(parts)


def _smi_xml(*gpus, driver="550.54.15"):
    body = "".join(gpus)
    return (
        '<?xml version="1.0" ?><nvidia_smi_log>'
        f"<driver_version>{driver}</driver_version>{body}</nvidia_smi_log>"
    )


def _nvlink(gpu0_link1_crc=0, gpu1_link1_crc=0):
    def block(idx, crc):
        return "\n".join(
            [
                f"GPU {idx}: NVIDIA H100 80GB HBM3 (UUID: GPU-{idx})",
                "         Link 0: Replay Errors: 0",
                "         Link 0: Recovery Errors: 0",
                "         Link 0: CRC Errors: 0",
                "         Link 1: Replay Errors: 0",
                "         Link 1: Recovery Errors: 0",
                f"         Link 1: CRC Errors: {crc}",
            ]
        )

    return block(0, gpu0_link1_crc) + "\n" + block(1, gpu1_link1_crc) + "\n"


HEALTHY = _smi_xml(_gpu(index=0), _gpu(index=1, serial="1650000000002", temp="39 C"))
ECC_DISABLED = _smi_xml(
    _gpu(
        ecc="Disabled",
        serial="N/A",
        slow="N/A",
        temp="35 C",
        old_power=True,
        power_draw="28.00 W",
        power_limit="450.00 W",
    ),
    driver="535.104.05",
)


def test_parse_healthy_two_gpus():
    parsed = gh.parse_smi_xml(HEALTHY)
    assert parsed["driver_version"] == "550.54.15"
    assert len(parsed["gpus"]) == 2
    g0 = parsed["gpus"][0]
    assert g0["index"] == 0
    assert g0["name"] == "NVIDIA H100 80GB HBM3"
    assert g0["serial"] == "1650000000001"
    assert g0["ecc_enabled"] is True
    assert g0["volatile_correctable"] == 0
    assert g0["volatile_uncorrectable"] == 0
    assert g0["aggregate_uncorrectable"] == 0
    assert g0["row_remap_pending"] is False
    assert g0["row_remap_failure"] is False
    assert g0["retired_pages_pending"] is None
    assert g0["throttle"] == {
        "sw_power_cap": False,
        "sw_thermal": False,
        "hw_thermal": False,
        "hw_slowdown": False,
        "hw_power_brake": False,
    }
    assert g0["temp_c"] == 41
    assert g0["slowdown_temp_c"] == 92
    assert g0["power_w"] == 71.5
    assert g0["power_limit_w"] == 700.0
    assert g0["pcie_replay"] == 0
    assert parsed["gpus"][1]["index"] == 1


def test_parse_doctored_uncorrectable():
    xml = _smi_xml(_gpu(vol_unc=3))
    assert gh.parse_smi_xml(xml)["gpus"][0]["volatile_uncorrectable"] == 3


def test_parse_ecc_disabled():
    g0 = gh.parse_smi_xml(ECC_DISABLED)["gpus"][0]
    assert g0["ecc_enabled"] is False
    assert g0["volatile_uncorrectable"] is None
    assert g0["row_remap_pending"] is None
    assert g0["serial"] is None
    assert g0["slowdown_temp_c"] is None
    assert g0["power_w"] == 28.0
    assert g0["power_limit_w"] == 450.0


def test_parse_garbled_raises():
    with pytest.raises(ValueError):
        gh.parse_smi_xml("<?xml version='1.0'?><nvidia_smi_log><gpu><product_name>NVIDIA")


def test_parse_no_gpus_raises():
    with pytest.raises(ValueError):
        gh.parse_smi_xml("<nvidia_smi_log></nvidia_smi_log>")


def test_nvlink_healthy():
    per_gpu = gh.parse_nvlink(_nvlink())
    assert sorted(per_gpu) == [0, 1]
    assert per_gpu[0] == {"replay_errors": 0, "recovery_errors": 0, "crc_errors": 0}


def test_nvlink_sums_across_links():
    per_gpu = gh.parse_nvlink(_nvlink(gpu0_link1_crc=7))
    assert per_gpu[0]["crc_errors"] == 7
    assert per_gpu[1]["crc_errors"] == 0


def test_nvlink_unsupported_empty():
    assert gh.parse_nvlink("") == {}
    assert gh.parse_nvlink("NVLink is not supported on this device\n") == {}


def healthy_gpu(**overrides):
    gpu = {
        "index": 0,
        "name": "NVIDIA H100",
        "serial": "1650000000001",
        "ecc_enabled": True,
        "volatile_correctable": 0,
        "volatile_uncorrectable": 0,
        "aggregate_uncorrectable": 0,
        "row_remap_pending": False,
        "row_remap_failure": False,
        "retired_pages_pending": None,
        "sram_threshold_exceeded": False,
        "throttle": {
            "sw_power_cap": False,
            "sw_thermal": False,
            "hw_thermal": False,
            "hw_slowdown": False,
            "hw_power_brake": False,
        },
        "temp_c": 40,
        "slowdown_temp_c": 92,
        "temp_margin_c": None,
        "power_w": 100.0,
        "power_limit_w": 700.0,
        "pcie_replay": 0,
    }
    gpu.update(overrides)
    return gpu


NO_NVLINK_ERRORS = {"replay_errors": 0, "recovery_errors": 0, "crc_errors": 0}


def tiers(gpu, nvlink=NO_NVLINK_ERRORS):
    return {k: v[0] for k, v in gh.evaluate(gpu, nvlink).items()}


def test_evaluate_all_ok():
    assert tiers(healthy_gpu()) == {
        "ecc": gh.OK,
        "throttle": gh.OK,
        "pcie": gh.OK,
        "nvlink": gh.OK,
    }


def test_evaluate_volatile_uncorrectable_fails():
    assert tiers(healthy_gpu(volatile_uncorrectable=1))["ecc"] == gh.FAIL


def test_evaluate_row_remap_pending_fails():
    assert tiers(healthy_gpu(row_remap_pending=True))["ecc"] == gh.FAIL


def test_evaluate_row_remap_failure_fails():
    assert tiers(healthy_gpu(row_remap_failure=True))["ecc"] == gh.FAIL


def test_evaluate_retired_pages_pending_fails():
    assert tiers(healthy_gpu(retired_pages_pending=True))["ecc"] == gh.FAIL


def test_evaluate_hw_slowdown_fails():
    gpu = healthy_gpu()
    gpu["throttle"]["hw_slowdown"] = True
    assert tiers(gpu)["throttle"] == gh.FAIL


def test_evaluate_aggregate_uncorrectable_warns():
    assert tiers(healthy_gpu(aggregate_uncorrectable=2))["ecc"] == gh.WARN


def test_evaluate_correctable_over_threshold_warns():
    gpu = healthy_gpu(volatile_correctable=gh.CORRECTABLE_ECC_WARN + 1)
    assert tiers(gpu)["ecc"] == gh.WARN


def test_evaluate_correctable_at_threshold_ok():
    gpu = healthy_gpu(volatile_correctable=gh.CORRECTABLE_ECC_WARN)
    assert tiers(gpu)["ecc"] == gh.OK


def test_evaluate_power_cap_throttle_is_ok():
    """man nvidia-smi calls this the SW scaling algorithm holding the power limit."""
    gpu = healthy_gpu()
    gpu["throttle"]["sw_power_cap"] = True
    checks = gh.evaluate(gpu, None)
    assert checks["throttle"][0] == gh.OK
    assert "normal" in checks["throttle"][1]


def test_evaluate_power_brake_fails():
    gpu = healthy_gpu()
    gpu["throttle"]["hw_power_brake"] = True
    checks = gh.evaluate(gpu, None)
    assert checks["throttle"][0] == gh.FAIL
    assert "hw_power_brake" in checks["throttle"][1]


def test_evaluate_throttle_all_unreported_is_na():
    gpu = healthy_gpu()
    gpu["throttle"] = dict.fromkeys(gpu["throttle"])
    gpu["temp_c"] = None
    gpu["slowdown_temp_c"] = None
    gpu["temp_margin_c"] = None
    assert tiers(gpu)["throttle"] == gh.NA


def test_evaluate_thermal_throttle_warns():
    gpu = healthy_gpu()
    gpu["throttle"]["sw_thermal"] = True
    assert tiers(gpu)["throttle"] == gh.WARN


def test_evaluate_hw_thermal_throttle_warns():
    gpu = healthy_gpu()
    gpu["throttle"]["hw_thermal"] = True
    assert tiers(gpu)["throttle"] == gh.WARN


def test_evaluate_temp_near_slowdown_warns():
    gpu = healthy_gpu(temp_c=92 - gh.TEMP_MARGIN_C, slowdown_temp_c=92)
    assert tiers(gpu)["throttle"] == gh.WARN


def test_evaluate_temp_below_margin_ok():
    gpu = healthy_gpu(temp_c=92 - gh.TEMP_MARGIN_C - 1, slowdown_temp_c=92)
    assert tiers(gpu)["throttle"] == gh.OK


def test_evaluate_pcie_replay_warns_above_threshold():
    assert tiers(healthy_gpu(pcie_replay=gh.PCIE_REPLAY_WARN + 1))["pcie"] == gh.WARN


def test_evaluate_pcie_replay_at_threshold_is_ok():
    """A replay is an ordinary link-layer retry, so a handful is not a fault."""
    assert tiers(healthy_gpu(pcie_replay=gh.PCIE_REPLAY_WARN))["pcie"] == gh.OK


def test_evaluate_sram_threshold_exceeded_fails():
    gpu = healthy_gpu()
    gpu["sram_threshold_exceeded"] = True
    checks = gh.evaluate(gpu, None)
    assert checks["ecc"][0] == gh.FAIL
    assert "RMA" in checks["ecc"][1]


def test_evaluate_thermal_margin_warns_without_a_slowdown_threshold():
    """Hopper reports gpu_temp_tlimit, a margin, and no absolute slowdown point."""
    gpu = healthy_gpu(temp_c=60)
    gpu["slowdown_temp_c"] = None
    gpu["temp_margin_c"] = gh.TEMP_MARGIN_C
    assert tiers(gpu)["throttle"] == gh.WARN
    gpu["temp_margin_c"] = gh.TEMP_MARGIN_C + 1
    assert tiers(gpu)["throttle"] == gh.OK


def test_evaluate_nvlink_errors_warn():
    assert tiers(healthy_gpu(), nvlink={"crc_errors": 3})["nvlink"] == gh.WARN


def test_evaluate_ecc_disabled_is_na():
    gpu = healthy_gpu(
        ecc_enabled=False,
        volatile_correctable=None,
        volatile_uncorrectable=None,
        aggregate_uncorrectable=None,
        row_remap_pending=None,
        row_remap_failure=None,
    )
    assert tiers(gpu)["ecc"] == gh.NA


def test_evaluate_ecc_unreported_is_na():
    gpu = healthy_gpu(
        ecc_enabled=None,
        volatile_correctable=None,
        volatile_uncorrectable=None,
        aggregate_uncorrectable=None,
        row_remap_pending=None,
        row_remap_failure=None,
        retired_pages_pending=None,
        sram_threshold_exceeded=None,
    )
    assert tiers(gpu)["ecc"] == gh.NA


def test_evaluate_no_nvlink_is_na():
    assert tiers(healthy_gpu(), nvlink=None)["nvlink"] == gh.NA


def test_evaluate_no_throttle_data_is_na():
    gpu = healthy_gpu(throttle=None, temp_c=None, slowdown_temp_c=None)
    assert tiers(gpu)["throttle"] == gh.NA


def test_evaluate_pcie_unreported_is_na():
    assert tiers(healthy_gpu(pcie_replay=None))["pcie"] == gh.NA


def test_evaluate_ecc_counters_unreported_noted():
    gpu = healthy_gpu(
        volatile_correctable=None,
        volatile_uncorrectable=None,
        aggregate_uncorrectable=None,
    )
    check = gh.evaluate(gpu, NO_NVLINK_ERRORS)["ecc"]
    assert check[0] == gh.OK
    assert "not reported" in check[1]


def test_worst_ordering():
    assert gh.worst([gh.OK, gh.WARN, gh.FAIL]) == gh.FAIL
    assert gh.worst([gh.OK, gh.WARN]) == gh.WARN
    assert gh.worst([gh.OK, gh.OK]) == gh.OK


def test_worst_na_never_worsens():
    assert gh.worst([gh.NA, gh.OK]) == gh.OK
    assert gh.worst([gh.NA]) == gh.OK
    assert gh.worst([]) == gh.OK


def _healthy_result():
    parsed = gh.parse_smi_xml(HEALTHY)
    nvlink = gh.parse_nvlink(_nvlink())
    return gh.build_result(parsed, nvlink, host="testhost", timestamp="2026-07-02T10:00:00")


def test_build_healthy_snapshot():
    result = _healthy_result()
    assert result["host"] == "testhost"
    assert result["timestamp"] == "2026-07-02T10:00:00"
    assert result["driver_version"] == "550.54.15"
    assert result["verdict"] == gh.OK
    assert len(result["gpus"]) == 2
    g0 = result["gpus"][0]
    assert g0["verdict"] == gh.OK
    assert sorted(g0["checks"]) == ["ecc", "nvlink", "pcie", "throttle"]
    assert g0["checks"]["ecc"]["row_remap"] == "none"
    assert g0["checks"]["nvlink"]["errors"] == {}
    assert g0["checks"]["throttle"]["active"] == []


def test_build_node_verdict_is_worst_gpu():
    parsed = gh.parse_smi_xml(_smi_xml(_gpu(index=0), _gpu(index=1, vol_unc=5)))
    result = gh.build_result(parsed, None, host="h", timestamp="t")
    assert result["gpus"][0]["verdict"] == gh.OK
    assert result["gpus"][1]["verdict"] == gh.FAIL
    assert result["verdict"] == gh.FAIL


def test_build_nvlink_none_is_na_everywhere():
    parsed = gh.parse_smi_xml(HEALTHY)
    result = gh.build_result(parsed, None, host="h", timestamp="t")
    for gpu in result["gpus"]:
        assert gpu["checks"]["nvlink"]["status"] == gh.NA
    assert result["verdict"] == gh.OK


def test_build_header_only_nvlink_is_na():
    parsed = gh.parse_smi_xml(HEALTHY)
    nvlink = gh.parse_nvlink("GPU 0: NVIDIA H100 (UUID: x)\nGPU 1: NVIDIA H100 (UUID: y)\n")
    result = gh.build_result(parsed, nvlink, host="h", timestamp="t")
    for gpu in result["gpus"]:
        assert gpu["checks"]["nvlink"]["status"] == gh.NA


def test_build_row_remap_states():
    parsed = gh.parse_smi_xml(_smi_xml(_gpu(remap_pending="Yes")))
    result = gh.build_result(parsed, None, host="h", timestamp="t")
    assert result["gpus"][0]["checks"]["ecc"]["row_remap"] == "pending"
    assert result["gpus"][0]["verdict"] == gh.FAIL


def test_render_text_healthy():
    text = gh.render_text(_healthy_result())
    assert text.startswith("gpu-health @ testhost  (driver 550.54.15,")
    assert "GPU 0: NVIDIA H100 80GB HBM3" in text
    assert "GPU 1:" in text
    assert text.rstrip().endswith("node verdict: OK")


def test_collect_not_found(monkeypatch):
    monkeypatch.setattr(gh.process, "probe", lambda cmd, timeout=None: (127, "", ""))
    with pytest.raises(gh.ProbeError, match="not found"):
        gh.collect()


def test_collect_timeout(monkeypatch):
    monkeypatch.setattr(gh.process, "probe", lambda cmd, timeout=None: (124, "", ""))
    with pytest.raises(gh.ProbeError, match="timed out"):
        gh.collect()


def test_collect_nonzero_failed(monkeypatch):
    monkeypatch.setattr(gh.process, "probe", lambda cmd, timeout=None: (2, "", "boom"))
    with pytest.raises(gh.ProbeError, match="failed"):
        gh.collect()


def test_collect_nvlink_failure_degrades(monkeypatch):
    def fake(cmd, timeout=None):
        if cmd[:2] == ["nvidia-smi", "-q"]:
            return (0, "<xml/>", "")
        return (1, "", "no nvlink")

    monkeypatch.setattr(gh.process, "probe", fake)
    xml_text, nvlink_text = gh.collect()
    assert xml_text == "<xml/>"
    assert nvlink_text is None


def test_render_text_names_failing_gpu():
    parsed = gh.parse_smi_xml(_smi_xml(_gpu(remap_failure="Yes")))
    result = gh.build_result(parsed, None, host="h", timestamp="t")
    text = gh.render_text(result)
    assert "row remap failure" in text
    assert text.rstrip().endswith("node verdict: FAIL (GPU 0)")


def test_render_json_round_trips():
    result = _healthy_result()
    payload = gh.render_json(result)
    assert json.loads(payload) == result
    assert payload.endswith("\n")


def test_nvlink_errors_are_attributed_to_the_right_gpu():
    """The XML position is the nvidia-smi index that parse_nvlink keys on."""
    xml = "<nvidia_smi_log>" + _gpu(index=1) + _gpu(index=0) + "</nvidia_smi_log>"
    parsed = gh.parse_smi_xml(xml)["gpus"]
    assert [g["index"] for g in parsed] == [0, 1]
    assert [g["minor_number"] for g in parsed] == [1, 0]


def test_nvlink_errors_land_on_the_nvidia_smi_index():
    """parse_nvlink keys on the nvidia-smi index, which is the <gpu> element order."""
    xml = "<nvidia_smi_log>" + _gpu(index=1) + _gpu(index=0) + "</nvidia_smi_log>"
    result = gh.build_result(gh.parse_smi_xml(xml), gh.parse_nvlink(_nvlink(gpu0_link1_crc=42)))
    first, second = result["gpus"]
    assert (first["index"], first["minor_number"]) == (0, 1)
    assert "crc_errors=42" in first["checks"]["nvlink"]["detail"]
    assert second["checks"]["nvlink"]["detail"] == ""
