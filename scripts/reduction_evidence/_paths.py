"""Where the reduction-evidence scripts read DB exports and write results (2026-11-23).

Results and DB exports are data, so they live outside Git: ``<repo>/data/derived/reduction_evidence/<step>/`` by default,
or under ``$REDUCTION_EVIDENCE_DATA``. Hand-made inputs that the repo keeps (source checks, cooling rows, transcribed plan
tables) stay next to the scripts."""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("REDUCTION_EVIDENCE_DATA", str(REPO / "data" / "derived" / "reduction_evidence")))


def data(step: str) -> Path:
    path = DATA / step
    path.mkdir(parents=True, exist_ok=True)
    return path
