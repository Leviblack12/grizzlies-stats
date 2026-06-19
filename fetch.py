"""
Fetch raw GameChanger data for a team using the real internal API.

Auth: a gc-token (JWT) captured from a logged-in web.gc.com session, supplied
via the GC_TOKEN environment variable (store it as a GitHub Actions secret).

Confirmed endpoint contract (June 2026):
  GET /teams/{team_id}/season-stats   Accept: application/vnd.gc.com.team_season_stats+json; version=0.2.0
  GET /teams/{team_id}/players        Accept: application/vnd.gc.com.player:list+json;      version=0.1.0
Both require the gc-token header. AWS WAF does NOT block plain server requests.
"""
import os
import json
import ssl
import urllib.request
import urllib.error

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

API = "https://api.team-manager.gc.com"
ACCEPT_STATS = "application/vnd.gc.com.team_season_stats+json; version=0.2.0"
ACCEPT_PLAYERS = "application/vnd.gc.com.player:list+json; version=0.1.0"


class TokenLapsed(Exception):
    """Raised on a 401 so the daily job can alert you to refresh the token."""


def _get(path, accept, token, extra_headers=None):
    req = urllib.request.Request(API + path, method="GET")
    req.add_header("Accept", accept)
    req.add_header("gc-app-name", "web")
    req.add_header("gc-token", token or "")
    req.add_header("Origin", "https://web.gc.com")
    req.add_header("Referer", "https://web.gc.com/")
    for k, v in (extra_headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as r:
            return json.loads(r.read().decode()), dict(r.headers)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise TokenLapsed("gc-token is missing or expired — capture a fresh one.")
        raise RuntimeError(f"GC API {e.code} on {path}: {e.read().decode()[:200]}")


def fetch_team_stats(team_id, token):
    data, _ = _get(f"/teams/{team_id}/season-stats", ACCEPT_STATS, token)
    return data


def fetch_team_players(team_id, token):
    players, path = [], f"/teams/{team_id}/players"
    while path:
        data, headers = _get(path, ACCEPT_PLAYERS, token, {"x-pagination": "true"})
        players.extend(data if isinstance(data, list) else data.get("items", []))
        nxt = headers.get("x-next-page")          # follow pagination if present
        path = nxt if nxt and nxt != path else None
    return players


if __name__ == "__main__":
    import sys
    token = os.environ.get("GC_TOKEN", "")
    team_id = sys.argv[1]
    try:
        stats = fetch_team_stats(team_id, token)
        players = fetch_team_players(team_id, token)
        print(f"OK: {len(stats.get('stats_data', {}).get('players', {}))} stat lines, "
              f"{len(players)} roster entries")
    except TokenLapsed as e:
        print(f"TOKEN LAPSED: {e}")
        sys.exit(2)
