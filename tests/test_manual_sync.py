"""0.4.0 M7: the manual can't drift from the code.

Gates: generated blocks are current; every protection window has an
alarm-response section and vice versa; every procedure is rendered; every
backticked name in the prose is a real contract name (or an existing repo
path); every `<!-- src: path::Symbol -->` provenance comment names a symbol
that exists; units cover every instrument exactly; and the manual never names
the simulator's fault-injection events (answer-key hygiene)."""
import importlib.util
import re
import sys
from pathlib import Path

from hotwell.actions import ACTION_SCHEMA
from hotwell.faults import PLANT_FAULT_TYPES
from hotwell.plant import load_config
from hotwell.procedures import load_procedures
from hotwell.protection.tables import load_protection_table
from hotwell.scenario import EVENT_TYPES
from hotwell.sensors import OBSERVATION_SPEC
from hotwell.simulator import Simulator
from hotwell.units import INSTRUMENT_UNITS

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "docs" / "manual"
_spec = importlib.util.spec_from_file_location("gen_manual", ROOT / "scripts" / "gen_manual.py")
gen_manual = importlib.util.module_from_spec(_spec)
sys.modules["gen_manual"] = gen_manual
_spec.loader.exec_module(gen_manual)

COMMENT = re.compile(r"<!--.*?-->", re.S)
TICKS = re.compile(r"`([^`\n]+)`")


def _texts() -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted(MANUAL.glob("*.md"))}


def _known_names() -> set[str]:
    sim = Simulator(load_config(), seed=0)
    sim.initialize_steady_state(60.0)
    names = {s.name for s in OBSERVATION_SPEC} | {a.key for a in ACTION_SCHEMA}
    names |= {c.id for c in load_protection_table().conditions}
    names |= set(sim._indications())
    names |= set(load_procedures())
    names |= {"cp1", "cp2", "fp1", "fp2", "<from>", "<to>"}            # pump names, params
    names |= {"CP1_TRIP:overload", "MANUAL_MFT", "MANUAL_TURBINE_TRIP"}  # first-out labels
    return names


def test_generated_blocks_are_current():
    stale = gen_manual.stale_files()
    print(f"\nmanual files: {sorted(_texts())}; stale: {[p.name for p in stale]}")
    assert not stale, "run: python scripts/gen_manual.py"


def test_every_window_has_an_alarm_response_section_and_vice_versa():
    text = _texts()["06-alarm-response.md"]
    ids = {c.id for c in load_protection_table().conditions}
    sections = set(re.findall(r"^## (\w+)$", text, re.M))
    blocks = set(re.findall(r"<!-- BEGIN GENERATED: arp_(\w+) -->", text))
    print(f"\n{len(ids)} windows; sections missing {sorted(ids - sections)}; "
          f"stray {sorted(sections - ids)}; arp blocks missing {sorted(ids - blocks)}")
    assert sections == ids
    assert blocks == ids


def test_every_procedure_is_rendered():
    text = _texts()["05-normal-procedures.md"]
    for pid in load_procedures():
        assert f"### {pid} —" in text, pid


def test_backticked_names_are_real():
    known = _known_names()
    allow = {"path::Symbol"}   # 00-index explains the provenance-comment format
    bad = []
    for name, text in _texts().items():
        for tok in TICKS.findall(COMMENT.sub("", text)):
            if tok in known or tok in allow:
                continue
            if "<from>" in tok or "<to>" in tok:
                # a procedure template: valid if it resolves for some pump pair
                pairs = [("cp1", "cp2"), ("fp1", "fp2")]
                if any(tok.replace("<from>", a).replace("<to>", b) in known for a, b in pairs):
                    continue
            if "/" in tok and (ROOT / tok.rstrip("/")).exists():
                continue
            bad.append((name, tok))
    print(f"\nunknown backticked names: {bad}")
    assert not bad


def test_provenance_comments_name_existing_symbols():
    bad, n = [], 0
    for name, text in _texts().items():
        for m in re.finditer(r"<!-- src: (\S+?)(?:::(\w+(?:\.\w+)?))?[ ]?(?:\(.*?\))? -->", text):
            n += 1
            path, sym = ROOT / m.group(1), m.group(2)
            if not path.exists():
                bad.append((name, m.group(1), "missing file"))
                continue
            if sym:
                src = path.read_text()
                parts = sym.split(".")
                pats = [rf"^\s*(class|def) {re.escape(p)}\b" for p in parts]
                if not all(re.search(pt, src, re.M) for pt in pats):
                    bad.append((name, m.group(1), sym))
    print(f"\n{n} provenance comments; bad {bad}")
    assert n > 20
    assert not bad


def test_units_cover_every_instrument_exactly():
    assert set(INSTRUMENT_UNITS) == {s.name for s in OBSERVATION_SPEC}


def test_manual_does_not_name_fault_injection_events():
    """Answer-key hygiene (plan M7): abnormal procedures are symptom-based and
    don't enumerate the simulator's fault library."""
    events = {e for e in (EVENT_TYPES | PLANT_FAULT_TYPES) if "_" in e}
    hits = [(name, e) for name, text in _texts().items() for e in events
            if re.search(rf"\b{re.escape(e)}\b", text)]
    print(f"\nfault-event names checked {sorted(events)}; found {hits}")
    assert not hits
