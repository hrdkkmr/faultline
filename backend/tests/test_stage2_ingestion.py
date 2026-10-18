import json

import pytest

from app.config import get_settings
from app.ingestion import rcaeval
from app.ingestion.features import _sanitize_message, extract_case, split_metric_column
from app.ingestion.pipeline import load_processed

from .fixtures import make_case


def test_incident_id_is_stable_and_opaque():
    a = rcaeval.incident_id_for("re2ob_checkoutservice_cpu_1")
    assert a == rcaeval.incident_id_for("re2ob_checkoutservice_cpu_1")
    assert a.startswith("INC-") and len(a) == 14
    assert "checkout" not in a and "cpu" not in a


def test_metric_column_parsing():
    assert split_metric_column("checkoutservice_latency-90") == ("checkoutservice", "latency-90")
    assert split_metric_column("frontend-external_workload") == ("frontend-external", "workload")
    assert split_metric_column("redis_diskio") == ("redis", "diskio")
    assert split_metric_column("weird") is None


def test_extract_detects_injected_shift(tmp_path):
    d = make_case(tmp_path / "c1", hot_service="currencyservice")
    ev = extract_case(d, "INC-unit")
    top = max((o for o in ev["observations"] if o["kind"] == "metric"), key=lambda o: o["score"])
    assert (top["service"], top["signal"], top["direction"]) == ("currencyservice", "cpu", "up")
    assert top["anomalous"] and top["onset_s"] is not None and top["onset_s"] >= 0
    normal = [o for o in ev["observations"] if o["kind"] == "metric" and o["service"] == "frontend"]
    assert normal and not any(o["anomalous"] for o in normal)
    assert {"caller": "frontend", "callee": "currencyservice"}.items() <= ev["calls"][0].items()
    errs = [o for o in ev["observations"] if o["signal"] == "log_errors" and o["service"] == "currencyservice"]
    assert errs and errs[0]["anomalous"] and "<n>" in errs[0]["samples"][0]
    assert len({o["id"] for o in ev["observations"]}) == len(ev["observations"])


def test_extract_without_optional_telemetry(tmp_path):
    d = make_case(tmp_path / "c2", with_logs=False, with_traces=False)
    ev = extract_case(d, "INC-unit2")
    assert ev["telemetry"] == {"metrics": True, "logs": False, "traces": False, "metric_columns": 12}
    assert set(ev["quality"]["missing_files"]) == {"logs.parquet", "traces.parquet"}


def test_invalid_inputs_fail_visibly(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        extract_case(tmp_path / "nope", "INC-x")
    d = make_case(tmp_path / "c3")
    (d / "inject_time.txt").write_text("yesterday")
    with pytest.raises(ValueError, match="not an integer"):
        extract_case(d, "INC-x")
    (d / "inject_time.txt").write_text("1")
    with pytest.raises(ValueError, match="outside metric window"):
        extract_case(d, "INC-x")
    (d / "metrics.parquet").unlink()
    with pytest.raises(ValueError, match="required file missing"):
        extract_case(d, "INC-x")


def test_log_text_is_sanitized():
    s = _sanitize_message("ERROR   user 12345 \n DROP TABLE; " + "x" * 500)
    assert "12345" not in s and "\n" not in s and len(s) <= 160


# ---- checks over the real processed RCAEval data (requires `python scripts/ingest.py` first) ----

def _real():
    evs = [e for e in load_processed(get_settings().data_path) if e["source"] == "rcaeval"]
    if not evs:
        pytest.fail("no processed RCAEval data; run `python scripts/ingest.py --mode sample` first")
    return evs


def test_real_processed_evidence_has_no_labels():
    s = get_settings()
    manifest = json.loads((s.data_path / "manifests" / "rcaeval_manifest.json").read_text())
    case_of = {c["incident_id"]: c["case"] for c in manifest["cases"]}
    for ev in _real():
        blob = json.dumps(ev)
        assert case_of[ev["incident_id"]] not in blob
        for k in ("root_cause", "fault", "case", "repetition", "split"):
            assert f'"{k}"' not in blob, (ev["incident_id"], k)


def test_real_processed_evidence_has_provenance_and_observations():
    for ev in _real():
        assert ev["provenance"]["revision"] == rcaeval.HF_REVISION
        assert ev["telemetry"]["metrics"]
        assert len(ev["observations"]) > 50
