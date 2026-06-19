"""
Daily job: pull every team's GameChanger stats and write a single data.json
that widget.html reads. Run by the GitHub Action; token comes from GC_TOKEN.
"""
import os
import sys
import json
import fetch
import transform


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

    json.dump(all_records, open("data.json", "w"), indent=2)
    print(f"wrote data.json ({len(all_records)} players total)")


if __name__ == "__main__":
    try:
        main()
    except fetch.TokenLapsed as e:
        # Fail loud so GitHub emails you to refresh the token
        print(f"::error::{e}")
        sys.exit(2)
