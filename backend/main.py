from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from backend.routes.teachers import router as teachers_router
    from backend.routes.activities import router as activities_router
    from backend.routes.academic_data import router as academic_data_router
    from backend.routes.academic_workbook import router as academic_workbook_router
    from backend.routes.academic_workbook_spreadsheet import router as academic_workbook_spreadsheet_router
    from backend.routes.excel_import import router as excel_import_router
    from backend.routes.excel_templates import router as excel_templates_router
    from backend.routes.scheduler import router as scheduler_router
    from backend.routes.scheduler_live import router as scheduler_live_router
    from backend.routes.requirements import router as requirements_router
    from backend.routes.schedule_explanations import router as schedule_explanations_router
except ModuleNotFoundError:
    from routes.teachers import router as teachers_router
    from routes.activities import router as activities_router
    from routes.academic_data import router as academic_data_router
    from routes.academic_workbook import router as academic_workbook_router
    from routes.academic_workbook_spreadsheet import router as academic_workbook_spreadsheet_router
    from routes.excel_import import router as excel_import_router
    from routes.excel_templates import router as excel_templates_router
    from routes.scheduler import router as scheduler_router
    from routes.scheduler_live import router as scheduler_live_router
    from routes.requirements import router as requirements_router
    from routes.schedule_explanations import router as schedule_explanations_router


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(teachers_router)
app.include_router(activities_router)
app.include_router(academic_data_router)
app.include_router(academic_workbook_router)
app.include_router(academic_workbook_spreadsheet_router)
app.include_router(excel_import_router)
app.include_router(excel_templates_router)
app.include_router(scheduler_router)
app.include_router(scheduler_live_router)
app.include_router(requirements_router)
app.include_router(schedule_explanations_router)


@app.get("/")
def root():
    return {"missatge": "EMAD Scheduler funciona!"}