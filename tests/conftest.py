import sys
from pathlib import Path

# The tracker modules import each other as top-level modules (run from pricing_tracker/).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pricing_tracker"))
