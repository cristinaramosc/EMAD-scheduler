from fastapi import APIRouter, HTTPException

if __package__ and __package__.startswith("backend"):
    from backend.dependencies import get_explanation_use_cases
else:  # pragma: no cover
    from dependencies import get_explanation_use_cases

router = APIRouter(prefix="/schedule", tags=["Schedule Explanation"])


@router.get("/activity/{activity_id}/explanation")
def explain_activity(activity_id: int):
    use_cases = get_explanation_use_cases()
    explanation = use_cases.explain_activity(activity_id)
    if explanation is None:
        raise HTTPException(status_code=404, detail="activity_not_found")

    return explanation
