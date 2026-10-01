"""
scripts/train_model.py

Thin CLI entry point. Actual training logic lives in ml/training/train.py.

Usage:
    python scripts/train_model.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ml.training.train import main  # noqa: E402

if __name__ == "__main__":
    main()
