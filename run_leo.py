"""Run Leo's command line straight from the plugin folder:  python run_leo.py <command>"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from leo.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
