import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


LICHESS_ROOT = "https://lichess.org"
LICHESS_API = f"{LICHESS_ROOT}/api"
TEAM_ID = "the-chess-fan-club"
COMMAND_FILE = Path("command.json")
DEFAULT_OUTPUT_FILE = Path("small_active_teams.json")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "LichessTeamManagerChat/1.1"})


def get_token() -> str:
    token = os.getenv("LICHESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("LICHESS_TOKEN is not configured.")
    return token


def get_headers(*, accept: str = "application/json", authenticated: bool = True) -> dict[str, str]:
    headers = {
        "Accept": accept,
        "User-Agent": "LichessTeamManagerChat/1.1",
    }
    if authenticated:
        headers["Authorization"] = f"Bearer {get_token()}"
    return headers


def read_command() -> dict:
    if not COMMAND_FILE.exists():
        return {"command": "status"}
    with COMMAND_FILE.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("command.json must contain a JSON object.")
    return data


def request_with_backoff(method: str, url: str, **kwargs) -> requests.Response:
    timeout = kwargs.pop("timeout", 30)
    for attempt in range(3):
        response = SESSION.request(method, url, timeout=timeout, **kwargs)
        if response.status_code != 429:
            return response
        if attempt == 2:
            break
        time.sleep(60)
    return response


def check_account(_: dict) -> None:
    response = request_with_backoff(
        "GET",
        f"{LICHESS_API}/account",
        headers=get_headers(),
    )
    response.raise_for_status()
    account = response.json()
    print(f"Authenticated successfully as: {account.get('username', 'Unknown')}")


def list_team_members(_: dict) -> None:
    response = request_with_backoff(
        "GET",
        f"{LICHESS_API}/team/{TEAM_ID}/users",
        headers=get_headers(accept="application/x-ndjson"),
        timeout=60,
    )
    response.raise_for_status()
    members = [line for line in response.text.splitlines() if line.strip()]
    print(f"Team member records received: {len(members)}")


def list_tournaments(_: dict) -> None:
    response = request_with_backoff(
        "GET",
        f"{LICHESS_API}/team/{TEAM_ID}/swiss",
        headers=get_headers(accept="application/x-ndjson"),
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

    response = request_with_backoff(
        "POST",
        f"{LICHESS_ROOT}/inbox/{username}",
        headers=get_headers(),
        data={"text": message},
    )
    response.raise_for_status()
    print(f"Message sent to {username}.")


def create_swiss_tournaments(command_data: dict) -> None:
    team_id = str(command_data.get("team_id", TEAM_ID)).strip()
    tournaments = command_data.get("tournaments")

    if not isinstance(tournaments, list) or not tournaments:
        raise ValueError("create-swiss-tournaments requires a non-empty tournaments list.")
    if len(tournaments) > 10:
        raise ValueError("A maximum of 10 tournaments can be created in one run.")

    created = []
    for index, tournament in enumerate(tournaments, start=1):
        if not isinstance(tournament, dict):
            raise ValueError(f"Tournament #{index} must be a JSON object.")

        name = str(tournament.get("name", "")).strip()
        clock_limit = int(tournament.get("clock_limit", 180))
        clock_increment = int(tournament.get("clock_increment", 0))
        rounds = int(tournament.get("rounds", 5))
        variant = str(tournament.get("variant", "standard")).strip()
        description = str(tournament.get("description", "")).strip()
        rated = bool(tournament.get("rated", False))

        if not name:
            raise ValueError(f"Tournament #{index} is missing a name.")
        if not 3 <= rounds <= 100:
            raise ValueError(f"Tournament #{index} has invalid rounds: {rounds}.")
        if clock_limit < 0 or clock_increment < 0:
            raise ValueError(f"Tournament #{index} has an invalid clock setting.")

        payload = {
            "name": name,
            "clock.limit": clock_limit,
            "clock.increment": clock_increment,
            "nbRounds": rounds,
            "variant": variant,
            "rated": "true" if rated else "false",
            "description": description,
        }

        response = request_with_backoff(
            "POST",
            f"{LICHESS_API}/swiss/new/{team_id}",
            headers=get_headers(),
            data=payload,
        )
        response.raise_for_status()
        result = response.json()
        tournament_id = result.get("id", "unknown")
        created.append(tournament_id)
        print(f"Created {name}: https://lichess.org/swiss/{tournament_id}")
        if index < len(tournaments):
            time.sleep(2)

    print(f"Created {len(created)} Swiss tournaments.")


def normalize_space(value: str) -> str:
    return " ".join(value.split())


def parse_member_count(text: str) -> int | None:
    match = re.search(r"([\d,]+)\s+members?", text, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def extract_search_candidates(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[dict] = []
    seen: set[str] = set()

    for anchor in soup.select('a[href^="/team/"]'):
        href = str(anchor.get("href", "")).split("?", 1)[0].rstrip("/")
        parts = href.split("/")
        if len(parts) != 3:
            continue
        team_id = parts[-1].strip()
        if not team_id or team_id in {"all", "search", "new", "mine"} or team_id in seen:
            continue

        container = anchor
        for parent in anchor.parents:
            parent_text = normalize_space(parent.get_text(" ", strip=True))
            if re.search(r"[\d,]+\s+members?", parent_text, re.IGNORECASE):
                container = parent
                break

        text = normalize_space(container.get_text(" ", strip=True))
        count = parse_member_count(text)
        if count is None:
            continue

        name = normalize_space(anchor.get_text(" ", strip=True)) or team_id
        seen.add(team_id)
        candidates.append(
            {
                "team_id": team_id,
                "name": name,
                "members": count,
                "url": urljoin(LICHESS_ROOT, href),
            }
        )
    return candidates


def extract_team_details(team_id: str, fallback_name: str, fallback_members: int) -> dict:
    response = request_with_backoff(
        "GET",
        f"{LICHESS_ROOT}/team/{team_id}",
        headers=get_headers(accept="text/html", authenticated=False),
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    page_text = normalize_space(soup.get_text(" ", strip=True))

    heading = soup.select_one("h1")
    name = normalize_space(heading.get_text(" ", strip=True)) if heading else fallback_name
    members = parse_member_count(page_text) or fallback_members

    leaders: list[str] = []
    leader_label = soup.find(string=re.compile(r"Team leaders?", re.IGNORECASE))
    if leader_label:
        region = leader_label.parent
        for _ in range(3):
            if region is None:
                break
            leader_links = region.select('a[href^="/@/"]')
            if leader_links:
                for link in leader_links:
                    username = str(link.get("href", "")).split("/@/", 1)[-1].split("/", 1)[0]
                    username = username.strip()
                    if username and username not in leaders:
                        leaders.append(username)
                break
            region = region.parent

    if not leaders:
        match = re.search(r"Team leaders?:\s*([A-Za-z0-9_-]+)", page_text, re.IGNORECASE)
        if match:
            leaders.append(match.group(1))

    join_text_present = bool(
        re.search(r"\bJoin team\b|\bRequest to join\b", page_text, re.IGNORECASE)
    )
    closed_text_present = bool(
        re.search(
            r"\bclosed team\b|\bteam is closed\b|\bnot accepting new members\b",
            page_text,
            re.IGNORECASE,
        )
    )
    unlocked = join_text_present and not closed_text_present

    return {
        "team_id": team_id,
        "name": name,
        "members": members,
        "leaders": leaders,
        "leader": leaders[0] if leaders else None,
        "unlocked": unlocked,
        "url": f"{LICHESS_ROOT}/team/{team_id}",
    }


def parse_ndjson(text: str) -> list[dict]:
    records: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def timestamp_from_tournament(record: dict) -> datetime | None:
    for field in ("finishesAt", "startsAt", "createdAt"):
        value = record.get(field)
        if isinstance(value, (int, float)):
            if value > 10_000_000_000:
                value /= 1000
            return datetime.fromtimestamp(value, tz=timezone.utc)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
    return None


def get_recent_activity(team_id: str, active_days: int) -> tuple[bool, str | None, str | None]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=active_days)
    newest: datetime | None = None
    newest_type: str | None = None

    for tournament_type in ("arena", "swiss"):
        response = request_with_backoff(
            "GET",
            f"{LICHESS_API}/team/{team_id}/{tournament_type}",
            headers=get_headers(accept="application/x-ndjson"),
            params={"max": 5},
        )
        if response.status_code in {401, 403, 404}:
            continue
        response.raise_for_status()
        for record in parse_ndjson(response.text):
            timestamp = timestamp_from_tournament(record)
            if timestamp and (newest is None or timestamp > newest):
                newest = timestamp
                newest_type = tournament_type

    if newest is None:
        return False, None, None
    return newest >= cutoff, newest.isoformat(), newest_type


def discover_small_active_teams(command_data: dict) -> None:
    max_members = int(command_data.get("max_members", 149))
    target_count = int(command_data.get("target_count", 20))
    active_days = int(command_data.get("active_days", 180))
    pages_per_query = int(command_data.get("pages_per_query", 6))
    output_file = Path(str(command_data.get("output_file", DEFAULT_OUTPUT_FILE)))
    search_terms = command_data.get(
        "search_terms",
        ["chess", "club", "team", "academy", "school", "friends", "community", "battle"],
    )

    if not isinstance(search_terms, list) or not search_terms:
        raise ValueError("search_terms must be a non-empty list.")
    if not 1 <= target_count <= 100:
        raise ValueError("target_count must be between 1 and 100.")
    if max_members < 1:
        raise ValueError("max_members must be positive.")

    candidate_map: dict[str, dict] = {}
    for term in search_terms:
        for page in range(1, pages_per_query + 1):
            response = request_with_backoff(
                "GET",
                f"{LICHESS_ROOT}/team/search",
                headers=get_headers(accept="text/html", authenticated=False),
                params={"text": str(term), "page": page},
            )
            response.raise_for_status()
            found = extract_search_candidates(response.text)
            if not found:
                break
            for candidate in found:
                if candidate["members"] <= max_members:
                    candidate_map.setdefault(candidate["team_id"], candidate)
            time.sleep(0.8)

    print(f"Found {len(candidate_map)} candidate teams with at most {max_members} members.")

    results: list[dict] = []
    for candidate in candidate_map.values():
        if len(results) >= target_count:
            break
        try:
            details = extract_team_details(
                candidate["team_id"],
                candidate["name"],
                candidate["members"],
            )
            if details["members"] > max_members or not details["unlocked"] or not details["leaders"]:
                continue

            active, latest_activity, activity_type = get_recent_activity(
                details["team_id"], active_days
            )
            if not active:
                continue

            details["active"] = True
            details["latest_activity"] = latest_activity
            details["activity_type"] = activity_type
            results.append(details)
            print(
                f"[{len(results)}/{target_count}] {details['name']} "
                f"({details['members']} members) leaders={','.join(details['leaders'])}"
            )
        except requests.HTTPError as error:
            print(
                f"Skipping {candidate['team_id']} after HTTP "
                f"{error.response.status_code}.",
                file=sys.stderr,
            )
        time.sleep(1)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "criteria": {
            "maximum_members": max_members,
            "unlocked": True,
            "active_within_days": active_days,
        },
        "count": len(results),
        "teams": sorted(results, key=lambda item: (item["members"], item["name"].lower())),
        "leaders": sorted(
            {
                leader
                for team in results
                for leader in team.get("leaders", [])
                if leader
            },
            key=str.lower,
        ),
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Saved {len(results)} qualifying teams to {output_file}.")
    if not results:
        raise RuntimeError(
            "No qualifying teams were found. Increase pages_per_query, active_days, "
            "or change search_terms."
        )


def main() -> None:
    command_data = read_command()
    command_name = str(command_data.get("command", "status")).strip().lower()

    commands = {
        "status": check_account,
        "list-team-members": list_team_members,
        "list-tournaments": list_tournaments,
        "send-message": send_message,
        "create-swiss-tournaments": create_swiss_tournaments,
        "discover-small-active-teams": discover_small_active_teams,
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
            f"Lichess API error {response.status_code}: {response.text[:1000]}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
