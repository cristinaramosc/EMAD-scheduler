from pathlib import Path

from backend.bootstrap import reset_dependencies
from backend.routes.excel_templates import generate_excel_templates


def test_generate_excel_templates_endpoint_returns_folder_and_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EMAD_EXCEL_TEMPLATES_DIR", str(tmp_path / "generated"))
    reset_dependencies()

    payload = generate_excel_templates()

    assert payload["ok"] is True
    assert payload["output_folder"]
    assert len(payload["files"]) == 4
    assert sorted(file["name"] for file in payload["files"]) == [
        "01_Carrega_docent.xlsx",
        "02_Restriccions_professors.xlsx",
        "03_Restriccions_grups.xlsx",
        "04_Aules.xlsx",
    ]
    for file in payload["files"]:
        assert Path(file["path"]).exists()
