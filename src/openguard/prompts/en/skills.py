"""Skill SKILL.md content — English.

Format per CodeBuddy Skill spec:
  - YAML frontmatter: name + description (required)
  - Markdown body: imperative-voice instructions (<5k words)
  - Body uses verb-first directives, not second-person

Skill files are installed to .codebuddy/skills/openguard-<name>/SKILL.md
and are loaded by the AI when it determines relevance.
"""
from __future__ import annotations


# ──────────────────────────────────────────────────────────────────────────────
# Skill content — one per /opg:* command
# ──────────────────────────────────────────────────────────────────────────────

SKILL_RUN = """\
---
name: openguard-run
description: >
  Use this skill when the user invokes /opg:run or asks to start a QA test
  task for a requirement, code modification, or bug fix.
---

# openguard-run

## When to use
Trigger when user says `/opg:run <goal>` or asks to begin a test task.

## Execution model
This skill runs in **autonomous drive mode**: after creating the change, keep
advancing through all artifacts without waiting for the user — unless a
`wait_user` gate is reached or a genuine unknown requires human input.
The user said `/opg:run`, not `/opg:run then stop and wait`.

## Steps

**1. Confirm goal**
Ask "What should this QA task verify?" if the description is ambiguous.
Never guess the intent.

**2. Create the change**
Run in terminal:
```
openguard run "<goal>" [--from-openspec <id>] [--test-suite <suite>]
```

**3. Enter the drive loop**
After the command completes, read `state.yaml` and enter the drive loop below.
Keep looping until a stop condition is reached.

**4. Report to user**
Only report when the drive loop stops. Report: change ID, what was produced,
current state, and what (if anything) the user needs to decide.

## Drive Loop

After every CLI command or artifact generation, read `state.yaml` and act on
`agent_action`:

| `agent_action` | What to do |
| --- | --- |
| `run_cli` | Run `next_cli`, then loop |
| `generate` | Generate the artifacts in `missing`, write them, run `next_cli`, then loop |
| `resolve` | Read `unknowns.md`; resolve what you can autonomously; ask user for genuine unknowns, then loop |
| `wait_user` | **STOP.** Present the decision/summary to the user, wait for answer |
| `done` | **STOP.** Report completion summary to the user |

**Stop conditions (always pause):**
- `agent_action: wait_user` — especially `phase: ready_for_apply` (show summary, wait for confirmation)
- A genuine unknown that cannot be resolved from the codebase
- A blocker requiring a code fix
- Any CLI error

**Never stop for:**
- Generating a file (just generate it)
- Running `openguard _advance` (just run it)
- Resolving an unknown answerable from the codebase

## When generating test_knowledge.md

Include two machine-readable sections:

**a) YAML front matter:**
```yaml
external_preconditions:
  - some_state   # only if no case in this change produces it; [] otherwise
scene_map:        # Unity projects: executor uses this to auto-select entry scene
  login: Assets/Scenes/Login.unity   # key = logical name, value = scene path
  main: Assets/Scenes/Main.unity
```

**b) `## Cases` JSON block:**
```json
[
  {
    "id": "AC-001",
    "title": "Normal login",
    "produces_tags": ["logged_in"],
    "required_precondition_tags": []
  },
  {
    "id": "AC-005",
    "title": "Reconnect after disconnect",
    "produces_tags": [],
    "required_precondition_tags": ["logged_in"]
  }
]
```

Rules:
- `produces_tags`: states left behind when this case PASSES
- `required_precondition_tags`: states required BEFORE this case runs
- If B needs `logged_in` and A produces `logged_in` → matrix auto-orders A→B. Do NOT add to `external_preconditions`.
- Only add to `external_preconditions` when NO case in this change produces the state.
- Reason from semantics — never keyword-match.

## When generating test scripts
- Read `config.yaml` for `project.type`, `runtime`, `automation`
- `verified` scripts → reference directly
- `needs-review` → reference with annotation
- `stale`/`broken` → generate new draft in `openguard/changes/<id>/test_scripts/`
- Control channel by project type:
  - `web`/`h5`: Playwright
  - `webgl`/`web-game`: Playwright + JS bridge / WebSocket
  - `unity`: Unity Test Framework / WebSocket RPC
  - `unreal`: Automation Spec / console command
  - `backend`/`api`: HTTP API / gRPC

## Guardrails
- If a change with the same name exists, ask the user whether to continue or
  create new. Do not overwrite silently. This IS a stop condition.
- If goal is empty, ask — do not default.
- Write scripts only inside `openguard/`. Never write to project source directories.
- `phase: ready_for_apply` → MUST stop and show summary before allowing apply.
"""

