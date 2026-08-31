# Leadership Gap Ghosts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clicking "Detect phantom nodes" in Graph Loom draws a dashed ghost node for every department that has staff but no leader, wired into the graph exactly where the missing person would have sat.

**Architecture:** A Vercel Python serverless function wraps the existing `check_department_leaders()` with a graph adapter that treats every non-role node as a department. It returns gaps and recommended titles only. The browser owns all drawing: it creates ghost nodes, a direct "would lead" edge, and dashed copies of every real edge touching the department.

**Tech Stack:** Python 3.9+ stdlib only (no pip dependencies), Vercel Python runtime, vanilla JS in a single `index.html`, Playwright for browser tests.

## Global Constraints

- **No pip dependencies.** `leader_rules.py` and `detect_phantoms.py` import only `re`, `json`, and `http.server`. Vercel installs nothing.
- **`check_department_leaders()` is frozen.** Its signature, body, and every existing `_selfcheck()` assertion stay byte-for-byte identical. New code wraps it; nothing edits it.
- **Departments are keyed by node id**, never by label. Labels repeat, ids do not.
- **Nodes with `"external": true` are never given a ghost.**
- **Endpoint path is `/api/detect_phantoms`** (underscore), matching the Python filename.
- **Ghost ids are `ghost::<department node id>`** and ghost group is `suggested`, everywhere, in both API-facing and browser code.
- All new Python lives under `api/`; the page stays a single self-contained `index.html`.

---

## File Structure

| File | Responsibility |
|---|---|
| `api/leader_rules.py` | Existing detection logic (frozen) + new `analyze_graph()` adapter |
| `api/detect_phantoms.py` | Vercel HTTP entrypoint. Parse body, call `analyze_graph`, return JSON. No logic. |
| `index.html` | Button wiring, ghost node/edge construction, clearing, legend |
| `tests/test_leader_rules.py` | Python tests for `analyze_graph` |
| `tests/test_ghosts.js` | Playwright test for ghost rendering against a stubbed API |

---

### Task 1: Graph adapter — departments from any schema

**Files:**
- Modify: `api/leader_rules.py` (append below existing code; do not touch lines 1–99)
- Test: `tests/test_leader_rules.py`

**Interfaces:**
- Consumes: `check_department_leaders(ranks, departments=None) -> (results, recommendations)` — already in the file, unchanged.
- Produces: `analyze_graph(nodes, edges, rules=None) -> dict` where `nodes` is a list of `{"id","label","group","external"}`, `edges` a list of `{"source","target","label","group"}`, `rules` an optional dict. Returns `{"departments": {node_id: {"name","leader_present","recommended_title"}}, "gaps": [node_id], "summary": {"departments","gaps","coverage_pct"}}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_leader_rules.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_leader_rules.py -v`
Expected: FAIL — `ImportError: cannot import name 'analyze_graph'`

- [ ] **Step 3: Write minimal implementation**

Append to the **end** of `api/leader_rules.py`, above the `if __name__ == "__main__":` block:

```python
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
        # one department at a time: ask the frozen checker about this dept only
        results, _ = check_department_leaders(titles, [name])
        present = results[name]

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_leader_rules.py -v`
Expected: PASS, 6 passed

Run: `python3 api/leader_rules.py`
Expected: first line `selfcheck ok` — the frozen assertions still hold.

- [ ] **Step 5: Commit**

```bash
git add api/leader_rules.py tests/test_leader_rules.py
git commit -m "feat: add analyze_graph adapter - departments derived from graph, not hardcoded"
```

---

### Task 2: Vercel HTTP entrypoint

**Files:**
- Create: `api/detect_phantoms.py`
- Test: `tests/test_leader_rules.py` (append)

**Interfaces:**
- Consumes: `analyze_graph(nodes, edges, rules=None) -> dict` from Task 1.
- Produces: `handle_request(payload: dict) -> (status_code: int, body: dict)` — pure function the test calls directly; the `handler` class only adapts HTTP to it.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_leader_rules.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_leader_rules.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'detect_phantoms'`

- [ ] **Step 3: Write minimal implementation**

Create `api/detect_phantoms.py`:

```python
"""Vercel entrypoint. HTTP plumbing only - all logic lives in leader_rules."""
import json
from http.server import BaseHTTPRequestHandler

