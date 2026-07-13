from __future__ import annotations

try:
    from backend.application.explanation_use_cases import ExplanationUseCases
    from backend.application.live_schedule_use_cases import LiveScheduleUseCases
    from backend.application.scheduler_use_cases import SchedulerUseCases
    from backend.bootstrap import get_dependencies
    from backend.repositories.academic_data_repository import AcademicDataRepository
    from backend.repositories.requirement_repository import RequirementRepository
    from backend.repositories.working_timetable_repository import WorkingTimetableRepository
    from backend.services.academic_workbook_importer import AcademicWorkbookImporter
    from backend.services.excel_workbook_analyzer import ExcelWorkbookAnalyzer
    from backend.services.excel_template_exporter import ExcelTemplateExporter
    from backend.services.requirement_service import RequirementService
except ModuleNotFoundError:  # pragma: no cover
    from application.explanation_use_cases import ExplanationUseCases
    from application.live_schedule_use_cases import LiveScheduleUseCases
    from application.scheduler_use_cases import SchedulerUseCases
    from bootstrap import get_dependencies
    from repositories.academic_data_repository import AcademicDataRepository
    from repositories.requirement_repository import RequirementRepository
    from repositories.working_timetable_repository import WorkingTimetableRepository
    from services.academic_workbook_importer import AcademicWorkbookImporter
    from services.excel_workbook_analyzer import ExcelWorkbookAnalyzer
    from services.excel_template_exporter import ExcelTemplateExporter
    from services.requirement_service import RequirementService


def get_requirement_repo() -> RequirementRepository:
    return get_dependencies().requirement_repo


def get_requirement_service() -> RequirementService:
    return get_dependencies().requirement_service


def get_academic_data_repo() -> AcademicDataRepository:
    return get_dependencies().academic_data_repo


def get_academic_workbook_importer() -> AcademicWorkbookImporter:
    return get_dependencies().academic_workbook_importer


def get_excel_workbook_analyzer() -> ExcelWorkbookAnalyzer:
    return get_dependencies().excel_workbook_analyzer


def get_excel_template_exporter() -> ExcelTemplateExporter:
    return get_dependencies().excel_template_exporter


def get_scheduler_use_cases() -> SchedulerUseCases:
    return get_dependencies().scheduler_use_cases


def get_live_schedule_use_cases() -> LiveScheduleUseCases:
    return get_dependencies().live_schedule_use_cases


def get_explanation_use_cases() -> ExplanationUseCases:
    return get_dependencies().explanation_use_cases


def get_proposal_store() -> dict:
    return get_dependencies().proposal_store


def get_working_timetable_repo() -> WorkingTimetableRepository:
    return get_dependencies().working_timetable_repo
