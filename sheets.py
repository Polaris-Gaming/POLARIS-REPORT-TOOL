import os
import time
import json
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets"
]

_team_cache = {"data": None, "expires": 0}
_player_cache = {"data": None, "expires": 0}


def get_client():
    service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

    if service_account_json:
        service_account_info = json.loads(service_account_json)

        creds = Credentials.from_service_account_info(
            service_account_info,
            scopes=SCOPES
        )
    else:
        creds = Credentials.from_service_account_file(
            "service_account.json",
            scopes=SCOPES
        )

    return gspread.authorize(creds)


def get_spreadsheet():
    client = get_client()

    sheet_id = os.getenv("GOOGLE_SHEET_ID")

    if not sheet_id:
        raise Exception("GOOGLE_SHEET_ID is missing from environment variables.")

    return client.open_by_key(sheet_id)


def get_spreadsheet():
    client = get_client()
    sheet_id = os.getenv("GOOGLE_SHEET_ID")

    if not sheet_id:
        raise Exception("GOOGLE_SHEET_ID is missing from environment variables.")

    return client.open_by_key(sheet_id)


def get_teams_sheet():
    return get_spreadsheet().worksheet("Teams")


def get_reports_sheet():
    return get_spreadsheet().worksheet("Reports")


def get_league_reports_sheet():
    return get_spreadsheet().worksheet("League Reports")


def get_player_ranks_sheet():
    return get_spreadsheet().worksheet("Player ranks")


def clear_team_cache():
    global _team_cache
    _team_cache = {
        "data": None,
        "expires": 0
    }


def clear_player_cache():
    global _player_cache
    _player_cache = {
        "data": None,
        "expires": 0
    }


def refresh_validated_players_cache(ttl_seconds=3600):
    global _player_cache

    sheet = get_player_ranks_sheet()
    values = sheet.get("A3:A")

    players = []
    for row in values:
        if row and str(row[0]).strip():
            players.append(str(row[0]).strip())

    seen = set()
    unique_players = []

    for name in players:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            unique_players.append(name)

    _player_cache["data"] = unique_players
    _player_cache["expires"] = time.time() + ttl_seconds

    return len(unique_players)


def get_validated_players(use_cache=True, ttl_seconds=3600):
    global _player_cache

    now = time.time()

    if (
        use_cache
        and _player_cache["data"] is not None
        and now < _player_cache["expires"]
    ):
        return _player_cache["data"]

    refresh_validated_players_cache(ttl_seconds=ttl_seconds)
    return _player_cache["data"]


def get_all_teams_cached(ttl_seconds=30):
    global _team_cache

    now = time.time()

    if _team_cache["data"] is not None and now < _team_cache["expires"]:
        return _team_cache["data"]

    rows = get_teams_sheet().get_all_records()
    _team_cache["data"] = rows
    _team_cache["expires"] = now + ttl_seconds

    return rows


def get_next_team_number():
    rows = get_all_teams_cached()

    if not rows:
        return 1

    numbers = []

    for row in rows:
        value = str(row.get("Team Number", "")).strip()
        if value.isdigit():
            numbers.append(int(value))

    if not numbers:
        return 1

    return max(numbers) + 1


def register_team(player1, player2, player3, player4):
    teams_sheet = get_teams_sheet()
    team_number = get_next_team_number()

    teams_sheet.append_row([
        str(team_number),
        str(player1).strip(),
        str(player2).strip(),
        str(player3).strip(),
        str(player4).strip(),
        "No"
    ])

    clear_team_cache()
    return team_number


def get_team(team_number):
    rows = get_all_teams_cached()

    for row in rows:
        if str(row["Team Number"]).strip() == str(team_number).strip():
            return row

    return None


def is_team_closed(team_number):
    team = get_team(team_number)

    if not team:
        raise Exception("Team number not found.")

    closed_value = str(team.get("Closed", "No")).strip().lower()
    return closed_value in ["yes", "true", "closed", "1"]