from leader_rules import analyze_graph


def handle_request(payload):
    """Pure: dict in, (status, dict) out. Tested directly, no server needed."""
    if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
        return 400, {"error": "expected JSON body with a 'nodes' list"}
    return 200, analyze_graph(
        payload["nodes"],
        payload.get("edges") or [],
        payload.get("rules"),
    )


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as err:
            status, body = 400, {"error": "invalid JSON: " + str(err)}
        else:
            status, body = handle_request(payload)
        self._send(status, body)

    def do_OPTIONS(self):
        self._send(204, None)

    def _send(self, status, body):
        raw = b"" if body is None else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        if raw:
            self.wfile.write(raw)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_leader_rules.py -v`
Expected: PASS, 9 passed

- [ ] **Step 5: Commit**

```bash
git add api/detect_phantoms.py tests/test_leader_rules.py
git commit -m "feat: add Vercel serverless entrypoint for leadership gap detection"
```

---

### Task 3: Ghost rendering in the page

**Files:**
- Modify: `index.html` — the `PHANTOM_ENDPOINT` constant and the `btn-detect-phantom` click handler
- Test: `tests/test_ghosts.js`

**Interfaces:**
- Consumes: the API response shape from Task 2 — `{departments, gaps, summary}`.
- Produces: browser-side functions `clearGhosts()` and `drawGhosts(report)` inside the page's IIFE, plus ghost nodes carrying `suggested: true`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ghosts.js`:

```javascript
const { chromium } = require('playwright');

const SCHEMA = {
  nodes: [
    { id: 'ceo', label: 'CEO', group: 'executive' },
    { id: 'cfo', label: 'CFO', group: 'finance' },
    { id: 'marketing', label: 'Marketing', group: 'marketing' }
  ],
  edges: [
    { source: 'ceo', target: 'cfo', label: 'oversees finance' },
    { source: 'ceo', target: 'marketing', label: 'oversees marketing' },
    { source: 'cfo', target: 'marketing', label: 'approves marketing budget' }
  ]
};

const STUB = {
  departments: {
    ceo: { name: 'CEO', leader_present: true, recommended_title: null },
    cfo: { name: 'CFO', leader_present: true, recommended_title: null },
    marketing: { name: 'Marketing', leader_present: false, recommended_title: 'CMO' }
  },
  gaps: ['marketing'],
  summary: { departments: 3, gaps: 1, coverage_pct: 67 }
};

(async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
  const page = await browser.newPage({ viewport: { width: 1000, height: 800 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));

  // stub the API so the test never needs a live backend
  await page.route('**/api/detect_phantoms', route =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(STUB) }));

  await page.goto('file://' + process.cwd() + '/index.html');
  await page.click('#btn-edit');
  await page.fill('#json-input', JSON.stringify(SCHEMA));
  await page.click('#btn-apply-json');
  await page.waitForTimeout(4000);

  await page.click('#btn-detect-phantom');
  await page.waitForTimeout(1500);

  const first = await page.evaluate(() => {
    const labels = [...document.querySelectorAll('#scene text')].map(t => t.textContent);
    const dashed = document.querySelectorAll('#scene line[stroke-dasharray]').length;
    return { labels, dashed };
  });

  const ghostCount = first.labels.filter(l => l.includes('suggested')).length;
  console.log('ghost nodes (want 1):', ghostCount);
  console.log('dashed edges (want 3: would lead + 2 mirrored):', first.dashed);

  // second click must replace, not duplicate
  await page.click('#btn-detect-phantom');
  await page.waitForTimeout(1500);
  const second = await page.evaluate(() =>
    [...document.querySelectorAll('#scene text')].map(t => t.textContent)
      .filter(l => l.includes('suggested')).length);
  console.log('ghost nodes after 2nd click (want 1):', second);
  console.log('page errors (want none):', errors);

  const ok = ghostCount === 1 && first.dashed === 3 && second === 1 && errors.length === 0;
  console.log(ok ? 'PASS' : 'FAIL');
  await browser.close();
  process.exit(ok ? 0 : 1);
})();
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node tests/test_ghosts.js`
Expected: FAIL — `ghost nodes (want 1): 0`, because the click handler still expects `phantom_ids` and draws nothing.

