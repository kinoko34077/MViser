import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
sys.path.insert(0, str(PROJECT / "tools"))

import os  # noqa: E402

# Isolate tests from a developer's real Global settings file (MViser#16).
os.environ["MVISER_GLOBAL"] = str(PROJECT / "tests" / "__no_global__.yaml")
