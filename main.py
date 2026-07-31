import os
import sys

import requests


LICHESS_API = "https://lichess.org/api"
TEAM_ID = "the-chess-fan-club"


def get_token() -> str:
    token = os.getenv("LICHESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("LICHESS_TOKEN is not configured.")
    return token


def get_headers(*, accept: str = "application/json") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {get_token()}",
        "Accept": accept,
        "User-Agent": "LichessTeamManagerChat/1.0",
    }


def check_account() -> None:
    response = requests.get(
        f"{LICHESS_API}/account",
        headers=get_headers(),
        timeout=30,
    )
    response.raise_for_status()

    account = response.json()
    print(f"Authenticated successfully as: {account.get('username', 'Unknown')}")


def list_team_members() -> None:
    response = requests.get(
        f"{LICHESS_API}/team/{TEAM_ID}/users",
        headers=get_headers(accept="application/x-ndjson"),
        timeout=60,
    )
    response.raise_for_status()

    members = [line for line in response.text.splitlines() if line.strip()]
    print(f"Team member records received: {len(members)}")


def list_tournaments() -> None:
    response = requests.get(
        f"{LICHESS_API}/team/{TEAM_ID}/arena",
        headers=get_headers(),
        timeout=30,
    )
    response.raise_for_status()
    print(response.text)


def main() -> None:
    command = os.getenv("MANAGER_COMMAND", "status").strip().lower()

    commands = {
        "status": check_account,
        "list-team-members": list_team_members,
        "list-tournaments": list_tournaments,
    }

    action = commands.get(command)
    if action is None:
        print(f"Unknown command: {command}", file=sys.stderr)
        print(f"Allowed commands: {', '.join(commands)}", file=sys.stderr)
        raise SystemExit(2)

    action()


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as error:
        response = error.response
        print(
            f"Lichess API error {response.status_code}: {response.text[:500]}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
