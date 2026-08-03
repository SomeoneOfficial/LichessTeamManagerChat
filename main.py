import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests


LICHESS_API = "https://lichess.org/api"
TEAM_ID = "the-chess-fan-club"

DESCRIPTION = (
    "Next Prize Tournament: https://lichess.org/tournament/jGlGk30d\n\n"
    "Join The Chess Fan Club for prize tournaments, ChessMood subscriptions, "
    "trophies, flairs, titles, leaderboards and Hall of Fame rewards. "
    "Want to organize or add your team to future battles? DM @Ajisland."
)

# The first three Arenas from the previous run were likely created successfully.
# This retry creates only the two Arenas that failed, followed by all five Swisses.
ARENAS = [
    {"name": "Cheesse Arena Crazyhouse", "clock_time": 3, "clock_increment": 0, "minutes": 45, "wait_minutes": 45, "variant": "crazyhouse"},
    {"name": "Cheesse Arena Chess960", "clock_time": 5, "clock_increment": 3, "minutes": 60, "wait_minutes": 60, "variant": "chess960"},
]

SWISSES = [
    {"name": "Swiss Cheesse Bullet Reloaded", "clock_limit": 60, "clock_increment": 0, "rounds": 10, "variant": "standard"},
    {"name": "Swiss Cheesse Blitz Reloaded", "clock_limit": 180, "clock_increment": 2, "rounds": 8, "variant": "standard"},
    {"name": "Swiss Cheesse Crazyhouse Reloaded", "clock_limit": 180, "clock_increment": 0, "rounds": 7, "variant": "crazyhouse"},
    {"name": "Swiss Cheesse Atomic Reloaded", "clock_limit": 180, "clock_increment": 2, "rounds": 7, "variant": "atomic"},
    {"name": "Swiss Cheesse Rapid Reloaded", "clock_limit": 600, "clock_increment": 0, "rounds": 5, "variant": "standard"},
]


def token() -> str:
    value = os.getenv("LICHESS_TOKEN", "").strip()
    if not value:
        raise RuntimeError("LICHESS_TOKEN is missing from GitHub Actions secrets.")
    return value


def headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token()}",
        "Accept": "application/json",
        "User-Agent": "LichessTeamManagerChat/4.1",
    }


def post_with_rate_limit(url: str, payload: dict) -> requests.Response:
    response = requests.post(url, headers=headers(), data=payload, timeout=30)
    if response.status_code == 429:
        print("Lichess rate limit reached; waiting 60 seconds before one retry.", flush=True)
        time.sleep(60)
        response = requests.post(url, headers=headers(), data=payload, timeout=30)
    return response


def rounded_utc_start(delay_minutes: int) -> datetime:
    start = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
    start = start.replace(second=0, microsecond=0)
    remainder = start.minute % 5
    if remainder:
        start += timedelta(minutes=5 - remainder)
    return start


def create_arena(tournament: dict) -> str:
    payload = {
        "name": tournament["name"],
        "clockTime": tournament["clock_time"],
        "clockIncrement": tournament["clock_increment"],
        "minutes": tournament["minutes"],
        "waitMinutes": tournament["wait_minutes"],
        "variant": tournament["variant"],
        "rated": "false",
        "berserkable": "true",
        "description": DESCRIPTION,
        "conditions.teamMember.teamId": TEAM_ID,
    }

    response = post_with_rate_limit(f"{LICHESS_API}/tournament", payload)
    if not response.ok:
        raise RuntimeError(
            f"Failed to create Arena {tournament['name']}: "
            f"HTTP {response.status_code}: {response.text[:1000]}"
        )

    tournament_id = response.json().get("id")
    if not tournament_id:
        raise RuntimeError(f"No Arena ID returned for {tournament['name']}.")
    return f"https://lichess.org/tournament/{tournament_id}"


def create_swiss(tournament: dict, start_time: datetime) -> str:
    payload = {
        "name": tournament["name"],
        "clock.limit": tournament["clock_limit"],
        "clock.increment": tournament["clock_increment"],
        "nbRounds": tournament["rounds"],
        "variant": tournament["variant"],
        "rated": "false",
        "description": DESCRIPTION,
        "startsAt": start_time.isoformat().replace("+00:00", "Z"),
    }

    response = post_with_rate_limit(
        f"{LICHESS_API}/swiss/new/{TEAM_ID}",
        payload,
    )
    if not response.ok:
        raise RuntimeError(
            f"Failed to create Swiss {tournament['name']}: "
            f"HTTP {response.status_code}: {response.text[:1000]}"
        )

    tournament_id = response.json().get("id")
    if not tournament_id:
        raise RuntimeError(f"No Swiss ID returned for {tournament['name']}.")
    return f"https://lichess.org/swiss/{tournament_id}"


def main() -> None:
    created: list[str] = []

    print("Creating the 2 remaining Arenas with valid waitMinutes values...", flush=True)
    for arena in ARENAS:
        url = create_arena(arena)
        created.append(url)
        print(
            f"Created {arena['name']} (starts in {arena['wait_minutes']} minutes): {url}",
            flush=True,
        )
        time.sleep(3)

    first_swiss_start = rounded_utc_start(90)
    print("Creating 5 staggered Swiss tournaments...", flush=True)
    for index, swiss in enumerate(SWISSES):
        start_time = first_swiss_start + timedelta(minutes=index * 45)
        url = create_swiss(swiss, start_time)
        created.append(url)
        print(f"Created {swiss['name']} for {start_time.isoformat()}: {url}", flush=True)
        if index < len(SWISSES) - 1:
            time.sleep(3)

    print("\nCreated tournament links:")
    for url in created:
        print(url)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