def set_team_closed_status(team_number, closed: bool):
    sheet = get_teams_sheet()
    records = sheet.get_all_records()
    headers = sheet.row_values(1)

    if "Closed" not in headers:
        raise Exception("Teams sheet is missing the 'Closed' column.")

    closed_col = headers.index("Closed") + 1

    for idx, row in enumerate(records, start=2):
        if str(row["Team Number"]).strip() == str(team_number).strip():
            sheet.update_cell(idx, closed_col, "Yes" if closed else "No")
            clear_team_cache()
            return

    raise Exception("Team number not found.")


def append_report(
    reporter,
    team_number,
    map_number,
    p1_kills,
    p2_kills,
    p3_kills,
    p4_kills,
    placement
):
    team = get_team(team_number)

    if not team:
        raise Exception("Team number not found.")

    if is_team_closed(team_number):
        raise Exception(f"Team {team_number} is closed and cannot submit reports.")

    total_kills = int(p1_kills) + int(p2_kills) + int(p3_kills) + int(p4_kills)

    reports_sheet = get_reports_sheet()
    headers = reports_sheet.row_values(1)

    row_data = {
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Reporter": str(reporter).strip(),
        "Team Number": str(team_number).strip(),
        "Map Number": str(map_number).strip(),
        "Player 1": str(team["Player 1"]).strip(),
        "Player 2": str(team["Player 2"]).strip(),
        "Player 3": str(team["Player 3"]).strip(),
        "Player 4": str(team["Player 4"]).strip(),
        "P1 Kills": int(p1_kills),
        "P2 Kills": int(p2_kills),
        "P3 Kills": int(p3_kills),
        "P4 Kills": int(p4_kills),
        "Total Kills": total_kills,
        "Placement": int(placement),
    }

    missing_headers = [h for h in row_data.keys() if h not in headers]

    if missing_headers:
        raise Exception(f"Missing Reports sheet headers: {', '.join(missing_headers)}")

    row_to_append = [row_data.get(header, "") for header in headers]

    reports_sheet.append_row(
        row_to_append,
        value_input_option="USER_ENTERED"
    )


def append_league_report(
    reporter,
    team_number,
    map_number,
    map_name,
    p1_kills,
    p2_kills,
    p3_kills,
    p4_kills,
    placement,
    p1_damage,
    p2_damage,
    p3_damage,
    p4_damage
):
    team = get_team(team_number)

    if not team:
        raise Exception("Team number not found.")

    if is_team_closed(team_number):
        raise Exception(f"Team {team_number} is closed and cannot submit league reports.")

    total_kills = int(p1_kills) + int(p2_kills) + int(p3_kills) + int(p4_kills)
    total_damage = int(p1_damage) + int(p2_damage) + int(p3_damage) + int(p4_damage)

    league_sheet = get_league_reports_sheet()
    headers = league_sheet.row_values(1)

    row_data = {
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Reporter": str(reporter).strip(),
        "Team Number": str(team_number).strip(),
        "Map Number": str(map_number).strip(),
        "Map": str(map_name).strip(),
        "Player 1": str(team["Player 1"]).strip(),
        "Player 2": str(team["Player 2"]).strip(),
        "Player 3": str(team["Player 3"]).strip(),
        "Player 4": str(team["Player 4"]).strip(),
        "P1 Kills": int(p1_kills),
        "P2 Kills": int(p2_kills),
        "P3 Kills": int(p3_kills),
        "P4 Kills": int(p4_kills),
        "Total Kills": total_kills,
        "P1 Damage": int(p1_damage),
        "P2 Damage": int(p2_damage),
        "P3 Damage": int(p3_damage),
        "P4 Damage": int(p4_damage),
        "Total Damage": total_damage,
        "Placement": int(placement),
    }

    missing_headers = [h for h in row_data.keys() if h not in headers]

    if missing_headers:
        raise Exception(f"Missing League Reports sheet headers: {', '.join(missing_headers)}")

    row_to_append = [row_data.get(header, "") for header in headers]

    league_sheet.append_row(
        row_to_append,
        value_input_option="USER_ENTERED"
    )


def clear_teams():
    sheet = get_teams_sheet()
    rows = sheet.get_all_values()

    if len(rows) > 1:
        sheet.delete_rows(2, len(rows))

    clear_team_cache()