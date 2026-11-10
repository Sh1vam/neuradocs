import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import integrity_check  # noqa: E402


def test_project_integrity():
    failed = [msg for level, msg in integrity_check.check() if level == 'FAIL']
    assert not failed, failed
