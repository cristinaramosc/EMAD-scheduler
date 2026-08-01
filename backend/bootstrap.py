from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Dict, Optional

if __package__ and __package__.startswith("backend"):
    from backend.application.assistant_use_cases import AssistantUseCases
    from backend.application.explanation_use_cases import ExplanationUseCases
    from backend.application.live_schedule_use_cases import LiveScheduleUseCases
    from backend.application.scheduler_use_cases import SchedulerUseCases
    from backend.repositories.academic_data_repository import AcademicDataRepository
    from backend.repositories.requirement_repository import RequirementRepository
    from backend.repositories.school_calendar_repository import SchoolCalendarRepository
    from backend.repositories.working_timetable_repository import JsonWorkingTimetableRepository, WorkingTimetableSnapshot
    from backend.scheduler_engine.engine_instance import engine as scheduler_engine
    from backend.scheduler_engine.models import Activity, Conflict, Schedule, ScheduleProposal
    from backend.services.academic_workbook_importer import AcademicWorkbookImporter
    from backend.services.decision_explainer import DecisionExplainer
    from backend.services.excel_workbook_analyzer import ExcelWorkbookAnalyzer
    from backend.services.excel_template_exporter import ExcelTemplateExporter
    from backend.services.requirement_service import RequirementService
else:  # pragma: no cover
    from application.assistant_use_cases import AssistantUseCases
    from application.explanation_use_cases import ExplanationUseCases
    from application.live_schedule_use_cases import LiveScheduleUseCases
    from application.scheduler_use_cases import SchedulerUseCases
    from repositories.academic_data_repository import AcademicDataRepository
    from repositories.requirement_repository import RequirementRepository
    from repositories.school_calendar_repository import SchoolCalendarRepository
    from repositories.working_timetable_repository import JsonWorkingTimetableRepository, WorkingTimetableSnapshot
    from scheduler_engine.engine_instance import engine as scheduler_engine
    from scheduler_engine.models import Activity, Conflict, Schedule, ScheduleProposal
    from services.academic_workbook_importer import AcademicWorkbookImporter
    from services.decision_explainer import DecisionExplainer
    from services.excel_workbook_analyzer import ExcelWorkbookAnalyzer
    from services.excel_template_exporter import ExcelTemplateExporter
    from services.requirement_service import RequirementService


@dataclass
class AppDependencies:
    requirement_repo: RequirementRepository
    requirement_service: RequirementService
    academic_data_repo: AcademicDataRepository
    academic_workbook_importer: AcademicWorkbookImporter
    excel_workbook_analyzer: ExcelWorkbookAnalyzer
    excel_template_exporter: ExcelTemplateExporter
    working_timetable_repo: JsonWorkingTimetableRepository
    proposal_store: Dict[str, ScheduleProposal] = field(default_factory=dict)
    scheduler_use_cases: Optional[SchedulerUseCases] = None
    live_schedule_use_cases: Optional[LiveScheduleUseCases] = None
    explanation_use_cases: Optional[ExplanationUseCases] = None
    assistant_use_cases: Optional[AssistantUseCases] = None


_APP_DEPS: AppDependencies | None = None


def build_dependencies() -> AppDependencies:
    working_timetable_file = Path(
        os.environ.get(
            "EMAD_WORKING_TIMETABLE_FILE",
            str(Path(__file__).resolve().parent / "data" / "working_timetable.json"),
        )
    )
    requirement_repo = RequirementRepository()
    requirement_service = RequirementService(requirement_repo)
    academic_data_repo = AcademicDataRepository()
    school_calendar_repo = SchoolCalendarRepository(
        Path(
            os.environ.get(
                "EMAD_SCHOOL_CALENDAR_FILE",
                str(Path(__file__).resolve().parent / "data" / "school_calendar.json"),
            )
        )
    )
    academic_workbook_importer = AcademicWorkbookImporter(academic_data_repo)
    excel_workbook_analyzer = ExcelWorkbookAnalyzer()
    excel_template_exporter = ExcelTemplateExporter(
        academic_data_repo=academic_data_repo,
        school_calendar_repo=school_calendar_repo,
        output_root=Path(
            os.environ.get(
                "EMAD_EXCEL_TEMPLATES_DIR",
                str(Path(__file__).resolve().parent / "data" / "excel_templates"),
            )
        ),
    )
    working_timetable_repo = JsonWorkingTimetableRepository(working_timetable_file)
    proposal_store: Dict[str, ScheduleProposal] = {}

    _restore_working_timetable_state(working_timetable_repo.load_snapshot(), scheduler_engine, proposal_store)

    scheduler_use_cases = SchedulerUseCases(
        requirement_repo=requirement_repo,
        scheduler_engine=scheduler_engine,
        proposal_store=proposal_store,
        school_calendar=school_calendar_repo.load_school_calendar(),
        time_labels=school_calendar_repo.load_time_labels(),
        academic_data_repo=academic_data_repo,
        working_timetable_repo=working_timetable_repo,
    )
    live_schedule_use_cases = LiveScheduleUseCases(
        engine=scheduler_engine,
        working_timetable_repo=working_timetable_repo,
        academic_data_repo=academic_data_repo,
    )
    explanation_use_cases = ExplanationUseCases(DecisionExplainer(scheduler_engine))
    assistant_use_cases = AssistantUseCases(
        proposal_store=proposal_store,
        academic_data_repo=academic_data_repo,
    )

    return AppDependencies(
        requirement_repo=requirement_repo,
        requirement_service=requirement_service,
        academic_data_repo=academic_data_repo,
        academic_workbook_importer=academic_workbook_importer,
        excel_workbook_analyzer=excel_workbook_analyzer,
        excel_template_exporter=excel_template_exporter,
        working_timetable_repo=working_timetable_repo,
        proposal_store=proposal_store,
        scheduler_use_cases=scheduler_use_cases,
        live_schedule_use_cases=live_schedule_use_cases,
        explanation_use_cases=explanation_use_cases,
        assistant_use_cases=assistant_use_cases,
    )


def _restore_working_timetable_state(
    snapshot: WorkingTimetableSnapshot,
    scheduler_engine,
    proposal_store: Dict[str, ScheduleProposal],
) -> None:
    if scheduler_engine.state.all():
        return

    schedule = Schedule()
    for record in snapshot.active_schedule:
        schedule.add(Activity(**record))
    scheduler_engine.load(schedule)

    proposal_store.clear()
    if snapshot.current_proposal is None:
        return

    proposal_store[snapshot.current_proposal["id"]] = ScheduleProposal(
        id=snapshot.current_proposal["id"],
        activities=[Activity(**activity) for activity in snapshot.current_proposal.get("activities", [])],
        score=snapshot.current_proposal.get("score", 0.0),
        conflicts=[Conflict(**conflict) for conflict in snapshot.current_proposal.get("conflicts", [])],
        warnings=list(snapshot.current_proposal.get("warnings", [])),
        metadata=dict(snapshot.current_proposal.get("metadata", {})),
    )


def get_dependencies() -> AppDependencies:
    global _APP_DEPS
    if _APP_DEPS is None:
        _APP_DEPS = build_dependencies()
    return _APP_DEPS


def reset_dependencies() -> None:
    global _APP_DEPS
    _APP_DEPS = None
