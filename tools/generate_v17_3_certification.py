"""Generate ENTERPRISE_CERTIFICATION_REPORT.md and all V17.3 reports."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.generate_v17_3_reports import main

if __name__ == "__main__":
    main()
