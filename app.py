from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import threading
import time
import requests
import gspread
from gspread import Cell
from datetime import datetime, timedelta
import pytz
import json
import re
from typing import List, Dict

from projection.quantum_gauntlet import compute_roster_projection

# ——— GOOGLE SHEETS AUTHENTICATION ———
import os
try:
    # Try to load from environment variable (for deployment)
    creds_json_str = os.environ.get('GOOGLE_SHEETS_CREDS_JSON')
    if creds_json_str:
        import json
        from google.oauth2.service_account import Credentials
        creds_dict = json.loads(creds_json_str)
        creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
        gc = gspread.authorize(creds)
    else:
        # Fallback to local file (for development)
        gc = gspread.service_account(
            r'C:\Users\Seth\Documents\Phython\PyCharm Projects\PythonProject\automating_APIs\Sleeper API\sleeper_gsheet_creds.json'
        )
    
    spreadsheet_key = '1o0I8PKe7FFO7RzFvXZ8I5CSInuZ8wtvunePlNTGTJnY'
    spreadsheet = gc.open_by_key(spreadsheet_key)
    print("[OK] Google Sheets connected successfully")
except Exception as e:
    print(f"Warning: Could not initialize Google Sheets connection: {e}")
    spreadsheet = None

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Allow CORS for GitHub Pages and local development
allowed_origins = [
    "https://jellyfishreign.github.io",
    "https://shake-weight-fantasy.onrender.com",
    "http://localhost:5004",
    "http://127.0.0.1:5004"
]
socketio = SocketIO(app, cors_allowed_origins=allowed_origins)

# Add cache-busting headers and CORS for API endpoints
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
    # Add CORS headers for allowed origins
    origin = request.headers.get('Origin')
    if origin in ['https://jellyfishreign.github.io', 'https://shake-weight-fantasy.onrender.com', 'http://localhost:5004', 'http://127.0.0.1:5004']:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    
    # Add Content Security Policy to allow Socket.IO, Chart.js, and YouTube embeds
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdn.socket.io https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self' wss://shake-weight-fantasy.onrender.com ws://localhost:5004 http://localhost:5004 https://shake-weight-fantasy.onrender.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "img-src 'self' data: https:; "
        "frame-src 'self' https://www.youtube.com; "
        "frame-ancestors 'none';"
    )
    response.headers["Content-Security-Policy"] = csp
    
    return response

# Global variables to store the latest data
latest_data = {
    'timestamp': '',
    'week14': {},
    'week15': {},
    'week16': {},
    'week17': {},
    'combined': {},
    'standings': [],
    'initial_standings': []
}

def fmt(x):
    return f"{x:.2f}" if isinstance(x, (int, float)) else x