- [ ] **Step 3: Write minimal implementation**

In `index.html`, change the endpoint constant:

```javascript
const PHANTOM_ENDPOINT = '/api/detect_phantoms';
```

Replace the entire `btn-detect-phantom` click handler with:

```javascript
  // ghosts are drawn, never persisted - clearing is always safe
  function clearGhosts(){
    nodes = nodes.filter(n => !n.suggested);
    edges = edges.filter(e => !e.suggested);
  }

  function drawGhosts(report){
    clearGhosts();
    const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
    // busiest node, used only when a department has nothing else attached
    const degree = {};
    edges.forEach(e => { degree[e.source] = (degree[e.source]||0)+1; degree[e.target] = (degree[e.target]||0)+1; });
    const busiest = nodes.slice().sort((a,b) => (degree[b.id]||0) - (degree[a.id]||0))[0];

    (report.gaps || []).forEach(deptId => {
      const dept = byId[deptId];
      const info = report.departments[deptId];
      if (!dept || !info) return;

      const ghost = { id: 'ghost::' + deptId, label: info.recommended_title + ' (suggested)',
                      group: 'suggested', suggested: true,
                      about: 'No leader found for ' + info.name + '. This seat is a suggestion, not a real person.',
                      x: dept.x + 40, y: dept.y - 40, vx: 0, vy: 0 };
      nodes.push(ghost);

      const link = (source, target, label) => edges.push({
        source, target, label, group: 'suggested', dashed: true, suggested: true,
        s: source === ghost.id ? ghost : byId[source], t: target === ghost.id ? ghost : byId[target],
        _eid: nextEdgeId++
      });

      link(ghost.id, deptId, 'would lead');

      // mirror the department's real relationships onto the empty seat
      const real = edges.filter(e => !e.suggested && e.group !== 'role' &&
                                     (e.source === deptId || e.target === deptId));
      real.forEach(e => {
        const other = e.source === deptId ? e.target : e.source;
        if (other === ghost.id || !byId[other] || byId[other].group === 'role') return;
        link(other, ghost.id, 'would: ' + (e.label || 'relate'));
      });

      if (real.length === 0 && busiest && busiest.id !== deptId) link(ghost.id, busiest.id, 'would report to');
    });

    refreshScene();
  }

  document.getElementById('btn-detect-phantom').addEventListener('click', async () => {
    const errEl = document.getElementById('json-error');
    if (!nodes.length) { errEl.textContent = 'Load a graph first.'; return; }
    errEl.textContent = 'Checking leadership coverage…';
    try {
      const res = await fetch(PHANTOM_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nodes: nodes.filter(n => !n.suggested).map(n => ({ id: n.id, label: n.label, group: n.group, external: !!n.external })),
          edges: edges.filter(e => !e.suggested).map(e => ({ source: e.source, target: e.target, label: e.label || '', group: e.group || '' })),
          rules: currentRules
        })
      });
      if (!res.ok) throw new Error('detector returned ' + res.status);
      const report = await res.json();
      drawGhosts(report);
      const s = report.summary || {};
      errEl.textContent = (report.gaps || []).length
        ? s.gaps + ' of ' + s.departments + ' departments have no leader (' + s.coverage_pct + '% covered). Suggested seats drawn as dashed nodes.'
        : 'Every department has a leader.';
    } catch (err) {
      errEl.textContent = 'Leadership detector not reachable (' + err.message +
        '). It runs on Vercel at ' + PHANTOM_ENDPOINT + ' — works on the deployed site, not on a local file.';
    }
  });
```

Add `currentRules` next to the other top-level state declarations (near `let nodes = [], edges = []`):

```javascript
  let currentRules = null;   // leadership_rules from the pasted schema, if any
```

And capture it in `loadGraph()`, immediately after `const g = normalize(raw);`:

```javascript
    currentRules = raw && raw.leadership_rules ? raw.leadership_rules : null;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node tests/test_ghosts.js`
