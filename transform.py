"""
Turn two GameChanger API responses into clean, standard-line player records.

Inputs (raw JSON, exactly as returned by the GC internal API):
  - season-stats response  -> {"stats_data": {"players": {<uuid>: {...}}, ...}}
  - players (roster) response -> [ {id, first_name, last_name, number, status}, ... ]

Output: a list of per-player dicts with a standard hitting line, plus a
standard pitching line for anyone who pitched. Removed players are dropped;
players with no stats yet are kept with has_stats=False so the profile can
show a clean "no stats yet" state.
"""
import json

# Standard hitting line (counting stats) and rate stats
HIT_COUNT = ["PA", "AB", "R", "H", "2B", "3B", "HR", "RBI", "BB", "SO", "SB"]
HIT_RATE  = ["AVG", "OBP", "SLG", "OPS"]


def avg_fmt(v):
    """Baseball rate format: 3 decimals, drop the leading zero (.286, 1.000, 2.000)."""
    if v is None:
        v = 0
    s = f"{float(v):.3f}"
    return s[1:] if s.startswith("0.") else s


def two(v):
    """Two-decimal format for ERA / WHIP (1.00, 0.57)."""
    return f"{float(v or 0):.2f}"


def ip_from_outs(outs):
    """Convert outs to baseball innings notation: 21 -> '7.0', 20 -> '6.2'."""
    outs = int(outs)
    return f"{outs // 3}.{outs % 3}"


def build_records(stats_json, players_json):
    by_id = stats_json.get("stats_data", {}).get("players", {})
    records = []

    for p in players_json:
        if p.get("status") == "removed":
            continue  # drop players no longer on the roster

        pid = p["id"]
        rec = {
            "player_id": pid,
            "number": p.get("number", ""),
            "first_name": p.get("first_name", ""),
            "last_name": p.get("last_name", ""),
            "name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
        }

        node = by_id.get(pid)
        if not node:
            rec["has_stats"] = False        # rostered but no game data yet
            records.append(rec)
            continue

        stats = node.get("stats", {})
        off = stats.get("offense", {})
        deff = stats.get("defense", {})
        gen = stats.get("general", {})

        rec["has_stats"] = True
        rec["GP"] = gen.get("GP", off.get("GP", 0))

        # --- hitting line (only if they actually had a plate appearance) ---
        pa = off.get("PA", 0) or 0
        rec["batted"] = pa > 0
        if rec["batted"]:
            for k in HIT_COUNT:
                rec[k] = off.get(k, 0)
            for k in HIT_RATE:
                rec[k] = avg_fmt(off.get(k, 0))

        # --- pitching line (only if they recorded outs / faced batters) ---
        outs = deff.get("outs")
        pitched = bool((deff.get("BF", 0) or 0) or (outs or 0) or (deff.get("IP", 0) or 0))
        rec["is_pitcher"] = pitched
        if pitched:
            rec["pitching"] = {
                "W": deff.get("W", 0), "L": deff.get("L", 0), "SV": deff.get("SV", 0),
                "IP": ip_from_outs(outs) if outs is not None else str(deff.get("IP", 0)),
                "H": deff.get("H", 0), "R": deff.get("R", 0), "ER": deff.get("ER", 0),
                "BB": deff.get("BB", 0), "SO": deff.get("SO", 0),
                "ERA": two(deff.get("ERA", 0)), "WHIP": two(deff.get("WHIP", 0)),
            }

        records.append(rec)

    return records


if __name__ == "__main__":
    import sys
    stats = json.load(open(sys.argv[1]))
    players = json.load(open(sys.argv[2]))
    out = build_records(stats, players)
    print(json.dumps(out, indent=2))
