from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

if __package__ and __package__.startswith("backend"):
    from backend.dependencies import get_excel_workbook_analyzer
else:  # pragma: no cover
    from dependencies import get_excel_workbook_analyzer


router = APIRouter(prefix="/imports/excel", tags=["Excel Import"])


class WorkbookAnalyzeRequest(BaseModel):
    workbook_path: str


@router.post("/analyze")
def analyze_workbook(payload: WorkbookAnalyzeRequest):
    analyzer = get_excel_workbook_analyzer()
    analysis = analyzer.analyze(Path(payload.workbook_path))
    if analysis.errors:
        raise HTTPException(status_code=400, detail=analysis.to_dict())
    return analysis.to_dict()