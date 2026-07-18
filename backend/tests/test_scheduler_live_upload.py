from pathlib import Path

from backend.bootstrap import reset_dependencies
from backend.dependencies import get_live_schedule_use_cases


def test_load_fet_accepts_uploaded_file_bytes() -> None:
    reset_dependencies()
    fet_file_path = Path(__file__).resolve().parents[2] / "EMAD_2627_.fet"
    content = fet_file_path.read_bytes()

    result = get_live_schedule_use_cases().load_fet(content)

    assert result["ok"] is True
    assert result["loaded"] > 0
    assert isinstance(result.get("activities"), list)
    assert isinstance(result.get("conflicts"), list)
