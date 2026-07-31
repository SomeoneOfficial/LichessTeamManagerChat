import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests


LICHESS_API = "https://lichess.org/api"
TEAM_ID = "the-chess-fan-club"
START_DELAY_MINUTES = 30
SPACING_MINUTES = 45

DESCRIPTION = (
    "Next Prize Tournament: https://lichess.org/tournament/jGlGk30d\n\n"
    "Join The Chess Fan Club for prize tournaments, ChessMood subscriptions, "
    "trophies, flairs, titles, leaderboards and Hall of Fame rewards. "
    "Want to organize or add your team to future battles? DM @Ajisland."
)

TOURNAMENTS = [
    {
        "name": "Swiss Cheesse UltraBullet",
        "clock_limit": 15,
        "clock_increment": 0,
        "rounds": 12,
        "variant": "standard",
    },
    {
        "name": "Swiss Cheesse HyperBullet",
        "clock_limit": 30,
        "clock_increment": 0,
        "rounds": 11,
        "variant": "standard",
    },
    {
        "name": "Swiss Cheesse Bullet",
        "clock_limit": 60,
        "clock_increment": 0,
        "rounds": 10,
        "variant": "standard",
    },
    {
        "name": "Swiss Cheesse Bullet Plus",
        "clock_limit": 60,
        "clock_increment": 1,
        "rounds": 9,
        "variant": "standard",
    },
    {
        "name": "Swiss Cheesse Blitz",
        "clock_limit": 180,
        "clock_increment": 0,
        "rounds": 8,
        "variant": "standard",
    },
    {
        "name": "Swiss Cheesse Blitz Increment",
        "clock_limit": 180,
        "clock_increment": 2,
        "rounds": 8,
        "variant": "standard",
    },
    {
        "name": "Swiss Cheesse Crazyhouse",
        "clock_limit": 180,
        "clock_increment": 0,
        "rounds": 7,
        "variant": "crazyhouse",
    },
    {
        "name": "Swiss Cheesse Atomic",
        "clock_limit": 180,
        "clock_increment": 2,
        "rounds": 7,
        "variant": "atomic",
    },
    {
        "name": "Swiss Cheesse Chess960",
        "clock_limit": 300,
        "clock_increment": 3,
        "rounds": 6,
        "variant": "chess960",
    },
    {
        "name": "Swiss Cheesse Rapid",
        "clock_limit": 600,
        "clock_increment": 0,
        "rounds": 5,
        "variant": "standard",
    },
]


def get_token() -> str:
    token = os.getenv("LICHESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("LICHESS_TOKEN is missing from GitHub Actions secrets.")
    return token


def get_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {get_token()}",
        "Accept": "application/json",
        "User-Agent": "LichessTeamManagerChat/3.0",
    }


def rounded_start() -> datetime:
    start = datetime.now(timezone.utc) + timedelta(minutes=START_DELAY_MINUTES)
    start = start.replace(second=0, microsecond=0)
    remainder = start.minute % 5
    if remainder:
        start += timedelta(minutes=5 - remainder)
    return start


def create_tournament(tournament: dict, start_time: datetime) -> str:
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

    response = requests.post(
        f"{LICHESS_API}/swiss/new/{TEAM_ID}",
        headers=get_headers(),
        data=payload,
        timeout=30,
    )

    if response.status_code == 429:
        raise RuntimeError("Lichess rate limit reached. Wait one minute before retrying.")

    if not response.ok:
        raise RuntimeError(
            f"Failed to create {tournament['name']}: "
            f"HTTP {response.status_code}: {response.text[:1000]}"
        )

    result = response.json()
    tournament_id = result.get("id")
    if not tournament_id:
        raise RuntimeError(
            f"Lichess returned no tournament ID for {tournament['name']}: {result}"
        )

    return f"https://lichess.org/swiss/{tournament_id}"


def main() -> None:
    if len(TOURNAMENTS) != 10:
        raise RuntimeError("The script must contain exactly 10 tournaments.")

    first_start = rounded_start()
    created: list[str] = []

    for index, tournament in enumerate(TOURNAMENTS):
        start_time = first_start + timedelta(minutes=index * SPACING_MINUTES)
        url = create_tournament(tournament, start_time)
        created.append(url)
        print(
            f"Created {tournament['name']} for {start_time.isoformat()}: {url}",
            flush=True,
        )

        if index < len(TOURNAMENTS) - 1:
            time.sleep(3)

    print("\nCreated all 10 Swiss tournaments:")
    for url in created:
        print(url)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
