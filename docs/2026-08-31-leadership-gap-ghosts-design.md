# Leadership Gap Ghosts — Design

Date: 2026-08-31
Status: approved

## Problem

`department_leader_check.py` finds departments with staff but no leader-level
title. Today that answer only exists as terminal text. Graph Loom shows the org
as a graph but has no idea a box is missing.

Joining them: a department with staff and no leader is where an informal leader
hides. Drawing that empty seat on the graph — attached exactly where the missing
person would have sat — turns a text report into something a room full of people
can read at a glance.

The feature must work for any company's schema, not the six departments the
Python currently hardcodes.

## Boundary

The API detects. The browser draws.

| Component | Responsibility |
|---|---|
| `api/leader_rules.py` | Existing `check_department_leaders()` (unchanged) + a graph adapter |
| `api/detect_phantoms.py` | Vercel HTTP entrypoint. Parse, call, return JSON. No logic. |
| `index.html` | Button, ghost nodes and edges, legend, error states |

The Python never computes graph geometry or ghost edges. The page never
re-implements leader rules. Neither can drift into being a second copy of the
other.

`check_department_leaders()` keeps its exact current signature and behaviour;
its existing `_selfcheck()` must still pass untouched. New code wraps it.

## What counts as a department

No hardcoded department list. The rule, in priority order:

1. `leadership_rules` in the pasted schema, if present (explicit override)
2. Otherwise: **every non-role node is a candidate department.** Its titles are
   its own label plus the labels of its role-children.

Nodes marked `"external": true` are skipped — customers and regulators do not
need a CMO.

Verified against both real schemas:

| Schema | Node | Titles considered | Result |
|---|---|---|---|
| Exec team | Marketing | `["Marketing"]` | no leader → gap, suggest CMO |
| Exec team | CFO | `["CFO"]` | leader present |
| Company Anatomy | Leadership | `["Leadership","CEO","Chief Product Officer","CTO","CFO / COO"]` | leader present |
| Company Anatomy | Marketing | `["Marketing","Content Marketer","Growth Marketer","Brand & PR","SEO / ASO"]` | no leader → gap |
| Company Anatomy | Market & Customers | — | skipped, external |

### Recommended title resolution

1. `leadership_rules.titles[department]` from the schema
2. The existing `recommend_map` (CMO, CRO, CFO, CHRO, CLO, CBO)
3. `Head of <Department Name>`

Step 3 replaces the current `recommend_map.get(dept_lower, "CEO")` fallback,
which recommends "CEO" for any unknown department — wrong, and already visible
in the existing selfcheck (`["Engineering Manager"] → {"engineering": "CEO"}`).

## Contract

```
POST /api/detect_phantoms

{
  "nodes": [ { "id", "label", "group", "external" } ],
  "edges": [ { "source", "target", "label", "group" } ],
  "rules": { ...optional leadership_rules from the schema... }
}
```

```
200 OK

{
  "departments": {
    "gtm_marketing": {
      "name": "Marketing",
      "leader_present": false,
      "recommended_title": "CMO"
    }
  },
  "gaps": ["gtm_marketing"],
  "summary": { "departments": 6, "gaps": 2, "coverage_pct": 67 }
}
```

Departments are keyed by **node id**, not label — two nodes may share a label,
ids are unique, and the browser needs the id to anchor the ghost. `name` carries
the human label for display.

The endpoint is `detect_phantoms` (underscore) to match the Python filename;
the `PHANTOM_ENDPOINT` constant in the page changes to match. No `vercel.json`
rewrite needed.

## Ghost rendering

For each department in `gaps`:

- **Ghost node** — id `ghost::<department node id>`, label `<Recommended Title> (suggested)`,
  group `suggested`. Hollow outline, its own legend colour.
- **Direct edge** — `ghost ⇢ department`, dashed, label `would lead`.
- **Indirect edges, mirrored from the user's own schema** — every existing
  non-role edge touching the department node is copied onto the ghost, dashed,
  labelled `would: <original label>`. So `ceo → marketing "oversees marketing"`
  yields `ceo ⇢ CMO "would: oversees marketing"`. Nothing is invented; the ghost
  inherits the relationships the real person would have had.
- **Fallback** — a department with no non-role edges gets one dashed edge to the
  most-connected node in the graph, labelled `would report to`, so it is not an
  island.

Re-running clears previous ghosts before drawing, so repeated clicks never
duplicate. Ghosts export through Export JSON tagged `"suggested": true`.

## Failure behaviour

| Condition | Behaviour |
|---|---|
| API unreachable | Existing message in `#json-error`; graph untouched |
| No gaps found | "Every department has a leader"; no ghosts drawn |
| Schema has no groups | Still works — each node is its own department |
| Malformed response | Error message; graph untouched |

## Verification

**Python** — every existing `_selfcheck()` assertion stays exactly as written;
new assertions are appended for graph-level cases using both real
schemas: exec team yields a marketing gap and a finance non-gap; Company Anatomy
yields Leadership led and Marketing gapped; external nodes are skipped; an
unknown department resolves to `Head of <Name>` rather than CEO.

**Browser** — Playwright with a stubbed API response asserting: ghost nodes
appear with the right count, their edges are dashed, mirrored edges match the
department's real edges, and a second click replaces rather than duplicates.

**Manual** — deploy, click the button on the live site against the exec schema.

## Out of scope

Phantom RAG detection (separate button, its own design), promoting a ghost into
a real node, persisting results between sessions.
