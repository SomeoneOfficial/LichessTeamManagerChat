import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


LICHESS_API = "https://lichess.org/api"
DEFAULT_TEAM_ID = "the-chess-fan-club"
COMMAND_FILE = Path("command.json")


def token() -> str:
    value = os.getenv("LICHESS_TOKEN", "").strip()
    if not value:
        raise RuntimeError("LICHESS_TOKEN is missing from GitHub Actions secrets.")
    return value


def headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token()}",
        "Accept": "application/json",
        "User-Agent": "LichessTeamManagerChat/2.0",
    }


def read_command() -> dict:
    with COMMAND_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError("command.json must contain a JSON object.")
    return data


def rounded_start(delay_minutes: int) -> datetime:
    start = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
    start = start.replace(second=0, microsecond=0)
    remainder = start.minute % 5
    if remainder:
        start += timedelta(minutes=5 - remainder)
    return start


def create_tournaments(command: dict) -> None:
    tournaments = command.get("tournaments")
    if not isinstance(tournaments, list) or len(tournaments) != 10:
        raise ValueError("command.json must contain exactly 10 tournaments.")

    team_id = str(command.get("team_id", DEFAULT_TEAM_ID)).strip()
    first_start = rounded_start(int(command.get("start_delay_minutes", 30)))
    spacing = int(command.get("spacing_minutes", 45))

    if spacing < 15:
        raise ValueError("spacing_minutes must be at least 15.")

    created: list[str] = []

    for index, tournament in enumerate(tournaments):
        if not isinstance(tournament, dict):
            raise ValueError(f"Tournament #{index + 1} must be an object.")

        start_time = first_start + timedelta(minutes=index * spacing)
        name = str(tournament["name"]).strip()

        payload = {
            "name": name,
            "clock.limit": int(tournament["clock_limit"]),
            "clock.increment": int(tournament.get("clock_increment", 0)),
            "nbRounds": int(tournament.get("rounds", 7)),
            "variant": str(tournament.get("variant", "standard")),
            "rated": "true" if bool(tournament.get("rated", False)) else "false",
            "description": str(tournament.get("description", "")),
            "startsAt": start_time.isoformat().replace("+00:00", "Z"),
        }

        response = requests.post(
            f"{LICHESS_API}/swiss/new/{team_id}",
            headers=headers(),
            data=payload,
            timeout=30,
        )

        if response.status_code == 429:
            raise RuntimeError("Lichess rate limit reached. Retry later.")

        if not response.ok:
            raise RuntimeError(
                f"Failed to create {name}: HTTP {response.status_code}: "
                f"{response.text[:1000]}"
            )

        result = response.json()
        tournament_id = result.get("id")
        if not tournament_id:
            raise RuntimeError(f"Lichess returned no tournament ID for {name}: {result}")

        url = f"https://lichess.org/swiss/{tournament_id}"
        created.append(url)
        print(f"Created {name} at {start_time.isoformat()}: {url}")

        if index < len(tournaments) - 1:
            time.sleep(3)

    print("\nCreated all tournaments:")
    for url in created:
        print(url)


def main() -> None:
    command = read_command()
    command_name = str(command.get("command", "")).strip().lower()

    if command_name != "create-swiss-tournaments":
        raise ValueError("command must be create-swiss-tournaments.")

    create_tournaments(command)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
