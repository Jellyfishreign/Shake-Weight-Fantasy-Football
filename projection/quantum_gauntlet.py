"""
Quantum Gauntlet Projection Module
---------------------------------

Implements an intelligent projection for a roster's starters based on:
- 3-week weighted rolling average per player (most recent → least recent)
- Excluding 0-point games from the averaging window by default (treat as DNP)
- Game state selection rule per starter (NOT_STARTED, IN_PROGRESS, FINISHED)

Public API:
  - compute_roster_projection
  - compute_tournament_projection

This module is intentionally decoupled from Flask and Sleeper-specific models.
It consumes plain dicts consistent with Sleeper's matchup responses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Literal, Iterable, Tuple, Callable, Any

GameState = Literal["NOT_STARTED", "IN_PROGRESS", "FINISHED"]


@dataclass
class PlayerProjection:
    player_id: str
    live_points: float
    forecast_points: float
    game_state: GameState
    chosen_points: float
    rationale: str


@dataclass
class RosterProjection:
    roster_id: int
    starters_breakdown: List[PlayerProjection]
    projected_total: float


def _get_roster_matchup(matchups: List[dict], roster_id: int) -> Optional[dict]:
    """Return the first matchup dict for a given roster_id from the provided list."""
    for matchup in matchups or []:
        try:
            if int(matchup.get("roster_id")) == int(roster_id):
                return matchup
        except Exception:
            continue
    return None


def _get_recent_points(
    player_id: str,
    week: int,
    matchups_by_week: Dict[int, List[dict]],
    lookback: int,
    exclude_zero: bool,
    roster_id: Optional[int] = None,
) -> List[float]:
    """
    Collect the player's points from the previous N weeks (week-1 .. week-lookback).
    If roster_id is provided, prefer the matchup for that roster (faster lookup),
    otherwise scan all matchups for the player points map.
    """
    recent: List[float] = []
    for back in range(1, lookback + 1):
        prior_week = week - back
        if prior_week < 1:
            break
        week_matchups = matchups_by_week.get(prior_week) or []

        points: Optional[float] = None
        if roster_id is not None:
            rm = _get_roster_matchup(week_matchups, roster_id)
            if rm is not None:
                points = (rm.get("players_points") or {}).get(player_id)
        if points is None:
            # Fallback: scan all matchups for this player id (slower but robust)
            for mu in week_matchups:
                pp = mu.get("players_points") or {}
                if player_id in pp:
                    points = pp.get(player_id)
                    break

        if points is None:
            continue
        if exclude_zero and (points == 0 or points == 0.0):
            continue
        recent.append(float(points))

    return recent


def _weighted_avg(values: List[float], weights: Tuple[float, ...]) -> float:
    """
    Compute a weighted average where weights are given from most-recent → least-recent.
    Only the first len(values) weights are used, then normalized.
    Returns 0.0 if values is empty or effective weight sum is 0.
    """
    if not values:
        return 0.0
    use_n = min(len(values), len(weights))
    used_weights = list(weights[:use_n])
    weight_sum = float(sum(used_weights))
    if weight_sum == 0:
        # Avoid division by zero; simple mean as fallback
        return sum(values[:use_n]) / float(use_n)
    # Normalize the used weights to sum to 1
    norm = [w / weight_sum for w in used_weights]
    return sum(v * w for v, w in zip(values[:use_n], norm))


def compute_roster_projection(
    roster_id: int,
    week: int,
    matchups_by_week: Dict[int, List[dict]],
    current_week_matchups: List[dict],
    get_player_game_state: Callable[[str], GameState],
    *,
    weights: Tuple[float, float, float] = (0.6, 0.3, 0.1),
    lookback_weeks: int = 3,
    exclude_zero_points: bool = True,
    default_floor: float = 0.0,
) -> RosterProjection:
    """
    Returns the projected score and per-player breakdown for a roster's starters.
    The projection is a sum across starters of chosen_points according to the
    game-state selection rule described in the module docstring.
    """
    # Locate current week's roster matchup
    roster_matchup = _get_roster_matchup(current_week_matchups, roster_id) or {}
    starters: List[str] = list(roster_matchup.get("starters") or [])
    players_points_current: Dict[str, float] = dict(roster_matchup.get("players_points") or {})

    starters_breakdown: List[PlayerProjection] = []
    running_total: float = 0.0

    for player_id in starters:
        # Gather recent points history excluding zeros if configured
        recent_points = _get_recent_points(
            player_id=player_id,
            week=week,
            matchups_by_week=matchups_by_week,
            lookback=lookback_weeks,
            exclude_zero=exclude_zero_points,
            roster_id=roster_id,
        )

        if not recent_points:
            forecast = float(default_floor)
        else:
            forecast = float(_weighted_avg(recent_points, weights))

        # Current week live points and state
        live_points = float(players_points_current.get(player_id, 0.0))
        game_state = get_player_game_state(player_id)

        # Selection rule
        if game_state == "NOT_STARTED":
            chosen = forecast
            rationale = "not_started → forecast"
        elif game_state == "IN_PROGRESS":
            if live_points < forecast:
                chosen = forecast
                rationale = "in_progress & live < forecast → forecast"
            else:
                chosen = live_points
                rationale = "in_progress & live ≥ forecast → live"
        else:  # FINISHED
            chosen = live_points
            rationale = "finished → final live"

        starters_breakdown.append(
            PlayerProjection(
                player_id=player_id,
                live_points=round(live_points, 2),
                forecast_points=round(forecast, 2),
                game_state=game_state,
                chosen_points=round(chosen, 2),
                rationale=rationale,
            )
        )
        running_total += chosen

    return RosterProjection(
        roster_id=int(roster_id),
        starters_breakdown=starters_breakdown,
        projected_total=round(running_total, 2),
    )


def compute_tournament_projection(
    roster_ids: Iterable[int],
    *,
    week: int,
    matchups_by_week: Dict[int, List[dict]],
    current_week_matchups: List[dict],
    get_player_game_state: Callable[[str], GameState],
    weights: Tuple[float, float, float] = (0.6, 0.3, 0.1),
    lookback_weeks: int = 3,
    exclude_zero_points: bool = True,
    default_floor: float = 0.0,
) -> Tuple[float, List[RosterProjection]]:
    """
    Compute projections for multiple rosters and return the summed total with
    individual roster breakdowns.
    """
    breakdowns: List[RosterProjection] = []
    total: float = 0.0

    for rid in roster_ids:
        rp = compute_roster_projection(
            roster_id=int(rid),
            week=week,
            matchups_by_week=matchups_by_week,
            current_week_matchups=current_week_matchups,
            get_player_game_state=get_player_game_state,
            weights=weights,
            lookback_weeks=lookback_weeks,
            exclude_zero_points=exclude_zero_points,
            default_floor=default_floor,
        )
        breakdowns.append(rp)
        total += rp.projected_total

    return round(total, 2), breakdowns

