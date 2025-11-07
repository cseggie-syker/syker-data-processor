import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.dtl_processor_web import DTLProcessingError, DTLWebProcessor  # noqa: E402


def test_process_uploads_requires_files(tmp_path: Path) -> None:
    processor = DTLWebProcessor()

    with pytest.raises(DTLProcessingError):
        processor.process_uploads([])


def test_process_directory_missing_files(tmp_path: Path) -> None:
    processor = DTLWebProcessor()

    with pytest.raises(DTLProcessingError):
        processor.process_directory(tmp_path)


