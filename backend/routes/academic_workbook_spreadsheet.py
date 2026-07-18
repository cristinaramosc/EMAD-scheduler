from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse

if __package__ and __package__.startswith("backend"):
    from backend.dependencies import get_academic_data_repo
    from backend.services.academic_workbook_spreadsheet import build_workbook, import_workbook
else:  # pragma: no cover
    from dependencies import get_academic_data_repo
    from services.academic_workbook_spreadsheet import build_workbook, import_workbook


router = APIRouter(prefix="/academic-data/spreadsheet", tags=["Academic Data Spreadsheet"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/blank")
def download_blank_spreadsheet():
    """Descarrega un full de càlcul model, buit (sense contingut del FET),
    per començar les dades acadèmiques de zero."""
    buffer = build_workbook(None, blank=True)
    return StreamingResponse(
        buffer,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=EMAD-model-buit.xlsx"},
    )


@router.get("/current")
def download_current_spreadsheet():
    """Descarrega un full de càlcul amb totes les dades acadèmiques actuals
    (professors, grups, assignatures, aules i restriccions)."""
    repo = get_academic_data_repo()
    buffer = build_workbook(repo, blank=False)
    return StreamingResponse(
        buffer,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=EMAD-dades-actuals.xlsx"},
    )


@router.post("/import")
async def import_spreadsheet(file: UploadFile = File(...)):
    """Substitueix les dades acadèmiques del repositori (professors, grups,
    assignatures, aules i restriccions) pel contingut del full de càlcul pujat."""
    repo = get_academic_data_repo()
    content = await file.read()
    try:
        summary = import_workbook(repo, content)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=f"No s'ha pogut importar el full de càlcul: {exc}") from exc

    return {"ok": True, **summary}