# Backward-compat alias
SKILL_NEW = SKILL_RUN

SKILL_CONTINUE = """\
---
name: openguard-continue
description: >
  Manual recovery: use when the AI drive loop was interrupted, the conversation
  was reset, or you want to check current progress. In normal flow the drive
  loop runs automatically after /opg:run — you do not need to invoke this.
---

# openguard-continue

## When to use
Trigger when user says `/opg:continue` or asks to resume/check progress.
In normal flow, `/opg:run` drives the loop automatically. Use this only for
manual recovery after interruption.

## Drive Loop

After every CLI command or artifact generation, read `state.yaml` and act on
`agent_action`:

| `agent_action` | What to do |
| --- | --- |
| `run_cli` | Run `openguard continue` again, then loop |
| `generate` | Generate the missing artifact(s) listed in `missing_artifacts`, write them, then run `openguard continue` again and loop |
| `resolve` | Read `unknowns.md`; resolve items you can determine autonomously; for items requiring human input, ask the user, incorporate the answer, then loop |
| `wait_user` | **STOP.** Present the decision to the user and wait for their answer |
| `done` | **STOP.** Report completion summary to the user |

**Stop conditions (always pause and ask the user):**
- `agent_action: wait_user` in state.yaml
- A genuine unknown that cannot be resolved without domain knowledge the AI
  does not have (e.g., "what is the production server URL?")
- A blocker that requires a code fix before continuing
- Any error from a CLI command

**Never stop for:**
- Generating a file (just generate it)
- Running `openguard continue` again (just run it)
- Resolving an unknown that can be answered from the codebase (just answer it)

## Steps

**1. Run CLI**
```
openguard continue [--change <id>]
```

**2. Read state**
Read `state.yaml`. Check `agent_action` and `missing_artifacts`.

**3. Act per Drive Loop table above**

**4. When generating `test_knowledge.md`**

Include two machine-readable sections:

**a) YAML front matter:**
```yaml
external_preconditions:
  - some_state   # only if no case in this change produces it; [] otherwise
```

**b) `## Cases` JSON block:**
```json
[
  {
    "id": "AC-001",
    "title": "Normal login",
    "produces_tags": ["logged_in"],
    "required_precondition_tags": []
  },
  {
    "id": "AC-005",
    "title": "Reconnect after disconnect",
    "produces_tags": [],
    "required_precondition_tags": ["logged_in"]
  }
]
```

Rules:
- `produces_tags`: system states left behind when this case PASSES
- `required_precondition_tags`: states required BEFORE this case runs
- If B needs `logged_in` and A produces `logged_in` → matrix auto-orders A→B.
  Do NOT add to `external_preconditions`.
- `external_preconditions`: only when NO case in this change produces the state.
- Reason from semantics — never keyword-match.

**5. When generating test scripts**
- Read `config.yaml` for `project.type`, `runtime`, `automation`
- `verified` scripts → reference directly
- `needs-review` → reference with annotation
- `stale`/`broken` → generate new draft in `openguard/changes/<id>/test_scripts/`
- Control channel by project type:
  - `web`/`h5`: Playwright
  - `webgl`/`web-game`: Playwright + JS bridge / WebSocket
  - `unity`: Unity Test Framework / WebSocket RPC
  - `unreal`: Automation Spec / console command
  - `backend`/`api`: HTTP API / gRPC

## Guardrails
- Do not regenerate artifacts that already exist and are fresh.
- Do not reference `stale` or `broken` scripts.
- Write scripts only to `openguard/changes/<id>/test_scripts/`.
- Do not advance to apply if `unknowns.md` has unresolved items.
- Never use keyword matching to infer `produces_tags` or `required_precondition_tags`.
"""

