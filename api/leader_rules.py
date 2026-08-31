import re


def check_department_leaders(ranks, departments=None):
    if departments is None:
        departments = ["marketing", "sales", "finance", "hr", "legal", "business"]

    leader_pattern = re.compile(
        r"\bdirector\b|\b\w*vp\b|\bvice\s*president\b", re.IGNORECASE
    )

    dept_alias_map = {
        "marketing": ["marketing"],
        "sales": ["sales", "revenue"],
        "finance": ["finance", "financial"],
        "hr": ["hr", "human resources", "human resource", "people"],
        "legal": ["legal"],
        "business": ["business"],
    }

    c_level_map = {
        "marketing": [r"cmo", r"chief\s+marketing\s+officer"],
        "sales": [
            r"cro",
            r"cso",
            r"chief\s+revenue\s+officer",
            r"chief\s+sales\s+officer",
        ],
        "finance": [r"cfo", r"chief\s+financial\s+officer"],
        "hr": [
            r"chro",
            r"cho",
            r"chief\s+human\s+resources?\s+officer",
            r"chief\s+people\s+officer",
        ],
        "legal": [
            r"clo",
            r"cco",
            r"chief\s+legal\s+officer",
            r"chief\s+compliance\s+officer",
        ],
        "business": [
            r"cbo",
            r"cgo",
            r"csgo",
            r"chief\s+business\s+officer",
            r"chief\s+growth\s+officer",
            r"chief\s+strategy\s+and\s+growth\s+officer",
        ],
    }

    recommend_map = {
        "marketing": "CMO",
        "sales": "CRO",
        "finance": "CFO",
        "hr": "CHRO",
        "legal": "CLO",
        "business": "CBO",
    }

    normalized_ranks = [r.lower() for r in ranks]

    results = {}
    recommendations = {}
    for dept in departments:
        dept_lower = dept.lower()
        aliases = dept_alias_map.get(dept_lower, [dept_lower])
        dept_pattern = re.compile(
            r"\b(?:" + "|".join(re.escape(a) for a in aliases) + r")\b"
        )
        c_titles = c_level_map.get(dept_lower, [])

        has_leader = any(
            (dept_pattern.search(rank) and leader_pattern.search(rank))
            or any(re.search(rf"\b{c}\b", rank) for c in c_titles)
            for rank in normalized_ranks
        )
        results[dept] = has_leader

        if not has_leader:
            dept_mentioned = any(dept_pattern.search(rank) for rank in normalized_ranks)
            if dept_mentioned:
                recommendations[dept] = recommend_map.get(dept_lower, "CEO")

    return results, recommendations


def print_missing_leaders(ranks, departments=None):
    results, recommendations = check_department_leaders(ranks, departments)

    for dept, present in results.items():
        status = "Present" if present else "MISSING"
        print(f"{dept.capitalize()} Leader: {status}")

    if recommendations:
        print("\nRecommended titles to add:")
        for dept, title in recommendations.items():
            print(f"  {dept.capitalize()}: {title}")



GENERIC_LEADER = re.compile(
    r"\bdirector\b|\b\w*vp\b|\bvice\s*president\b|\bhead\s+of\b"
    r"|\bchief\b.*\bofficer\b|\bc[a-z]{1,3}o\b|\bpresident\b",
    re.IGNORECASE,
)


def dept_alias_map():
    """Departments the rulebook has explicit C-title knowledge for."""
    return {
        "marketing", "sales", "revenue", "finance", "financial",
        "hr", "human resources", "human resource", "people", "legal", "business",
    }


def _generic_leader(titles):
    """Is any of these titles leader-level at all, for a department the rulebook
    has no specific C-titles for (Radiology, Leadership, a standalone CFO box)."""
    return any(GENERIC_LEADER.search(t or "") for t in titles)


ROLE_GROUP = "role"


