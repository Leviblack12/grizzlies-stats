"""
Daily job: pull every team's GameChanger stats and write a single data.json
that widget.html reads. Run by the GitHub Action; token comes from GC_TOKEN.
"""
import os
import sys
import json
from collections import defaultdict
import fetch
import transform


# ---------------------------------------------------------------------------
# Combined-record helpers
# ---------------------------------------------------------------------------

def _ip_to_outs(ip_str):
    """'5.2' -> 17 outs, '7.0' -> 21 outs."""
    parts = str(ip_str).split(".")
    return int(parts[0]) * 3 + (int(parts[1]) if len(parts) == 2 else 0)


def _detect_era_mult(records):
    """Detect whether GC uses ERA*7 or ERA*9 by back-checking a real pitcher."""
    for r in records:
        if not r.get("is_pitcher"):
            continue
        p = r.get("pitching", {})
        outs = _ip_to_outs(p.get("IP", "0.0"))
        er = float(p.get("ER", 0) or 0)
        era = float(p.get("ERA", 0) or 0)
        if outs > 0 and er > 0 and era > 0:
            ip_val = outs / 3
            for mult in (7, 9):
                if abs(er * mult / ip_val - era) < 0.02:
                    return mult
    return 7  # 7-inning high-school default


def _fmt(v):
    """Rate stat: 3 decimals, drop leading zero (.286, 1.000)."""
    s = f"{float(v):.3f}"
    return s[1:] if s.startswith("0.") else s


def _two(v):
    return f"{float(v or 0):.2f}"


def _gs(rec, key):
    """Get a counting stat from a player record (0 if absent/None)."""
    return int(rec.get(key, 0) or 0)


def build_combined_records(all_records, era_mult):
    """
    Detect players rostered on 2+ teams (matched by normalized full name).
    For each, sum raw counting stats and recompute rate stats from totals.
    Returns a list of combined records (individual per-team records unchanged).
    """
    by_name = defaultdict(list)
    for r in all_records:
        norm = r.get("name", "").lower().strip()
        if norm:
            by_name[norm].append(r)

    combined = []
    for norm_name, recs in by_name.items():
        teams_seen = {r.get("team") for r in recs}
        if len(teams_seen) < 2:
            continue  # single-team player, skip

        first = recs[0]
        first_name = first.get("first_name", "")
        last_name = first.get("last_name", "")
        slug = (first_name + last_name).lower().replace(" ", "")
        pid = f"combined-{slug}"

        # Jersey: first non-empty number found
        number = next((r.get("number") for r in recs if r.get("number")), "")

        has_stats = any(r.get("has_stats") for r in recs)
        is_pitcher = any(r.get("is_pitcher") for r in recs)
        batted = any(r.get("batted") for r in recs)

        # --- hitting (sum counting, recompute rates) ---
        gp   = sum(r.get("GP", 0) or 0 for r in recs)
        pa   = sum(_gs(r, "PA")  for r in recs if r.get("batted"))
        ab   = sum(_gs(r, "AB")  for r in recs if r.get("batted"))
        runs = sum(_gs(r, "R")   for r in recs if r.get("batted"))
        h    = sum(_gs(r, "H")   for r in recs if r.get("batted"))
        d    = sum(_gs(r, "2B")  for r in recs if r.get("batted"))
        t    = sum(_gs(r, "3B")  for r in recs if r.get("batted"))
        hr   = sum(_gs(r, "HR")  for r in recs if r.get("batted"))
        rbi  = sum(_gs(r, "RBI") for r in recs if r.get("batted"))
        bb   = sum(_gs(r, "BB")  for r in recs if r.get("batted"))
        so   = sum(_gs(r, "SO")  for r in recs if r.get("batted"))
        sb   = sum(_gs(r, "SB")  for r in recs if r.get("batted"))
        hbp  = sum(_gs(r, "HBP") for r in recs if r.get("batted"))
        sf   = sum(_gs(r, "SF")  for r in recs if r.get("batted"))

        singles = h - d - t - hr
        tb  = singles + 2*d + 3*t + 4*hr
        avg = (h / ab)                          if ab > 0 else 0
        slg = (tb / ab)                         if ab > 0 else 0
        obp_denom = ab + bb + hbp + sf
        obp = ((h + bb + hbp) / obp_denom)     if obp_denom > 0 else 0
        ops = obp + slg

        crec = {
            "player_id":  pid,
            "number":     number,
            "first_name": first_name,
            "last_name":  last_name,
            "name":       first.get("name", ""),
            "has_stats":  has_stats,
            "is_pitcher": is_pitcher,
            "team":       "Combined (" + " + ".join(sorted(teams_seen)) + ")",
            "GP":         gp,
        }

        if batted:
            crec.update({
                "batted": True,
                "PA": pa, "AB": ab, "R": runs, "H": h,
                "2B": d, "3B": t, "HR": hr,
                "RBI": rbi, "BB": bb, "SO": so, "SB": sb,
                "AVG": _fmt(avg),
                "OBP": _fmt(obp),
                "SLG": _fmt(slg),
                "OPS": _fmt(ops),
            })

        # --- pitching (sum outs, recompute ERA/WHIP) ---
        if is_pitcher:
            total_outs = 0
            p_h = p_r = p_er = p_bb = p_so = p_w = p_l = p_sv = 0
            for r in recs:
                if r.get("is_pitcher") and r.get("pitching"):
                    p = r["pitching"]
                    total_outs += _ip_to_outs(p.get("IP", "0.0"))
                    p_h  += int(p.get("H",  0) or 0)
                    p_r  += int(p.get("R",  0) or 0)
                    p_er += int(p.get("ER", 0) or 0)
                    p_bb += int(p.get("BB", 0) or 0)
                    p_so += int(p.get("SO", 0) or 0)
                    p_w  += int(p.get("W",  0) or 0)
                    p_l  += int(p.get("L",  0) or 0)
                    p_sv += int(p.get("SV", 0) or 0)

            ip_val = total_outs / 3 if total_outs > 0 else 0
            era  = (p_er * era_mult / ip_val) if ip_val > 0 else 0
            whip = ((p_bb + p_h) / ip_val)    if ip_val > 0 else 0

            crec["pitching"] = {
                "W": p_w, "L": p_l, "SV": p_sv,
                "IP": f"{total_outs // 3}.{total_outs % 3}",
                "H": p_h, "R": p_r, "ER": p_er,
                "BB": p_bb, "SO": p_so,
                "ERA":  _two(era),
                "WHIP": _two(whip),
            }

        combined.append(crec)

    return combined