Expected: PASS — `ghost nodes (want 1): 1`, `dashed edges (want 3...): 3`, `ghost nodes after 2nd click (want 1): 1`, `page errors (want none): []`

- [ ] **Step 5: Verify the exported graph excludes nothing it should**

Run: `node tests/test_ghosts.js` then manually in the browser: click Export JSON after detecting. Ghost nodes appear with `"suggested": true` and are visually distinguishable in the legend under the `suggested` group.

- [ ] **Step 6: Commit**

```bash
git add index.html tests/test_ghosts.js
git commit -m "feat: draw suggested-leader ghost nodes wired into the schema's own relationships"
```

---

### Task 4: Deploy configuration and live verification

**Files:**
- Create: `requirements.txt` (empty marker so Vercel selects the Python runtime deterministically)
- Modify: none

**Interfaces:**
- Consumes: `api/detect_phantoms.py` from Task 2.
- Produces: a working `POST /api/detect_phantoms` on the deployed site.

- [ ] **Step 1: Create the runtime marker**

Create `requirements.txt` with a single comment line — the module uses only the standard library, but the file's presence makes Vercel's Python detection explicit:

```
# stdlib only - no dependencies
```

- [ ] **Step 2: Commit and push**

```bash
git add requirements.txt api/ index.html
git commit -m "chore: mark Python runtime for Vercel"
git push
```

- [ ] **Step 3: Verify the deployed function**

Run (replace with the live domain):

```bash
curl -s -X POST https://graph-plot-five.vercel.app/api/detect_phantoms \
  -H 'Content-Type: application/json' \
  -d '{"nodes":[{"id":"mkt","label":"Marketing","group":"gtm"}],"edges":[]}'
```

Expected: `{"departments": {"mkt": {"name": "Marketing", "leader_present": false, "recommended_title": "CMO"}}, "gaps": ["mkt"], "summary": {"departments": 1, "gaps": 1, "coverage_pct": 0}}`

- [ ] **Step 4: Verify in the browser**

Open the live site, paste the exec team schema, click **Detect phantom nodes**.
Expected: one dashed `CMO (suggested)` node attached to Marketing, dashed edges from CEO and CFO mirroring "oversees marketing" and "approves marketing budget", and the message `1 of 3 departments have no leader (67% covered).`

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "fix: deployment adjustments for leadership gap endpoint"
git push
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| API detects, browser draws | 1 (analyze_graph), 3 (drawGhosts) |
| `check_department_leaders` frozen | 1, Step 4 re-runs `selfcheck ok` |
| Department = every non-role node | 1, `analyze_graph` |
| Role children count as department titles | 1, `test_role_children_count_as_that_departments_titles` |
| External nodes skipped | 1, `test_external_nodes_are_skipped` |
| Title: rules → known map → `Head of <Name>` | 1, `_suggested_title` + two tests |
| Departments keyed by node id | 1, keys are `n["id"]` throughout |
| Endpoint `/api/detect_phantoms` | 2, 3 (constant), 4 (curl) |
| Ghost id / group / label format | 3, `drawGhosts` |
| Direct "would lead" edge | 3 |
| Mirrored indirect edges from real schema | 3, `real.forEach` |
| Fallback for edgeless department | 3, `if (real.length === 0 ...)` |
| Re-run replaces, no duplicates | 3, `clearGhosts()` + second-click assertion |
| Export tags ghosts `suggested: true` | 3, Step 5 |
| API unreachable → message, graph intact | 3, catch block |
| No gaps → "Every department has a leader" | 3, message branch |
| Playwright verification | 3 |

No gaps found.

**Placeholder scan:** No TBD/TODO, no "add error handling" without code, every code step carries complete code.

**Type consistency:** `analyze_graph(nodes, edges, rules)` in Task 1 matches the call in Task 2's `handle_request`. Response keys `departments` / `gaps` / `summary` are identical in Task 1's implementation, Task 2's test, Task 3's stub, and Task 4's curl output. `clearGhosts()` and `drawGhosts(report)` are named identically at definition and call site. Ghost id prefix `ghost::` and group `suggested` match across Task 3's implementation and its test's filter.
