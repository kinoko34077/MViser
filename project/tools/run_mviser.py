"""Run MViser from a checkout without installing: python project/tools/run_mviser.py ..."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mviser.cli import main  # noqa: E402

sys.exit(main())
