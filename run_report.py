import json
import sys

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "api"))

from leader_rules import check_department_leaders


def load_roster(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def flatten(roster):
    titles = []
    for positions in roster.values():
        titles.extend(positions)
    return titles


def build_report(roster, departments):
    titles = flatten(roster)
    print(f"checking {len(titles)} titles", file=sys.stderr)

    results, recommendations = check_department_leaders(titles, departments)

    report = {
        "total_positions": len(titles),
        "groups": {group: len(positions) for group, positions in roster.items()},
        "departments": {},
        "gaps": [],
        "recommendations": recommendations,
    }

    for dept, present in results.items():
        report["departments"][dept] = {
            "positions_listed": len(roster.get(dept, [])),
            "leader_present": present,
            "recommended_title": recommendations.get(dept),
        }
        if not present:
            report["gaps"].append(dept)

    print(f"{len(report['gaps'])} gaps found", file=sys.stderr)
    return report


def print_report(report):
    print("ORG LEADER REPORT")
    print(f"{report['total_positions']} positions across {len(report['groups'])} groups")
    print()
    print(f"{'DEPARTMENT':<12}{'POSITIONS':>10}  {'LEADER':<9}  ACTION")
    print("-" * 48)

    for dept, row in report["departments"].items():
        status = "Present" if row["leader_present"] else "MISSING"
        title = row["recommended_title"]
        if row["leader_present"]:
            action = "-"
        elif title:
            action = f"add {title}"
        else:
            action = "not staffed at all"
        print(f"{dept:<12}{row['positions_listed']:>10}  {status:<9}  {action}")

    print("-" * 48)
    if report["gaps"]:
        print(f"gaps: {', '.join(report['gaps'])}")
    else:
        print("gaps: none")


def save_json(report, path):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(f"saved {path}", file=sys.stderr)


def main():
    roster_path = "org_roster.json"
    output_path = "leader_report.json"
    departments = None

    roster = load_roster(roster_path)
    report = build_report(roster, departments)
    print_report(report)
    save_json(report, output_path)


if __name__ == "__main__":
    main()
