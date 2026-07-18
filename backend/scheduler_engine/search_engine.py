from __future__ import annotations

import time
from typing import List, Optional

from .constraint_evaluator import ConstraintEvaluator
from .models import GenerationContext, GenerationResult, ScheduleProposal, SearchResult
from .proposal_scorer import ProposalScorer


class SearchEngine:
    """Rank and deduplicate proposal candidates from a generation result."""

    def __init__(
        self,
        scorer: Optional[ProposalScorer] = None,
        constraint_evaluator: Optional[ConstraintEvaluator] = None,
    ) -> None:
        self._scorer = scorer or ProposalScorer(constraint_evaluator=constraint_evaluator)

    def search(self, generation_result: GenerationResult, context: GenerationContext) -> SearchResult:
        started_at = time.perf_counter()
        proposals: List[ScheduleProposal] = []

        for proposal in generation_result.proposals:
            self._ensure_scored(proposal, context)
            proposals.append(proposal)

        unique_proposals: List[ScheduleProposal] = []
        seen_ids = set()
        for proposal in proposals:
            if proposal.id in seen_ids:
                continue
            seen_ids.add(proposal.id)
            unique_proposals.append(proposal)

        ordered = sorted(unique_proposals, key=lambda proposal: proposal.score, reverse=True)
        best_proposal = ordered[0] if ordered else None
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)

        return SearchResult(
            best_proposal=best_proposal,
            proposals=ordered,
            explored_states=len(generation_result.proposals),
            elapsed_time_ms=elapsed_ms,
            statistics={
                "proposals_generated": len(ordered),
                "best_score": best_proposal.score if best_proposal else 0.0,
                "duplicates_removed": len(proposals) - len(ordered),
            },
        )

    def _ensure_scored(self, proposal: ScheduleProposal, context: GenerationContext) -> None:
        if proposal.score_breakdown is None:
            breakdown = self._scorer.calculate(proposal, context)
            proposal.score = breakdown.total_score
            proposal.score_breakdown = breakdown
            proposal.metadata = {**(proposal.metadata or {}), "score_breakdown": breakdown}
