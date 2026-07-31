import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = "https://lichess.org"
API = f"{ROOT}/api"
OUTPUT = Path("small_active_teams.json")
TOKEN = os.getenv("LICHESS_TOKEN", "").strip()
SESSION = requests.Session()
SESSION.headers.update