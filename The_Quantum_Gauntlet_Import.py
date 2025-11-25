import requests
import gspread
from gspread import Cell
from datetime import datetime
import pytz

# ——— AUTHENTICATION ———
gc = gspread.service_account(
    r'C:\Users\Seth\Documents\Phython\PyCharm Projects\PythonProject\automating_APIs\Sleeper API\sleeper_gsheet_creds.json'
)
spreadsheet_key = '1o0I8PKe7FFO7RzFvXZ8I5CSInuZ8wtvunePlNTGTJnY'
spreadsheet     = gc.open_by_key(spreadsheet_key)
try:
    ws = spreadsheet.worksheet("The_Quantum_Gauntlet")
except gspread.exceptions.WorksheetNotFound:
    print("Error: Worksheet 'The_Quantum_Gauntlet' not found.")
    exit()

# ——— ADD TIMESTAMP TO A1 ———
central_tz = pytz.timezone('America/Chicago')
current_time = datetime.now(central_tz).strftime("%m/%d/%Y %H:%M CST")
timestamp_cell = Cell(1, 1, f"Last Update: {current_time}")
ws.update_cells([timestamp_cell])
print(f"Timestamp updated: Last Update: {current_time}")

# ——— CONFIGURATION ———
username           = "LactatingLtinas"
season             = "2025"
target_league_name = "The Shake Weight Fantasy League"
weeks_pre          = list(range(1, 14))  # Weeks 1–13
w14, w15, w16, w17 = 14, 15, 16, 17     # Playoff rounds

# ——— HELPER ———
def fmt(x):
    return f"{x:.2f}" if isinstance(x, (int, float)) else x

# ——— FETCH USER & LEAGUE ———
user_resp = requests.get(f"https://api.sleeper.app/v1/user/{username}")
user_resp.raise_for_status()
user_id = user_resp.json()["user_id"]

leagues = requests.get(f"https://api.sleeper.app/v1/user/{user_id}/leagues/nfl/{season}").json()
league_id = next((L["league_id"] for L in leagues if L.get("name")==target_league_name), None)
if not league_id:
    raise RuntimeError(f"League '{target_league_name}' not found.")

# ——— BUILD ROSTER ↔ TEAM MAP ———
rosters = requests.get(f"https://api.sleeper.app/v1/league/{league_id}/rosters").json()
roster_to_owner = {r["roster_id"]: r["owner_id"] for r in rosters}
users = requests.get(f"https://api.sleeper.app/v1/league/{league_id}/users").json()
owner_to_name = {u["user_id"]: (u.get("metadata",{}).get("team_name") or u["display_name"]) for u in users}
roster_to_name = {rid: owner_to_name.get(owner_id,f"Roster {rid}") for rid,owner_id in roster_to_owner.items()}

# ——— PULL SCORES FOR ALL WEEKS ———
scores = {rid:{} for rid in roster_to_name}
for wk in weeks_pre + [w14, w15, w16, w17]:
    resp = requests.get(f"https://api.sleeper.app/v1/league/{league_id}/matchups/{wk}")
    resp.raise_for_status()
    for m in resp.json():
        scores[m["roster_id"]][wk] = m.get("points",0.0)

# ——— COMPUTE PRE-TOTAL & INITIAL SEED ———
results = []
for rid, team in roster_to_name.items():
    pre_total = sum(scores[rid].get(w,0.0) for w in weeks_pre)
    results.append({
        "roster_id": rid, "team": team, "pre_total": pre_total,
        "wk14": scores[rid].get(w14,0.0),
        "wk15": scores[rid].get(w15,0.0),
        "wk16": scores[rid].get(w16,0.0),
        "wk17": scores[rid].get(w17,0.0)
    })
results.sort(key=lambda r:r["pre_total"], reverse=True)
for idx, r in enumerate(results, start=1):
    r["orig_seed"] = idx

# ——— IDENTIFY WILDCARD WINNER ———
wildcards = [r for r in results if 7<=r["orig_seed"]<=12]
wildcard_winner = max(wildcards, key=lambda r:r["wk14"]) if wildcards else None

# ——— ASSIGN ROUND 1 POSITIONS ———
for r in results:
    seed=r["orig_seed"]
    if seed<=2: r["position"]="Bye"
    elif seed<=6: r["position"]="Playoff"
    else: r["position"]="Wildcard Winner" if r is wildcard_winner else "Toliet Bowl"

# ——— BUILD LISTS ———
bye_list     = [r for r in results if r["position"]=="Bye"]
playoff_list = sorted([r for r in results if r["position"]=="Playoff"], key=lambda r:r["wk14"], reverse=True)
wildcard_list= sorted([r for r in results if r["position"] in ("Wildcard Winner","Toliet Bowl")],
                      key=lambda r:r["wk14"], reverse=True)

