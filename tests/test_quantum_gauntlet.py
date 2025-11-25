import math
from typing import Dict, List

import pytest

from projection.quantum_gauntlet import (
    compute_roster_projection,
    compute_tournament_projection,
)


def _mk_matchup(roster_id: int, starters: List[str], players_points: Dict[str, float]):
    return {"roster_id": roster_id, "starters": starters, "players_points": players_points}


def test_weighted_projection_and_selection_rules():
    # Synthetic history for three weeks back:
    # player A: [10, 20, 30] → weighted 0.6*30 + 0.3*20 + 0.1*10 = 18 + 6 + 1 = 25
    # player B: [0 (excluded), 10, 40] → with exclude_zero=True → [10, 40]
    #   weights normalized for 2 values: 0.6/(0.6+0.3)=0.666..., 0.3/(0.9)=0.333...
    #   forecast = 0.666*40 + 0.333*10 ≈ 26.667 + 3.333 = 30.0
    # player C: no history → forecast = 0.0

    week = 9
    rid = 1
    pA, pB, pC = "A", "B", "C"

    matchups_by_week = {
        6: [_mk_matchup(rid, [pA, pB, pC], {pA: 10, pB: 0})],
        7: [_mk_matchup(rid, [pA, pB, pC], {pA: 20, pB: 10})],
        8: [_mk_matchup(rid, [pA, pB, pC], {pA: 30, pB: 40})],
    }
    current = [_mk_matchup(rid, [pA, pB, pC], {pA: 15, pB: 35, pC: 5})]

    def state_provider(pid: str):
        # A: IN_PROGRESS and live < forecast → use forecast (25)
        # B: IN_PROGRESS and live ≥ forecast → use live (35 vs 30 forecast → 35)
        # C: NOT_STARTED → use forecast (0)
        return {
            pA: "IN_PROGRESS",
            pB: "IN_PROGRESS",
            pC: "NOT_STARTED",
        }[pid]

    rp = compute_roster_projection(
        roster_id=rid,
        week=week,
        matchups_by_week=matchups_by_week,
        current_week_matchups=current,
        get_player_game_state=state_provider,
    )

    # A chosen 25.0, B chosen 35.0, C chosen 0.0 → total 60.0
    assert math.isclose(rp.projected_total, 60.0, rel_tol=1e-9, abs_tol=1e-9)

    # Check rationales
    rationale_map = {p.player_id: p.rationale for p in rp.starters_breakdown}
    assert rationale_map[pA].startswith("in_progress & live < forecast")
    assert rationale_map[pB].startswith("in_progress & live ≥ forecast")
    assert rationale_map[pC].startswith("not_started")


def test_finished_uses_live_and_exclude_zero_removes_all_history():
    week = 5
    rid = 2
    p = "P"

    # All zero history → excluded → forecast falls to default_floor (0.0)
    matchups_by_week = {
        2: [_mk_matchup(rid, [p], {p: 0.0})],
        3: [_mk_matchup(rid, [p], {p: 0.0})],
        4: [_mk_matchup(rid, [p], {p: 0.0})],
    }
    current = [_mk_matchup(rid, [p], {p: 12.3})]

    def state_provider(_):
        return "FINISHED"

    rp = compute_roster_projection(
        roster_id=rid,
        week=week,
        matchups_by_week=matchups_by_week,
        current_week_matchups=current,
        get_player_game_state=state_provider,
        exclude_zero_points=True,
        default_floor=0.0,
    )

    assert rp.projected_total == pytest.approx(12.3, rel=1e-9)
    assert rp.starters_breakdown[0].forecast_points == 0.0
    assert rp.starters_breakdown[0].chosen_points == pytest.approx(12.3, rel=1e-9)
    assert rp.starters_breakdown[0].rationale.startswith("finished")


def test_compute_tournament_projection_sums_multiple_rosters():
    week = 3
    r1, r2 = 10, 11
    p1, p2 = "1", "2"

    matchups_by_week = {
        1: [_mk_matchup(r1, [p1], {p1: 10}), _mk_matchup(r2, [p2], {p2: 20})],
        2: [_mk_matchup(r1, [p1], {p1: 20}), _mk_matchup(r2, [p2], {p2: 10})],
    }
    current = [_mk_matchup(r1, [p1], {p1: 0}), _mk_matchup(r2, [p2], {p2: 5})]

    def state_provider(pid: str):
        # r1: NOT_STARTED → uses forecast (normalized weights for 2 games: ~0.666, ~0.333)
        #     forecast ≈ 0.666*20 + 0.333*10 = 16.667
        # r2: IN_PROGRESS live 5 vs forecast ≈ 0.666*10 + 0.333*20 = 13.333 → choose forecast 13.333
        return {p1: "NOT_STARTED", p2: "IN_PROGRESS"}[pid]

    total, breakdowns = compute_tournament_projection(
        roster_ids=[r1, r2],
        week=week,
        matchups_by_week=matchups_by_week,
        current_week_matchups=current,
        get_player_game_state=state_provider,
    )

    assert total == pytest.approx(30.0, rel=1e-9)  # ~16.667 + ~13.333
    assert len(breakdowns) == 2

