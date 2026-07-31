import json
import os
import sys
from pathlib import Path

import requests


LICHESS_API = "https://lichess.org/api"
TEAM_ID = "the-chess-fan-club"
COMMAND_FILE = Path("command.json")


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


def read_command() -> dict:
    if not COMMAND_FILE.exists():
        return {"command": "status"}
    with COMMAND_FILE.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("command.json must contain a JSON object.")
    return data


def check_account(_: dict) -> None:
    response = requests.get(
        f"{LICHESS_API}/account",
        headers=get_headers(),
        timeout=30,
    )
    response.raise_for_status()
    account = response.json()
    print(f"Authenticated successfully as: {account.get('username', 'Unknown')}")


def list_team_members(_: dict) -> None:
    response = requests.get(
        f"{LICHESS_API}/team/{TEAM_ID}/users",
        headers=get_headers(accept="application/x-ndjson"),
        timeout=60,
    )
    response.raise_for_status()
    members = [line for line in response.text.splitlines() if line.strip()]
    print(f"Team member records received: {len(members)}")


def list_tournaments(_: dict) -> None:
    response = requests.get(
        f"{LICHESS_API}/team/{TEAM_ID}/arena",
        headers=get_headers(),
        timeout=30,
    )
    response.raise_for_status()
    print(response.text)


def send_message(command_data: dict) -> None:
    username = str(command_data.get("username", "")).strip()
    message = str(command_data.get("message", "")).strip()

    if not username:
        raise ValueError("send-message requires a username.")
    if not message:
        raise ValueError("send-message requires a message.")
    if len(message) > 8000:
        raise ValueError("Message is too long.")

    response = requests.post(
        f"{LICHESS_API}/inbox/{username}",
        headers=get_headers(accept="application/json"),
        data={"text": message},
        timeout=30,
    )
    response.raise_for_status()
    print(f"Message sent to {username}.")


def main() -> None:
    command_data = read_command()
    command_name = str(command_data.get("command", "status")).strip().lower()

    commands = {
        "status": check_account,
        "list-team-members": list_team_members,
        "list-tournaments": list_tournaments,
        "send-message": send_message,
    }

    action = commands.get(command_name)
    if action is None:
        print(f"Unknown command: {command_name}", file=sys.stderr)
        print(f"Allowed commands: {', '.join(commands)}", file=sys.stderr)
        raise SystemExit(2)

    action(command_data)


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