# Week 14: top/low bye, top4 playoff, all wildcard
top_bye= max(bye_list, key=lambda r:r["wk14"])
low_bye= min(bye_list, key=lambda r:r["wk14"])

# Week15 lists
top_bye15= max(bye_list, key=lambda r:r["wk15"])
low_bye15= min(bye_list, key=lambda r:r["wk15"])
playoff15= [r for r in results if 3<=r["orig_seed"]<=6]
if wildcard_winner: playoff15.append(wildcard_winner)
playoff15_sorted = sorted(playoff15, key=lambda r:r["wk15"], reverse=True)[:5]
wild15_sorted    = sorted([r for r in wildcard_list if r is not wildcard_winner],
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
conf_sorted   = sorted(conf_list, key=lambda r:r["wk16"], reverse=True)
purg_list     = sorted(playoff_comb, key=lambda r:r["wk16"])[:2] + \
                [sorted(wildcard_list, key=lambda r:r["wk16"], reverse=True)[1]]
purg_sorted   = sorted(purg_list, key=lambda r:r["wk16"], reverse=True)
toilet_sorted = sorted(results, key=lambda r:r["wk16"])[:4]
toilet_sorted = sorted(toilet_sorted, key=lambda r:r["wk16"], reverse=True)

# ——— BATCH WRITE: Week 14 (individual cells) ———
week14_cells=[]
# top/low bye
week14_cells.append(Cell(5,6, fmt(top_bye["wk14"])))  # F5
week14_cells.append(Cell(5,4, f"({top_bye['orig_seed']}) {top_bye['team']}"))  # D5
week14_cells.append(Cell(6,6, fmt(low_bye["wk14"])))  # F6
week14_cells.append(Cell(6,4, f"({low_bye['orig_seed']}) {low_bye['team']}"))  # D6
# playoff top4
for i, team in enumerate(playoff_list[:4]):
    r=10+i
    week14_cells.append(Cell(r,6, fmt(team["wk14"])))
    week14_cells.append(Cell(r,4, f"({team['orig_seed']}) {team['team']}"))
# wildcard all
for i, team in enumerate(wildcard_list):
    r=18+i
    week14_cells.append(Cell(r,4, f"({team['orig_seed']}) {team['team']}"))
    week14_cells.append(Cell(r,6, fmt(team["wk14"])))
ws.update_cells(week14_cells)
print("Week 14 written via update_cells.")

# ——— BATCH WRITE: Week 15 (ranges) ———
week15_updates=[]
week15_updates.append({
    'range':'H5:J6',
    'values':[
        [f"({top_bye15['orig_seed']}) {top_bye15['team']}","",fmt(top_bye15["wk15"])],
        [f"({low_bye15['orig_seed']}) {low_bye15['team']}","",fmt(low_bye15["wk15"])]
    ]
})
week15_updates.append({
    'range':'H10:J14',
    'values':[[f"({t['orig_seed']}) {t['team']}","",fmt(t["wk15"])] for t in playoff15_sorted]
})
week15_updates.append({
    'range':'H18:J22',
    'values':[[f"({t['orig_seed']}) {t['team']}","",fmt(t["wk15"])] for t in wild15_sorted]
})
ws.batch_update(week15_updates)
print("Week 15 written via batch_update.")

# ——— BATCH WRITE: Combined Week 14+15 ———
combined_updates=[]
combined_updates.append({
    'range':'L5:N6',
    'values':[
        [f"({top_bye_comb['orig_seed']}) {top_bye_comb['team']}","",fmt(top_bye_comb["combined"])],
        [f"({low_bye_comb['orig_seed']}) {low_bye_comb['team']}","",fmt(low_bye_comb["combined"])]
    ]
})
combined_updates.append({
    'range':'L10:N14',
    'values':[[f"({t['orig_seed']}) {t['team']}","",fmt(t["combined"])] for t in playoff_comb]
})
combined_updates.append({
    'range':'L18:N22',
    'values':[[f"({t['orig_seed']}) {t['team']}","",fmt(t["combined"])] for t in wild_comb_sorted]
})
ws.batch_update(combined_updates)
print("Combined 14+15 written via batch_update.")

# ——— BATCH WRITE: Week 16 ———

# 1) Build playoff_combined (seeds 3–6 + wildcard_winner) and compute combined scores
playoff_combined = [r for r in results if 3 <= r["orig_seed"] <= 6]
if wildcard_winner:
    playoff_combined.append(wildcard_winner)
for r in playoff_combined:
    r["combined"] = r["wk14"] + r["wk15"]

# 2) Pick top 3 and bottom 2 by combined
top3_pc = sorted(playoff_combined, key=lambda r: r["combined"], reverse=True)[:3]
bot2_pc = sorted(playoff_combined, key=lambda r: r["combined"])[:2]

# 3) Identify the two wildcards to exclude:
#    a) wildcard_winner (highest wk14)
#    b) second_comb_wild (highest combined besides wildcard_winner)
# compute combined for all wildcards
for r in wildcard_list:
    r["combined"] = r["wk14"] + r["wk15"]
# sort by combined, then pick first one that's not wildcard_winner
combined_wild = sorted(wildcard_list, key=lambda r: r["combined"], reverse=True)
second_comb_wild = next(r for r in combined_wild if r["roster_id"] != wildcard_winner["roster_id"])

# 4) Build your three groups:
conf_list   = bye_list + top3_pc
purg_list   = bot2_pc + [second_comb_wild]
# Exclude any team that's already in conf_list or purg_list
exclude_ids = {t["roster_id"] for t in conf_list + purg_list}

remaining_wild = [
    r for r in wildcard_list
    if r["roster_id"] not in exclude_ids
]

# Now pick the 4 lowest by Week-15 from those remaining
toilet_list = sorted(remaining_wild, key=lambda r: r["wk15"])[:4]

# 5) Sort each by week-16 score
conf_sorted   = sorted(conf_list,   key=lambda r: r["wk16"], reverse=True)
purg_sorted   = sorted(purg_list,   key=lambda r: r["wk16"], reverse=True)
toilet_sorted = sorted(toilet_list, key=lambda r: r["wk16"], reverse=True)

# 6) Batch-update all three ranges in one API call
week16_updates = [
    {
        'range': 'U5:W9',
        'values': [
            [f"({t['orig_seed']}) {t['team']}", "", fmt(t["wk16"])]
            for t in conf_sorted
        ]
    },
    {
        'range': 'U13:W15',
        'values': [
            [f"({t['orig_seed']}) {t['team']}", "", fmt(t["wk16"])]
            for t in purg_sorted
        ]
    },
    {
        'range': 'U19:W22',
        'values': [
            [f"({t['orig_seed']}) {t['team']}", "", fmt(t["wk16"])]
            for t in toilet_sorted
        ]
    }
]

ws.batch_update(week16_updates)
print("Week 16 grids U5–U9, U13–U15 & U19–U22 written via batch_update.")


# ——— BATCH WRITE: Week 17 ———

# 1) Top 3 from conf_list by week-16, then sort by week-17
conf_top3 = conf_sorted[:3]
conf_top3_sorted = sorted(conf_top3, key=lambda r: r["wk17"], reverse=True)

# 2) Extend purg_list (from Week 16) with bottom 2 of conf_list by wk16 + top wk16 from toilet_list
bottom2_conf16 = sorted(conf_list, key=lambda r: r["wk16"])[:2]
toilet_top16   = sorted(toilet_list, key=lambda r: r["wk16"], reverse=True)[0]

purg17_list = purg_list + bottom2_conf16 + [toilet_top16]
purg17_sorted = sorted(purg17_list, key=lambda r: r["wk17"], reverse=True)

# 3) Bottom 3 for Week 17: start from wildcard_list but exclude any team in conf_top3 or purg17_list
exclude_ids = {t["roster_id"] for t in conf_top3 + purg17_list}

# filter down to only those wildcards
toilet_candidates = [
    r for r in wildcard_list
    if r["roster_id"] not in exclude_ids
]

# pick the three lowest by Week-16, then sort those by Week-17 descending
toilet_bottom3_16 = sorted(toilet_candidates, key=lambda r: r["wk16"])[:3]
toilet17_sorted   = sorted(toilet_bottom3_16, key=lambda r: r["wk17"], reverse=True)


# 4) Batch update all three grids
week17_updates = [
    {
        'range': 'AC5:AE7',
        'values': [
            [f"({t['orig_seed']}) {t['team']}", "", fmt(t["wk17"])]
            for t in conf_top3_sorted
        ]
    },
    {
        'range': 'AC11:AE16',
        'values': [
            [f"({t['orig_seed']}) {t['team']}", "", fmt(t["wk17"])]
            for t in purg17_sorted
        ]
    },
    {
        'range': 'AC20:AE22',
        'values': [
            [f"({t['orig_seed']}) {t['team']}", "", fmt(t["wk17"])]
            for t in toilet17_sorted
        ]
    }
]

ws.batch_update(week17_updates)
print("Week 17 grids AC5–AE7, AC11–AE16 & AC20–AE22 written via batch_update.")