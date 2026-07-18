from fastapi import APIRouter, HTTPException

if __package__ and __package__.startswith("backend"):
    from backend.dependencies import get_excel_template_exporter
else:  # pragma: no cover
    from dependencies import get_excel_template_exporter


router = APIRouter(prefix="/exports/excel/templates", tags=["Excel Templates"])


@router.post("/generate")
def generate_excel_templates():
    try:
        result = get_excel_template_exporter().export_templates()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail="excel_template_export_failed") from exc

    return {
        "ok": True,
        **result.to_dict(),
    }