def _role_children(node_id, nodes_by_id, edges):
    """Labels of nodes this department owns via 'has role' style edges."""
    out = []
    for e in edges:
        if e.get("source") != node_id:
            continue
        child = nodes_by_id.get(e.get("target"))
        if child and child.get("group") == ROLE_GROUP:
            out.append(child.get("label", ""))
    return out


def _suggested_title(dept_id, name, rules):
    """Schema rules win, then the known map, then a generic head-of title."""
    titles = (rules or {}).get("titles") or {}
    if dept_id in titles:
        return titles[dept_id]
    known = {
        "marketing": "CMO", "sales": "CRO", "finance": "CFO",
        "hr": "CHRO", "legal": "CLO", "business": "CBO",
    }
    key = name.strip().lower()
    if key in known:
        return known[key]
    return "Head of " + name


def analyze_graph(nodes, edges, rules=None):
    """Every non-role, non-external node is a department. Its titles are its own
    label plus its role children's labels. Schema-agnostic by construction - no
    hardcoded department list."""
    nodes_by_id = {n["id"]: n for n in nodes}
    only = set((rules or {}).get("departments") or [])

    departments, gaps = {}, []
    for n in nodes:
        if n.get("group") == ROLE_GROUP or n.get("external"):
            continue
        if only and n["id"] not in only:
            continue

        name = n.get("label") or n["id"]
        titles = [name] + _role_children(n["id"], nodes_by_id, edges)
        if name.strip().lower() in dept_alias_map():
            # a department the rulebook knows: use the strict, department-aware
            # check so a Sales Director never counts as Marketing's leader
            results, _ = check_department_leaders(titles, [name])
            present = results[name]
        else:
            # any other node (Leadership, Radiology, a CFO box): the rulebook has
            # no C-titles for it, so ask the generic question instead
            present = _generic_leader(titles)

        departments[n["id"]] = {
            "name": name,
            "leader_present": present,
            "recommended_title": None if present else _suggested_title(n["id"], name, rules),
        }
        if not present:
            gaps.append(n["id"])

    total = len(departments)
    return {
        "departments": departments,
        "gaps": gaps,
        "summary": {
            "departments": total,
            "gaps": len(gaps),
            "coverage_pct": round(100 * (total - len(gaps)) / total) if total else 100,
        },
    }


def _selfcheck():
    baseline_ranks = [
        "CEO",
        "CFO",
        "CLO",
        "Marketing Manager",
        "Sales Executive",
        "Finance Executive",
        "HR Manager",
        "Legal Executive",
        "Business Executive",
    ]
    results, recommendations = check_department_leaders(baseline_ranks)
    assert results == {
        "marketing": False,
        "sales": False,
        "finance": True,
        "hr": False,
        "legal": True,
        "business": False,
    }, results
    assert recommendations == {
        "marketing": "CMO",
        "sales": "CRO",
        "hr": "CHRO",
        "business": "CBO",
    }, recommendations

    spelled, _ = check_department_leaders(
        ["Chief Marketing Officer", "Chief Legal Officer", "Chief People Officer"]
    )
    assert spelled["marketing"] is True, spelled
    assert spelled["legal"] is True, spelled
    assert spelled["hr"] is True, spelled

    synonym, _ = check_department_leaders(
        ["Chief Financial Officer", "Revenue Director"]
    )
    assert synonym["finance"] is True, synonym
    assert synonym["sales"] is True, synonym

    boundary, _ = check_department_leaders(["Paralegal Director"], ["legal"])
    assert boundary["legal"] is False, boundary

    _, custom = check_department_leaders(["Engineering Manager"], ["engineering"])
    assert custom == {"engineering": "CEO"}, custom

    print("selfcheck ok")


def main():
    sample_ranks = [
        "CEO",
        "CFO",
        "CLO",
        "Marketing Manager",
        "Sales Executive",
        "Finance Executive",
        "HR Manager",
        "Legal Executive",
        "Business Executive",
    ]
    departments = None

    _selfcheck()
    print()
    print_missing_leaders(sample_ranks, departments)


if __name__ == "__main__":
    main()