def fetch_playoff_data():
    """Fetch and process playoff data from Sleeper API"""
    try:
        print("[UPDATE] Fetching playoff data...")
        # ——— CONFIGURATION ———
        username = "LactatingLtinas"
        season = "2025"
        target_league_name = "The Shake Weight Fantasy League"
        weeks_pre = list(range(1, 9))  # Weeks 1–8 (TESTING: normally 1-13)
        w14, w15, w16, w17 = 9, 10, 11, 12  # TESTING: Playoff rounds (normally 14, 15, 16, 17)

        # ——— FETCH USER & LEAGUE ———
        print(f"[INFO] Looking up user: {username}")
        user_resp = requests.get(f"https://api.sleeper.app/v1/user/{username}")
        user_resp.raise_for_status()
        user_id = user_resp.json()["user_id"]
        print(f"[OK] Found user ID: {user_id}")

        print(f"[INFO] Fetching leagues for season {season}...")
        leagues = requests.get(f"https://api.sleeper.app/v1/user/{user_id}/leagues/nfl/{season}").json()
        print(f"[INFO] Found {len(leagues)} leagues")
        for league in leagues:
            print(f"   - {league.get('name', 'Unknown')}")
        
        league_id = next((L["league_id"] for L in leagues if L.get("name")==target_league_name), None)
        if not league_id:
            print(f"[ERROR] League '{target_league_name}' not found in available leagues")
            raise RuntimeError(f"League '{target_league_name}' not found.")
        print(f"[OK] Found league ID: {league_id}")

        # ——— BUILD ROSTER ↔ TEAM MAP ———
        rosters = requests.get(f"https://api.sleeper.app/v1/league/{league_id}/rosters").json()
        roster_to_owner = {r["roster_id"]: r["owner_id"] for r in rosters}
        users = requests.get(f"https://api.sleeper.app/v1/league/{league_id}/users").json()
        owner_to_name = {u["user_id"]: (u.get("metadata",{}).get("team_name") or u["display_name"]) for u in users}
        roster_to_name = {rid: owner_to_name.get(owner_id,f"Roster {rid}") for rid,owner_id in roster_to_owner.items()}

        # ——— PULL SCORES FOR ALL WEEKS ———
        print("[INFO] Fetching scores for all weeks...")
        scores = {rid:{} for rid in roster_to_name}
        # Store raw matchup dictionaries by week for projection module
        matchups_by_week: Dict[int, List[dict]] = {}
        for wk in weeks_pre + [w14, w15, w16, w17]:
            print(f"   Week {wk}...")
            resp = requests.get(f"https://api.sleeper.app/v1/league/{league_id}/matchups/{wk}")
            resp.raise_for_status()
            matchups = resp.json()
            print(f"     Found {len(matchups)} matchups")
            matchups_by_week[wk] = matchups
            for m in matchups:
                scores[m["roster_id"]][wk] = m.get("points",0.0)
        print(f"[OK] Scores loaded for {len(scores)} rosters")

        # ——— FETCH MATCHUP DATA FOR WIN/LOSS RECORDS ———
        print("[INFO] Calculating win/loss records...")
        team_records = {rid: {'wins': 0, 'losses': 0, 'weekly_records': []} for rid in roster_to_name}

        for week in range(1, 14):  # Regular season weeks 1-13
            resp = requests.get(f"https://api.sleeper.app/v1/league/{league_id}/matchups/{week}")
            resp.raise_for_status()
            matchups = resp.json()
            
            # Group matchups by matchup_id to find head-to-head results
            matchup_groups = {}
            for m in matchups:
                mid = m.get('matchup_id')
                if mid not in matchup_groups:
                    matchup_groups[mid] = []
                matchup_groups[mid].append(m)
            
            # Determine winners for each matchup
            for matchup_list in matchup_groups.values():
                if len(matchup_list) == 2:  # Head-to-head matchup
                    team1, team2 = matchup_list
                    if team1.get('points', 0) > team2.get('points', 0):
                        team_records[team1['roster_id']]['wins'] += 1
                        team_records[team2['roster_id']]['losses'] += 1
                    else:
                        team_records[team2['roster_id']]['wins'] += 1
                        team_records[team1['roster_id']]['losses'] += 1
            
            # Store weekly record snapshot
            for rid in team_records:
                team_records[rid]['weekly_records'].append({
                    'week': week,
                    'wins': team_records[rid]['wins'],
                    'losses': team_records[rid]['losses']
                })

        print(f"[OK] Win/loss records calculated for {len(team_records)} teams")

        # ——— COMPUTE PRE-TOTAL & INITIAL SEED ———
        print("[INFO] Computing playoff standings...")
        results = []
        for rid, team in roster_to_name.items():
            pre_total = sum(scores[rid].get(w,0.0) for w in weeks_pre)
            results.append({
                "roster_id": rid, "team": team, "pre_total": pre_total,
                "wk14": scores[rid].get(w14,0.0),
                "wk15": scores[rid].get(w15,0.0),
                "wk16": scores[rid].get(w16,0.0),
                "wk17": scores[rid].get(w17,0.0),
                "weekly_records": team_records[rid]['weekly_records'],
                "all_weekly_scores": [scores[rid].get(w, 0) for w in range(1, 18)]
            })
        results.sort(key=lambda r:r["pre_total"], reverse=True)
        for idx, r in enumerate(results, start=1):
            r["orig_seed"] = idx
        print(f"[OK] Processed {len(results)} teams")
        for r in results[:5]:  # Show top 5
            print(f"   #{r['orig_seed']}: {r['team']} - {r['pre_total']:.2f}")

        # ——— IDENTIFY WILDCARD WINNER ———
        print("[INFO] Identifying wildcard winner...")
        wildcards = [r for r in results if 7<=r["orig_seed"]<=12]
        wildcard_winner = max(wildcards, key=lambda r:r["wk14"]) if wildcards else None
        if wildcard_winner:
            print(f"   Wildcard winner: {wildcard_winner['team']}")
        else:
            print("   No wildcard winner found")

        # ——— ASSIGN ROUND 1 POSITIONS ———
        print("[INFO] Assigning playoff positions...")
        for r in results:
            seed=r["orig_seed"]
            if seed<=2: 
                r["position"]="Bye"
                print(f"   #{seed} {r['team']}: Bye")
            elif seed<=6: 
                r["position"]="Playoff"
                print(f"   #{seed} {r['team']}: Playoff")
            else: 
                r["position"]="Wildcard Winner" if r is wildcard_winner else "Toliet Bowl"
                print(f"   #{seed} {r['team']}: {r['position']}")

        # ——— BUILD LISTS ———
        bye_list = [r for r in results if r["position"]=="Bye"]
        playoff_list = sorted([r for r in results if r["position"]=="Playoff"], key=lambda r:r["wk14"], reverse=True)
        wildcard_list = sorted([r for r in results if r["position"] in ("Wildcard Winner","Toliet Bowl")],
                              key=lambda r:r["wk14"], reverse=True)

        # Week 14: top/low bye, top4 playoff, all wildcard
        top_bye = max(bye_list, key=lambda r:r["wk14"])
        low_bye = min(bye_list, key=lambda r:r["wk14"])

        # Week15 lists
        top_bye15 = max(bye_list, key=lambda r:r["wk15"])
        low_bye15 = min(bye_list, key=lambda r:r["wk15"])
        playoff15 = [r for r in results if 3<=r["orig_seed"]<=6]
        if wildcard_winner: playoff15.append(wildcard_winner)
        playoff15_sorted = sorted(playoff15, key=lambda r:r["wk15"], reverse=True)[:5]
        wild15_sorted = sorted([r for r in wildcard_list if r is not wildcard_winner],
                              key=lambda r:r["wk15"], reverse=True)[:5]

        # Combined Week14+15
        for r in bye_list: r["combined"]=r["wk14"]+r["wk15"]
        for r in playoff15: r["combined"]=r["wk14"]+r["wk15"]
        for r in wildcard_list: r["combined"]=r["wk14"]+r["wk15"]
        top_bye_comb = max(bye_list, key=lambda r:r["combined"])
        low_bye_comb = min(bye_list, key=lambda r:r["combined"])
        playoff_comb = sorted(playoff15, key=lambda r:r["combined"], reverse=True)[:5]
        wild_comb_sorted = sorted([r for r in wildcard_list if r is not wildcard_winner],
                                  key=lambda r:r["combined"], reverse=True)[:5]

        # Week16 lists
        conf_list = bye_list + sorted(playoff_comb, key=lambda r:r["wk16"], reverse=True)[:3]
        conf_sorted = sorted(conf_list, key=lambda r:r["wk16"], reverse=True)
        purg_list = sorted(playoff_comb, key=lambda r:r["wk16"])[:2] + \
                    [sorted(wildcard_list, key=lambda r:r["wk16"], reverse=True)[1]]
        purg_sorted = sorted(purg_list, key=lambda r:r["wk16"], reverse=True)
        toilet_sorted = sorted(results, key=lambda r:r["wk16"])[:4]
        toilet_sorted = sorted(toilet_sorted, key=lambda r:r["wk16"], reverse=True)

        # Week17 lists
        conf_top3 = conf_sorted[:3]
        conf_top3_sorted = sorted(conf_top3, key=lambda r: r["wk17"], reverse=True)
        bottom2_conf16 = sorted(conf_list, key=lambda r: r["wk16"])[:2]
        
        # Build toilet_list for Week 17 calculations
        remaining_wild = [r for r in wildcard_list if r["roster_id"] not in {t["roster_id"] for t in conf_list + purg_list}]
        toilet_list = sorted(remaining_wild, key=lambda r: r["wk15"])[:4]
        
        toilet_top16 = sorted(toilet_list, key=lambda r: r["wk16"], reverse=True)[0] if toilet_list else None
        purg17_list = purg_list + bottom2_conf16 + ([toilet_top16] if toilet_top16 else [])
        purg17_sorted = sorted(purg17_list, key=lambda r: r["wk17"], reverse=True)
        exclude_ids = {t["roster_id"] for t in conf_top3 + purg17_list}
        toilet_candidates = [r for r in wildcard_list if r["roster_id"] not in exclude_ids]
        toilet_bottom3_16 = sorted(toilet_candidates, key=lambda r: r["wk16"])[:3]
        toilet17_sorted = sorted(toilet_bottom3_16, key=lambda r: r["wk17"], reverse=True)

        # Prepare data for frontend
        global latest_data
        central_tz = pytz.timezone('America/Chicago')
        current_time = datetime.now(central_tz).strftime("%m/%d/%Y %H:%M CST")
        
        # ——— CALCULATE PAYOUTS DATA ———
        print("[INFO] Calculating payout data...")
        
        # Determine which weeks are complete based on current date
        # NFL weeks end on Monday night, we consider them complete starting Tuesday
        # Week 1 starts Sep 4, 2025 (Thursday)
        # Each week is 7 days, ending on Monday night
        # We mark as complete on Tuesday (2 days after Sunday of that week)
        
        now = datetime.now(central_tz)
        
        # NFL 2025 season start date (Week 1 Thursday, Sep 4, 2025)
        # Adjust this to match actual 2025 NFL season start
        season_start = central_tz.localize(datetime(2025, 9, 4))
        
        # Calculate which week we're in and which weeks are complete
        # NFL weeks run Thursday-Monday with games primarily on Sunday
        # Week is considered complete starting Tuesday after Monday Night Football
        days_since_start = (now - season_start).days
        current_nfl_week = (days_since_start // 7) + 1
        
        # Determine the latest fully completed week
        # Each week starts on Thursday and is complete 5 days later (following Tuesday)
        # Example: Week 1 starts Thu Sep 4, complete Tue Sep 9 (5 days later)
        latest_completed_week = 0
        for week in range(1, 18):
            # Week starts on Thursday of that week
            week_start = season_start + timedelta(weeks=week-1)
            # Week is complete 5 days after Thursday start (= Tuesday)
            week_complete_date = week_start + timedelta(days=5)
            
            if now >= week_complete_date:
                latest_completed_week = week
            else:
                break
        
        print(f"[INFO] Current date: {now.strftime('%Y-%m-%d %H:%M')}")
        print(f"[INFO] Current NFL week in progress: {current_nfl_week}")
        print(f"[INFO] Latest completed week: {latest_completed_week}")
        
        # For tournament display, we want to show the current week even if not complete
        # This allows real-time scores during games
        current_week_for_display = current_nfl_week if current_nfl_week <= 17 else 17
        
        # Weekly high scores (only for completed weeks 1-8) - TESTING: normally 1-13
        weekly_winners = {}
        for week in range(1, min(9, latest_completed_week + 1)):
            week_scores = [(r['team'], scores[r['roster_id']].get(week, 0)) for r in results]
            # Only add if there are actual scores
            if any(score > 0 for _, score in week_scores):
                winner_team, winner_score = max(week_scores, key=lambda x: x[1])
                weekly_winners[week] = {
                    'team': winner_team,
                    'score': winner_score,
                    'week': week,
                    'payout': 25,
                    'date': ''  # Can be populated with actual dates if needed
                }
        
        # Season high score (only if week 8 is complete) - TESTING: normally week 13
        season_high_score = None
        if latest_completed_week >= 8:
            season_high_team = max(results, key=lambda r: r['pre_total'])
            season_high_score = {
                'team': season_high_team['team'],
                'totalScore': season_high_team['pre_total'],
                'payout': 75,
                'date': ''
            }
        
        # Duel of Fates (only if week 10 is complete) - TESTING: normally week 15
        duel_of_fates = {}
        if latest_completed_week >= 10 and len(bye_list) >= 2:
            bye_teams_sorted = sorted(bye_list, key=lambda r: r.get("combined", 0), reverse=True)
            
            # Calculate payout based on winning margin
            winner_score = bye_teams_sorted[0].get("combined", 0)
            loser_score = bye_teams_sorted[1].get("combined", 0)
            margin = abs(winner_score - loser_score)
            
            # Payout tiers based on margin
            if margin <= 7.5:
                win_payout, lose_payout = 60, 40
            elif margin <= 15:
                win_payout, lose_payout = 70, 30
            elif margin <= 23.5:
                win_payout, lose_payout = 80, 20
            elif margin <= 30:
                win_payout, lose_payout = 90, 10
            else:
                win_payout, lose_payout = 100, 0
            
            print(f"[INFO] Duel of Fates margin: {margin:.2f} points -> ${win_payout}/${lose_payout}")
            
            duel_of_fates[bye_teams_sorted[0]['team']] = {
                'team': bye_teams_sorted[0]['team'],
                'payout': win_payout,
                'category': 'Duel of the Fates Winner',
                'date': ''
            }
            duel_of_fates[bye_teams_sorted[1]['team']] = {
                'team': bye_teams_sorted[1]['team'],
                'payout': lose_payout,
                'category': 'Duel of the Fates Runner-up',
                'date': ''
            }
        
        # Champion (only if week 12 is complete) - TESTING: normally week 17
        champion = None
        if latest_completed_week >= 12 and conf_top3_sorted:
            champion_team = conf_top3_sorted[0]
            champion = {
                'team': champion_team['team'],
                'payout': 700,
                'date': ''
            }
        
        payouts_data = {
            'weeklyWinners': weekly_winners,
            'seasonHighScore': season_high_score,
            'duelOfFates': duel_of_fates,
            'champion': champion,
            'lastUpdated': current_time,
            'currentWeek': latest_completed_week,  # For payout display (completed only)
            'currentWeekInProgress': current_week_for_display  # For tournament display (includes in-progress)
        }
        print(f"[OK] Payouts calculated: {len(weekly_winners)} weekly winners for completed weeks")
        print(f"[INFO] Tournament will show data through week {current_week_for_display} (including in-progress)")
        
        # Calculate projected scores and payouts
        def calculate_projected_score(team, week):
            """Compute intelligent projection for the given roster and target week."""
            roster_id = team.get("roster_id")
            if not roster_id:
                return 0.0

            current_week_matchups = matchups_by_week.get(week, [])

            # Default heuristic: if a player shows > 0 points this week → IN_PROGRESS; else NOT_STARTED
            # We cannot reliably distinguish FINISHED without a schedule feed, so keep provider pluggable.
            # This can be replaced later by injecting a real schedule-aware provider.
            players_points_lookup = {}
            rm = next((m for m in current_week_matchups if m.get("roster_id") == roster_id), None)
            if rm is not None:
                players_points_lookup = rm.get("players_points") or {}

            def get_player_game_state(player_id: str):
                live = float(players_points_lookup.get(player_id, 0.0))
                if live > 0.0:
                    return "IN_PROGRESS"
                return "NOT_STARTED"

            rp = compute_roster_projection(
                roster_id=roster_id,
                week=week,
                matchups_by_week=matchups_by_week,
                current_week_matchups=current_week_matchups,
                get_player_game_state=get_player_game_state,
                weights=(0.6, 0.3, 0.1),
                lookback_weeks=3,
                exclude_zero_points=True,
                default_floor=0.0,
            )
            return rp.projected_total

        def get_next_week(team, current_week):
            """Determine next week assignment based on current week and performance"""
            if current_week == 15:
                if team in bye_list:
                    return "Conf Champ"
                elif team in playoff15_sorted[:3]:
                    return "Conf Champ"
                else:
                    return "Purgatory"
            elif current_week == 16:
                if team in conf_sorted[:3]:
                    return "Superbowl"
                else:
                    return "Purgatory"
            elif current_week == 17:
                if team in conf_top3_sorted[:1]:
                    return "Champion"
                else:
                    return "Purgatory"
            return ""

        def get_payout(team, current_week):
            """Calculate payout based on performance and week"""
            if current_week == 15:
                if team in bye_list:
                    # For Duel of the Fates (bye teams), calculate based on winning margin
                    if len(bye_list) >= 2:
                        # Get the two bye teams and their combined scores
                        bye_teams = sorted(bye_list, key=lambda r: r["combined"], reverse=True)
                        winner = bye_teams[0]
                        loser = bye_teams[1]
                        
                        if team == winner:
                            # Calculate winning margin
                            margin = winner["combined"] - loser["combined"]
                            
                            # Apply winning margin rules
                            if margin <= 7.5:
                                return "$60.00"
                            elif margin <= 15:
                                return "$70.00"
                            elif margin <= 23.5:
                                return "$80.00"
                            elif margin <= 30:
                                return "$90.00"
                            else:
                                return "$100.00"
                        elif team == loser:
                            # Calculate winning margin
                            margin = winner["combined"] - loser["combined"]
                            
                            # Apply winning margin rules
                            if margin <= 7.5:
                                return "$40.00"
                            elif margin <= 15:
                                return "$30.00"
                            elif margin <= 23.5:
                                return "$20.00"
                            elif margin <= 30:
                                return "$10.00"
                            else:
                                return "$0.00"
                    
                    # Fallback for single team
                    return "$60.00" if team == top_bye15 else "$40.00"
                else:
                    return "$-"
            elif current_week == 17:
                if team in conf_top3_sorted[:1]:
                    return "$700.00"
                else:
                    return "$-"
            return "$-"

        # After calculating results and before building latest_data, add initial standings
        initial_standings = []
        for idx, r in enumerate(results, start=1):
            initial_standings.append({
                'seed': idx,
                'team': r['team'],
                'position': r['position'],
                'pre_total': fmt(r['pre_total'])
            })

        # Create toilet bowl data for Week 15 (all wildcard teams except the winner)
        toilet_bowl_teams = [r for r in wildcard_list if r is not wildcard_winner]
        
        # Fix the playoff result logic - top 3 should get Conf Champ
        playoff_result_sorted = sorted(playoff_comb, key=lambda r: r["combined"], reverse=True)
        
        # Build week15 data first
        week15_data = {
            'bye': [{'team': f"({top_bye15['orig_seed']}) {top_bye15['team']}", 'score': fmt(top_bye15["wk15"])}, 
                   {'team': f"({low_bye15['orig_seed']}) {low_bye15['team']}", 'score': fmt(low_bye15["wk15"])}],
            'playoff': [{'team': f"({t['orig_seed']}) {t['team']}", 'score': fmt(t["wk15"])} for t in playoff15_sorted],
            'toilet': [{'team': f"({t['orig_seed']}) {t['team']}", 'score': fmt(t["wk15"])} for t in toilet_bowl_teams],
            'bye_result': [
                {
                    'team': f"({t['orig_seed']}) {t['team']}",
                    'proj_score': fmt(calculate_projected_score(t, 15)),
                    'score': fmt(calculate_projected_score(t, 15)),
                    'next_week': get_next_week(t, 15),
                    'payout': get_payout(t, 15)
                } for t in bye_list
            ],
            'playoff_result': [
                {
                    'team': f"({t['orig_seed']}) {t['team']}",
                    'proj_score': fmt(calculate_projected_score(t, 15)),
                    'score': fmt(t["combined"]),
                    'next_week': "Conf Champ" if idx < 3 else "Purgatory",
                    'payout': get_payout(t, 15)
                } for idx, t in enumerate(playoff_result_sorted)
            ],
            'toilet_result': [
                {
                    'team': f"({t['orig_seed']}) {t['team']}",
                    'proj_score': fmt(calculate_projected_score(t, 15)),
                    'score': fmt(t["combined"]),
                    'next_week': "Purgatory" if idx == 0 else "Toilet Bowl",
                    'payout': get_payout(t, 15)
                } for idx, t in enumerate(wild_comb_sorted)
            ]
        }
        
        # Get teams that should be in conference championship (store roster_id for lookup)
        conf_champ_roster_ids = set()
        for result in week15_data['playoff_result']:
            if result['next_week'] == 'Conf Champ':
                # Extract roster_id from team string: "(seed) Team Name"
                team_str = result['team']
                for t in results:
                    if f"({t['orig_seed']}) {t['team']}" == team_str:
                        conf_champ_roster_ids.add(t['roster_id'])
        for result in week15_data['bye_result']:
            if result['next_week'] == 'Conf Champ':
                team_str = result['team']
                for t in results:
                    if f"({t['orig_seed']}) {t['team']}" == team_str:
                        conf_champ_roster_ids.add(t['roster_id'])
        
        # Conference Championship: all Conf Champ teams, sorted by wk16 score
        conf_champ_teams = [t for t in results if t['roster_id'] in conf_champ_roster_ids]
        conf_champ_sorted = sorted(conf_champ_teams, key=lambda t: t['wk16'], reverse=True)
        conference_rows = []
        for idx, t in enumerate(conf_champ_sorted):
            next_week = 'Superbowl' if idx < 3 else 'Purgatory'
            conference_rows.append({
                'team': f"({t['orig_seed']}) {t['team']}",
                'proj_score': fmt(calculate_projected_score(t, 16)),
                'score': fmt(t['wk16']),
                'next_week': next_week
            })

        # Purgatory: all teams with Purgatory in next_week from BOTH week15 playoff_result and toilet_result
        purgatory_roster_ids = set()
        for result in week15_data['playoff_result']:
            if result['next_week'] == 'Purgatory':
                team_str = result['team']
                for t in results:
                    if f"({t['orig_seed']}) {t['team']}" == team_str:
                        purgatory_roster_ids.add(t['roster_id'])
        for result in week15_data['toilet_result']:
            if result['next_week'] == 'Purgatory':
                team_str = result['team']
                for t in results:
                    if f"({t['orig_seed']}) {t['team']}" == team_str:
                        purgatory_roster_ids.add(t['roster_id'])
        purgatory_teams = [t for t in results if t['roster_id'] in purgatory_roster_ids]
        purgatory_sorted = sorted(purgatory_teams, key=lambda t: t['wk16'], reverse=True)
        purgatory_rows = []
        for t in purgatory_sorted:
            purgatory_rows.append({
                'team': f"({t['orig_seed']}) {t['team']}",
                'proj_score': fmt(calculate_projected_score(t, 16)),
                'score': fmt(t['wk16']),
                'next_week': 'Purgatory'
            })

        def normalize_team_string(s):
            # Extract seed and name, ignore whitespace/case
            m = re.match(r"\((\d+)\)\s*(.*)", s.strip())
            if m:
                seed, name = m.groups()
                return int(seed), name.strip().lower()
            return None, s.strip().lower()

        # Toilet Bowl: all teams from toilet_result except the top scorer (index 0)
        toilet_bowl_roster_ids = set()
        # Skip the first team (top scorer) from toilet_result, include all others
        for result in week15_data['toilet_result'][1:]:  # Skip index 0 (top scorer)
            seed, name = normalize_team_string(result['team'])
            for t in results:
                if t['orig_seed'] == seed and t['team'].strip().lower() == name:
                    toilet_bowl_roster_ids.add(t['roster_id'])
        toilet_bowl_teams = [t for t in results if t['roster_id'] in toilet_bowl_roster_ids]
        toilet_bowl_sorted = sorted(toilet_bowl_teams, key=lambda t: t['wk16'], reverse=True)
        toilet_rows = []
        for idx, t in enumerate(toilet_bowl_sorted):
            next_week = 'Purgatory' if idx == 0 else 'Toilet Bowl'
            toilet_rows.append({
                'team': f"({t['orig_seed']}) {t['team']}",
                'proj_score': fmt(calculate_projected_score(t, 16)),
                'score': fmt(t['wk16']),
                'next_week': next_week
            })

        latest_data = {
            'timestamp': current_time,
            'payouts': payouts_data,
            'week14': {
                'bye': [{'team': f"({top_bye['orig_seed']}) {top_bye['team']}", 'score': fmt(top_bye["wk14"])}, 
                       {'team': f"({low_bye['orig_seed']}) {low_bye['team']}", 'score': fmt(low_bye["wk14"])}],
                'playoff': [{'team': f"({t['orig_seed']}) {t['team']}", 'score': fmt(t["wk14"])} for t in playoff_list[:4]],
                'wildcard': [{'team': f"({t['orig_seed']}) {t['team']}", 'score': fmt(t["wk14"])} for t in wildcard_list]
            },
            'week15': week15_data,
            'week16': {
                'conference': conference_rows,
                'purgatory': purgatory_rows,
                'toilet': toilet_rows
            },
            'week17': {
                'championship': [
                    {
                        'team': f"({t['orig_seed']}) {t['team']}", 
                        'proj_score': fmt(calculate_projected_score(t, 17)),
                        'score': fmt(t["wk17"]),
                        'final_result': "Champion" if idx == 0 else "Purgatory",
                        'payout': get_payout(t, 17)
                    } for idx, t in enumerate(sorted([t for t in conf_champ_sorted if any(result['team'] == f"({t['orig_seed']}) {t['team']}" and result['next_week'] == 'Superbowl' for result in conference_rows)], key=lambda t: t['wk17'], reverse=True))
                ],
                'purgatory': [
                    {
                        'team': f"({t['orig_seed']}) {t['team']}", 
                        'proj_score': fmt(calculate_projected_score(t, 17)),
                        'score': fmt(t["wk17"]),
                        'final_result': "Purgatory",
                        'payout': get_payout(t, 17)
                    } for t in sorted([t for t in results if any(result['team'] == f"({t['orig_seed']}) {t['team']}" and result['next_week'] == 'Purgatory' for result in conference_rows + purgatory_rows + toilet_rows)], key=lambda t: t['wk17'], reverse=True)
                ],
                'toilet': [
                    {
                        'team': f"({t['orig_seed']}) {t['team']}", 
                        'proj_score': fmt(calculate_projected_score(t, 17)),
                        'score': fmt(t["wk17"]),
                        'final_result': "Toilet Bowl",
                        'payout': get_payout(t, 17)
                    } for t in sorted(toilet17_sorted, key=lambda t: t['wk17'], reverse=True)
                ]
            },
            'standings': [{'seed': r['orig_seed'], 'team': r['team'], 'position': r['position'], 'pre_total': fmt(r['pre_total'])} for r in results],
            'initial_standings': initial_standings,
            'the_run': {
                'teams': [
                    {
                        'team': r['team'],
                        'seed': r['orig_seed'],
                        'weekly_records': r['weekly_records'],
                        'all_weekly_scores': r['all_weekly_scores'],
                        'position': r['position'],
                        'playoff_scores': {
                            'wk14': r['wk14'],
                            'wk15': r['wk15'], 
                            'wk16': r['wk16'],
                            'wk17': r['wk17']
                        }
                    } for r in results
                ],
                'playoff_results': {
                    'week15': week15_data,
                    'week16': {
                        'conference': conference_rows,
                        'purgatory': purgatory_rows,
                        'toilet': toilet_rows
                    },
                    'week17': {
                        'championship': [
                            {
                                'team': f"({t['orig_seed']}) {t['team']}", 
                                'proj_score': fmt(calculate_projected_score(t, 17)),
                                'score': fmt(t["wk17"]),
                                'final_result': "Champion" if idx == 0 else "Purgatory",
                                'payout': get_payout(t, 17)
                            } for idx, t in enumerate(sorted([t for t in conf_champ_sorted if any(result['team'] == f"({t['orig_seed']}) {t['team']}" and result['next_week'] == 'Superbowl' for result in conference_rows)], key=lambda t: t['wk17'], reverse=True))
                        ],
                        'purgatory': [
                            {
                                'team': f"({t['orig_seed']}) {t['team']}", 
                                'proj_score': fmt(calculate_projected_score(t, 17)),
                                'score': fmt(t["wk17"]),
                                'final_result': "Purgatory",
                                'payout': get_payout(t, 17)
                            } for t in sorted([t for t in results if any(result['team'] == f"({t['orig_seed']}) {t['team']}" and result['next_week'] == 'Purgatory' for result in conference_rows + purgatory_rows + toilet_rows)], key=lambda t: t['wk17'], reverse=True)
                        ],
                        'toilet': [
                            {
                                'team': f"({t['orig_seed']}) {t['team']}", 
                                'proj_score': fmt(calculate_projected_score(t, 17)),
                                'score': fmt(t["wk17"]),
                                'final_result': "Toilet Bowl",
                                'payout': get_payout(t, 17)
                            } for t in sorted(toilet17_sorted, key=lambda t: t['wk17'], reverse=True)
                        ]
                    }
                }
            }
        }
        
        # Emit updated data to all connected clients
        print("[INFO] Data processed successfully, emitting to clients...")
        print(f"[INFO] Timestamp being sent: {latest_data['timestamp']}")
        socketio.emit('data_update', latest_data)
        print("[OK] Data update complete")
        
    except Exception as e:
        print(f"[ERROR] Error fetching data: {e}")
        import traceback
        traceback.print_exc()
        socketio.emit('error', {'message': str(e)})

def background_update():
    """Background thread to continuously update data"""
    while True:
        fetch_playoff_data()
        time.sleep(3600)  # Update every hour

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data')
def get_data():
    return jsonify(latest_data)

# Temporary static snapshot endpoint for front-end hosting convenience
@app.route('/data_snapshot.json')
def data_snapshot():
    return jsonify(latest_data)

@app.route('/api/idp-scoring')
def get_idp_scoring():
    """Fetch IDP Scoring data from Google Sheet"""
    try:
        # Check if spreadsheet connection is available
        if spreadsheet is None:
            return jsonify({
                'success': False,
                'error': 'Google Sheets connection not available'
            })
        
        # Get the IDP Scoring worksheet
        idp_worksheet = spreadsheet.worksheet("IDP Scoring")
        
        # Get all values from the worksheet
        all_values = idp_worksheet.get_all_values()
        
        # Convert to list of dictionaries (assuming first row is headers)
        if all_values:
            headers = all_values[0]
            data = []
            for row in all_values[1:]:
                # Pad row to match header length
                while len(row) < len(headers):
                    row.append("")
                data.append(dict(zip(headers, row)))
            
            return jsonify({
                'success': True,
                'data': data,
                'headers': headers
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No data found in IDP Scoring worksheet'
            })
            
    except gspread.exceptions.WorksheetNotFound:
        return jsonify({
            'success': False,
            'error': 'IDP Scoring worksheet not found'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error fetching IDP Scoring data: {str(e)}'
        })

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    print(f'Sending initial data with timestamp: {latest_data.get("timestamp", "No timestamp")}')
    
    # If no data is available yet, trigger a fresh fetch
    if not latest_data.get('timestamp'):
        print('No data available, triggering fresh fetch...')
        fetch_playoff_data()
    
    emit('data_update', latest_data)

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

if __name__ == '__main__':
    # Initial data fetch before starting the server
    print("Starting application...")
    fetch_playoff_data()
    
    # Start background update thread
    update_thread = threading.Thread(target=background_update, daemon=True)
    update_thread.start()
    
    # Get port from environment variable (for cloud hosting) or default to 5004
    import os
    port = int(os.environ.get('PORT', 5004))
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    # Run the app (allow_unsafe_werkzeug needed for Render deployment)
    socketio.run(app, debug=debug_mode, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
