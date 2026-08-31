import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from leader_rules import analyze_graph

EXEC_NODES = [
    {"id": "ceo", "label": "CEO", "group": "executive", "external": False},
    {"id": "cfo", "label": "CFO", "group": "finance", "external": False},
    {"id": "marketing", "label": "Marketing", "group": "marketing", "external": False},
]
EXEC_EDGES = [
    {"source": "ceo", "target": "cfo", "label": "oversees finance", "group": "gov"},
    {"source": "ceo", "target": "marketing", "label": "oversees marketing", "group": "gov"},
    {"source": "cfo", "target": "marketing", "label": "approves marketing budget", "group": "flow"},
]


def test_marketing_is_a_gap_and_cfo_is_not():
    out = analyze_graph(EXEC_NODES, EXEC_EDGES)
    assert out["departments"]["marketing"]["leader_present"] is False
    assert out["departments"]["marketing"]["recommended_title"] == "CMO"
    assert out["departments"]["marketing"]["name"] == "Marketing"
    assert out["departments"]["cfo"]["leader_present"] is True
    assert "marketing" in out["gaps"]
    assert "cfo" not in out["gaps"]


def test_role_children_count_as_that_departments_titles():
    nodes = [
        {"id": "lead", "label": "Leadership", "group": "governance", "external": False},
        {"id": "lead::role::0", "label": "CEO", "group": "role", "external": False},
        {"id": "lead::role::1", "label": "CFO / COO", "group": "role", "external": False},
    ]
    edges = [
        {"source": "lead", "target": "lead::role::0", "label": "has role", "group": "role"},
        {"source": "lead", "target": "lead::role::1", "label": "has role", "group": "role"},
    ]
    out = analyze_graph(nodes, edges)
    assert out["departments"]["lead"]["leader_present"] is True
    assert "lead::role::0" not in out["departments"]  # role nodes are not departments


def test_external_nodes_are_skipped():
    nodes = [
        {"id": "cust", "label": "Market & Customers", "group": "market", "external": True},
        {"id": "mkt", "label": "Marketing", "group": "gtm", "external": False},
    ]
    out = analyze_graph(nodes, [])
    assert "cust" not in out["departments"]
    assert "mkt" in out["departments"]


def test_unknown_department_gets_head_of_not_ceo():
    nodes = [{"id": "rad", "label": "Radiology", "group": "clinical", "external": False}]
    out = analyze_graph(nodes, [])
    assert out["departments"]["rad"]["recommended_title"] == "Head of Radiology"


def test_schema_rules_override_the_suggested_title():
    nodes = [{"id": "rad", "label": "Radiology", "group": "clinical", "external": False}]
    rules = {"titles": {"rad": "Chief of Radiology"}}
    out = analyze_graph(nodes, [], rules)
    assert out["departments"]["rad"]["recommended_title"] == "Chief of Radiology"


def test_summary_counts_and_coverage():
    out = analyze_graph(EXEC_NODES, EXEC_EDGES)
    assert out["summary"]["departments"] == 3
    assert out["summary"]["gaps"] == len(out["gaps"])
    assert out["summary"]["coverage_pct"] == round(100 * (3 - len(out["gaps"])) / 3)


from detect_phantoms import handle_request


def test_handle_request_returns_analysis():
    status, body = handle_request({"nodes": EXEC_NODES, "edges": EXEC_EDGES})
    assert status == 200
    assert "marketing" in body["gaps"]


def test_handle_request_rejects_missing_nodes():
    status, body = handle_request({"edges": []})
    assert status == 400
    assert "nodes" in body["error"]


def test_handle_request_defaults_missing_edges_to_empty():
    status, body = handle_request({"nodes": EXEC_NODES})
    assert status == 200
    assert body["summary"]["departments"] == 3