def print_combined_verification(combined, all_records):
    """Print a verification table for every combined record."""
    by_name = defaultdict(list)
    for r in all_records:
        norm = r.get("name", "").lower().strip()
        if norm:
            by_name[norm].append(r)

    print("\n=== COMBINED RECORD VERIFICATION ===")
    for crec in combined:
        name = crec.get("name", "")
        norm = name.lower().strip()
        parts = by_name.get(norm, [])

        print(f"\n{name}  (id={crec['player_id']})")
        # Hitting verification
        if crec.get("batted"):
            team_lines = []
            for r in parts:
                if r.get("batted"):
                    team_lines.append(
                        f"  [{r['team']}] AB={r['AB']} H={r['H']} "
                        f"AVG={r['AVG']} OBP={r['OBP']} SLG={r['SLG']} OPS={r['OPS']}"
                    )
            for line in team_lines:
                print(line)
            # Expected sums
            exp_ab = sum(_gs(r,"AB") for r in parts if r.get("batted"))
            exp_h  = sum(_gs(r,"H")  for r in parts if r.get("batted"))
            print(f"  [COMBINED]  AB={crec['AB']} (exp {exp_ab}) "
                  f"H={crec['H']} (exp {exp_h}) "
                  f"H_match={'OK' if crec['H']==exp_h else 'MISMATCH'} "
                  f"AB_match={'OK' if crec['AB']==exp_ab else 'MISMATCH'}")
            print(f"  AVG={crec['AVG']} OBP={crec['OBP']} "
                  f"SLG={crec['SLG']} OPS={crec['OPS']}")

        # Pitching verification
        if crec.get("is_pitcher") and crec.get("pitching"):
            cp = crec["pitching"]
            for r in parts:
                if r.get("is_pitcher") and r.get("pitching"):
                    rp = r["pitching"]
                    print(f"  [{r['team']}] IP={rp['IP']} ER={rp['ER']} "
                          f"ERA={rp['ERA']} BB={rp['BB']} H={rp['H']} WHIP={rp['WHIP']}")
            exp_outs = sum(_ip_to_outs(r["pitching"].get("IP","0.0"))
                           for r in parts if r.get("is_pitcher") and r.get("pitching"))
            exp_er = sum(int(r["pitching"].get("ER",0) or 0)
                         for r in parts if r.get("is_pitcher") and r.get("pitching"))
            exp_h  = sum(int(r["pitching"].get("H",0) or 0)
                         for r in parts if r.get("is_pitcher") and r.get("pitching"))
            print(f"  [COMBINED]  IP={cp['IP']} ER={cp['ER']} (exp {exp_er}) "
                  f"ERA={cp['ERA']} BB={cp['BB']} H={cp['H']} (exp {exp_h}) WHIP={cp['WHIP']}")
    print("\n=== END VERIFICATION ===\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    token = os.environ.get("GC_TOKEN", "")
    teams = json.load(open("teams.json"))

    all_records = []
    for name, team_id in teams.items():
        if not team_id or team_id.startswith("PASTE"):
            print(f"skip {name}: team_id not set yet")
            continue
        stats = fetch.fetch_team_stats(team_id, token)
        players = fetch.fetch_team_players(team_id, token)
        recs = transform.build_records(stats, players)
        for r in recs:
            r["team"] = name
        all_records.extend(recs)
        print(f"{name}: {len(recs)} players")

    # Detect ERA multiplier from real pitcher data
    era_mult = _detect_era_mult(all_records)
    print(f"ERA multiplier: {era_mult}")

    # Build and append combined records for multi-team players
    combined = build_combined_records(all_records, era_mult)
    print_combined_verification(combined, all_records)
    all_records.extend(combined)
    print(f"Added {len(combined)} combined record(s) for multi-team players")

    json.dump(all_records, open("data.json", "w"), indent=2)
    print(f"wrote data.json ({len(all_records)} players total)")


if __name__ == "__main__":
    try:
        main()
    except fetch.TokenLapsed as e:
        # Fail loud so GitHub emails you to refresh the token
        print(f"::error::{e}")
        sys.exit(2)
