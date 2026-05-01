"""Slash Command Markdown 模板（/oqa:* 命令内容）。

这里集中定义写入各 AI 宿主 commands 目录的 Markdown 文件内容。
slash command 文件告诉 AI Agent 在收到 /oqa:* 指令时应该做什么。

内容结构：
  COMMANDS — list of (cmd_name, description, body_markdown)

渲染逻辑在 init/slash_commands.py 中，根据宿主类型加 front matter。
"""
from __future__ import annotations


# ──────────────────────────────────────────────────────────────────────────────
# 命令内容
# ──────────────────────────────────────────────────────────────────────────────

CMD_RUN_BODY = """\
## /oqa:run

Start a QA test task. After creating the change workspace, the AI enters the
drive loop and autonomously advances all preparation artifacts until ready for
user confirmation.

**Usage:** `/oqa:run <goal description>`

### Execution model: Drive Loop

After `openqa run` completes, read `state.yaml` and act on `agent_action`:

| `agent_action` | Action |
| --- | --- |
| `run_cli` | Call `next_cli`, then loop |
| `generate` | Generate the artifacts listed in `missing`, call `next_cli`, then loop |
| `resolve` | Read `unknowns.md`; answer what you can autonomously; ask user for unknowns you cannot resolve, then loop |
| `wait_user` | **STOP.** Present the summary to the user and wait for confirmation |
| `done` | **STOP.** Report completion to the user |

**Never stop for:** generating a file, calling `openqa _advance`, resolving knowable unknowns.
**Always stop for:** `wait_user`, unknowns requiring domain knowledge, CLI errors.

### Steps

1. If goal is ambiguous, ask the user before proceeding.
2. Run in terminal: `openqa run "<goal>" [--from-openspec <id>] [--test-suite <suite>]`
3. Enter the drive loop above. Keep looping until `agent_action: wait_user`.
4. When `phase: ready_for_apply`, present the `summary` from `state.yaml` to the user:
   - Number of test cases
   - Review issues found
   - Any notes requiring attention
5. Wait for user confirmation. Only after confirmation, suggest `/oqa:apply`.

### When generating test_knowledge.md

Include two machine-readable sections:

**a) YAML front matter:**
```yaml
external_preconditions:
  - some_state   # only if no case in this change produces it; [] otherwise
```

**b) `## Cases` JSON block:**
```json
[
  {"id": "AC-001", "title": "Normal login", "produces_tags": ["logged_in"], "required_precondition_tags": []},
  {"id": "AC-005", "title": "Reconnect", "produces_tags": [], "required_precondition_tags": ["logged_in"]}
]
```

### Strategy parameters
- `--scan-scope auto|full|incremental`
- `--test-suite smoke|incremental|requirement-full|regression|full`
- `--from-openspec <change-id>`
"""

CMD_CONTINUE_BODY = """\
## /oqa:continue

Manual recovery entry point. Use this when the AI drive loop was interrupted,
the conversation was reset, or you want to check current progress.
In normal flow, the drive loop runs automatically after `/oqa:run`.

**Usage:** `/oqa:continue`

### What to do when this command is invoked

1. Read `state.yaml` of the latest change: `agent_action`, `next_cli`, `missing`, `phase`.
2. Report current progress to the user (phase, completed artifacts, missing artifacts).
3. Resume the drive loop from the current state (see `/oqa:run` drive loop table).
   Do not reset any existing progress.
"""

CMD_APPLY_BODY = """\
## /oqa:apply

Execute the prepared test plan. Only invoke after the user has confirmed the
preparation summary from `/oqa:run`.

**Usage:** `/oqa:apply [--suite <name>] [--gate <gate>]`

### What to do when this command is invoked

1. Run in terminal:
   ```
   openqa apply [--change <id>] [--test-suite <suite>] [--gate <gate>] [--review-level <level>]
   ```
   Execution chain: `freshness check → code Review → toolchain ready → app ready → preconditions → test steps → report`

2. Do NOT operate the target application directly. Wait for the executor to finish.

3. Read reports:
   - `run_report.md` — human-readable summary
   - `timeline.md` — execution timeline
   - `run_report.json` — structured detail

4. Classify failures:
   - **env**: toolchain not ready or app not started
   - **precondition**: test data or state setup failed
   - **script**: test script error
   - **product**: system behavior does not match expectation
   - **unknown**: cannot classify (suggest additional evidence)

5. If attribution is available, write `report_overlay.yaml` then run:
   ```
   openqa apply --merge-overlay <path>
   ```

6. Report: conclusion, Run ID, pass/fail counts, failure summary, next step.

### Suite mode
```
openqa apply --suite <name> [--gate <gate>]
```
"""

CMD_ARCHIVE_BODY = """\
## /oqa:archive

Archive the completed change and promote stable knowledge and test scripts.

**Usage:** `/oqa:archive`

### What to do when this command is invoked

1. Run dry-run check:
   ```
   openqa archive [--change <id>] --dry-run
   ```

2. Check for blockers:
   - Unresolved unknowns
   - Blocking Review findings
   - Failed gate report
   - Incomplete execution report

3. If blockers exist, list them and ask the user whether to waive each.
   Record waiver reason — do not skip silently.

4. Show promotable test scripts (passed multiple times, no flaky history, has Run ID).
   Suggest suite membership for each.

5. Wait for user confirmation, then run:
   ```
   openqa archive [--change <id>]
   ```

6. Report: archive location, promoted scripts with anchor paths, knowledge summary, updated suites.
"""


# ──────────────────────────────────────────────────────────────────────────────
# 命令列表（供 init/slash_commands.py 消费）
# ──────────────────────────────────────────────────────────────────────────────

# 格式：(cmd_name, description, body_markdown)
COMMANDS: list[tuple[str, str, str]] = [
    (
        "oqa:run",
        "Start a QA test task; AI drives preparation autonomously until user confirmation.",
        CMD_RUN_BODY,
    ),
    (
        "oqa:continue",
        "Manual recovery: resume the drive loop from current state after interruption.",
        CMD_CONTINUE_BODY,
    ),
    (
        "oqa:apply",
        "Run code Review and test matrix; collect evidence; generate reports.",
        CMD_APPLY_BODY,
    ),
    (
        "oqa:archive",
        "Close and archive a finished change; promote stable knowledge and test scripts.",
        CMD_ARCHIVE_BODY,
    ),
]
