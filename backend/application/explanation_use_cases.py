from __future__ import annotations

from typing import Any, Dict, Optional


class ExplanationUseCases:
    def __init__(self, explainer: Any) -> None:
        self._explainer = explainer

    def explain_activity(self, activity_id: int) -> Optional[Dict[str, Any]]:
        explanation = self._explainer.explain_activity(activity_id)
        if explanation is None:
            return None
        return self._explainer.to_dict(explanation)