SKILL_APPLY = """\
---
name: openguard-apply
description: >
  Use this skill when the user invokes /opg:apply or asks to run code Review
  and tests. Supports change-context mode (default) and suite mode (--suite).
---

# openguard-apply

## When to use
Trigger when user says `/opg:apply` or asks to execute tests.

## Change-context mode (default)

**1. Run**
```
openguard apply [--change <id>] [--test-suite <suite>] [--gate <gate>] [--review-level <level>]
```
Execution chain: `freshness check → code Review → toolchain ready → app ready → preconditions → test steps → report`

**2. Wait**
Do not interact with the target application during execution.
Wait for the executor to finish.

**3. Read reports**
- `run_report.md` — human-readable summary
- `timeline.md` — execution timeline
- `run_report.json` — structured detail for deep analysis

**4. Analyze failures**
Classify failure type:
- **env**: toolchain not ready or app not started
- **precondition**: test data or state setup failed
- **script**: test script error
- **product**: system behavior does not match expectation
- **unknown**: cannot classify (request more evidence)

For `UNKNOWN` results: suggest what additional evidence is needed. Do NOT treat as PASS.
For product failures: generate preliminary root cause hints.

**5. Generate overlay (if attribution available)**
Write `report_overlay.yaml` then run:
```
openguard apply --merge-overlay <path>
```

**6. Report**
Report: conclusion, Run ID, pass/fail/unknown counts, failure summary, next step.

## Suite mode (--suite <name>)

Run:
```
openguard apply --suite <name> [--gate <gate>]
```
Read `run_report.md` and `timeline.md`.
Report: suite name, script anchor hashes, code version, conclusion.

## Guardrails
- Do not operate the target application directly (REQ-14-07). Execution is handled by the OpenGuard executor, not directly by the AI.
- Low-confidence attribution goes to overlay pending area only — do not modify code or artifacts.
- UNKNOWN must never be reported as PASS.
- `needs-review` scripts cannot run in `release` or `nightly` gates.
"""

SKILL_ARCHIVE = """\
---
name: openguard-archive
description: >
  Use this skill when the user invokes /opg:archive or asks to archive the
  current QA change and promote stable scripts and knowledge.
---

# openguard-archive

## When to use
Trigger when user says `/opg:archive` or asks to close a completed change.

## Steps

**1. Dry-run check**
```
openguard archive [--change <id>] --dry-run
```
Check for:
- Unresolved unknowns (must be resolved first)
- Blocking Review findings (must be fixed or explicitly waived)
- Gate report status
- Execution report completeness

**2. Handle blockers**
List blockers and ask user whether to waive them.
A waiver reason must be recorded — do not skip silently.

**3. Review promotable scripts**
Scripts are promotable if: executed multiple times with pass, no flaky history, has Run ID evidence.
Show suggested suite membership (smoke / regression / requirement / full).
Single-pass scripts must not be promoted.

**4. Get user confirmation**
Wait for user or AI to confirm the promotion list before proceeding.
Do not auto-execute promotion.

**5. Execute archive**
```
openguard archive [--change <id>]
```
This promotes scripts to `test_assets/` (with `.meta.yaml`), updates `suites/`, distills knowledge.

**6. Report**
Report: archive location, promoted scripts with anchor paths, knowledge summary, updated suites, next steps.

## Guardrails
- Do not skip blocking Review or failed gate — require explicit human confirmation (REQ-14-07).
- Do not auto-promote scripts — wait for confirmation. The AI must not directly execute promotion without user approval.
- Single-pass scripts must not be promoted.
- Keep change directory after archive (audit trail).
"""


# ──────────────────────────────────────────────────────────────────────────────
# Index
# ──────────────────────────────────────────────────────────────────────────────

_SKILL_CONTENT_MAP: dict[str, str] = {
    "openguard-run":      SKILL_RUN,
    "openguard-continue": SKILL_CONTINUE,
    "openguard-apply":    SKILL_APPLY,
    "openguard-archive":  SKILL_ARCHIVE,
}

SKILL_NAMES: list[str] = list(_SKILL_CONTENT_MAP.keys())


def get_skill_content(skill_name: str) -> str:
    """Return Markdown content for the given skill."""
    return _SKILL_CONTENT_MAP[skill_name]
