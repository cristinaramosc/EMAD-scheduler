from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

if __package__ and __package__.startswith("backend"):
    from backend.dependencies import get_academic_workbook_importer
    from backend.services.academic_workbook_importer import AcademicWorkbookImportError
else:  # pragma: no cover
    from dependencies import get_academic_workbook_importer
    from services.academic_workbook_importer import AcademicWorkbookImportError


router = APIRouter(prefix="/imports/excel/academic-workbook", tags=["Academic Workbook Import"])


class WorkbookFileDTO(BaseModel):
    name: str
    workbook_base64: str


class AcademicWorkbookImportRequest(BaseModel):
    files: list[WorkbookFileDTO]


@router.post("/import")
def import_academic_workbook(payload: AcademicWorkbookImportRequest):
    importer = get_academic_workbook_importer()
    try:
        report = importer.import_base64_files([item.dict() for item in payload.files])
    except AcademicWorkbookImportError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "academic_workbook_validation_failed",
                "issues": [issue.to_dict() for issue in exc.issues],
            },
        ) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail="academic_workbook_import_failed") from exc

    body = report.to_dict()
    return {
        "ok": True,
        **body,
    }
