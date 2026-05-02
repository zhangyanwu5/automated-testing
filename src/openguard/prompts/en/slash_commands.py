"""Slash Command Markdown 模板（/opg:* 命令内容）。

这里集中定义写入各 AI 宿主 commands 目录的 Markdown 文件内容。
slash command 文件告诉 AI Agent 在收到 /opg:* 指令时应该做什么。

内容结构：
  COMMANDS — list of (cmd_name, description, body_markdown)

渲染逻辑在 init/slash_commands.py 中，根据宿主类型加 front matter。
"""
from __future__ import annotations


# ──────────────────────────────────────────────────────────────────────────────
# 命令内容
# ──────────────────────────────────────────────────────────────────────────────

CMD_RUN_BODY = """\
## /opg:run

Start a QA test task. After creating the change workspace, the AI enters the
drive loop and autonomously advances all preparation artifacts until ready for
user confirmation.

**Usage:** `/opg:run <goal description>`

### Execution model: Drive Loop

After `openguard run` completes, read `state.yaml` and act on `agent_action`:

| `agent_action` | Action |
| --- | --- |
| `run_cli` | Call `next_cli`, then loop |
| `generate` | Generate the artifacts listed in `missing`, call `next_cli`, then loop |
| `resolve` | Read `unknowns.md`; answer what you can autonomously; ask user for unknowns you cannot resolve, then loop |
| `wait_user` | **STOP.** Present the summary to the user and wait for confirmation |
| `done` | **STOP.** Report completion to the user |

**Never stop for:** generating a file, calling `openguard _advance`, resolving knowable unknowns.
**Always stop for:** `wait_user`, unknowns requiring domain knowledge, CLI errors.

### Steps

1. If goal is ambiguous, ask the user before proceeding.
2. Run in terminal: `openguard run "<goal>" [--from-openspec <id>] [--test-suite <suite>]`
3. Enter the drive loop above. Keep looping until `agent_action: wait_user`.
4. When `phase: ready_for_apply`, present the `summary` from `state.yaml` to the user:
   - Number of test cases
   - Review issues found
   - Any notes requiring attention
5. Wait for user confirmation. Only after confirmation, suggest `/opg:apply`.

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
## /opg:continue

Manual recovery entry point. Use this when the AI drive loop was interrupted,
the conversation was reset, or you want to check current progress.
In normal flow, the drive loop runs automatically after `/opg:run`.

**Usage:** `/opg:continue`

### What to do when this command is invoked

1. Read `state.yaml` of the latest change: `agent_action`, `next_cli`, `missing`, `phase`.
2. Report current progress to the user (phase, completed artifacts, missing artifacts).
3. Resume the drive loop from the current state (see `/opg:run` drive loop table).
   Do not reset any existing progress.
"""

CMD_APPLY_BODY = """\
## /opg:apply

Execute the prepared test plan. Only invoke after the user has confirmed the
preparation summary from `/opg:run`.

**Usage:** `/opg:apply [--suite <name>] [--gate <gate>]`

### Script location policy

All test scripts must live inside `openguard/`:
- Draft scripts: `openguard/changes/<change-id>/test_scripts/`
- Promoted stable scripts: `openguard/test_assets/scripts/`

Never write test scripts into the project's source directories.

### What to do when this command is invoked

1. Run in terminal:
   ```
   openguard apply [--change <id>] [--test-suite <suite>] [--gate <gate>] [--review-level <level>]
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
   - **script**: test script error (path: `openguard/changes/<id>/test_scripts/`)
   - **product**: system behavior does not match expectation
   - **unknown**: cannot classify (suggest additional evidence)

5. If attribution is available, write `report_overlay.yaml` then run:
   ```
   openguard apply --merge-overlay <path>
   ```

6. Report: conclusion, Run ID, pass/fail counts, failure summary, next step.

### Suite mode
```
openguard apply --suite <name> [--gate <gate>]
```
"""

CMD_ARCHIVE_BODY = """\
## /opg:archive

Archive the completed change and promote stable knowledge and test scripts.

**Usage:** `/opg:archive`

### What to do when this command is invoked

1. Run dry-run check:
   ```
   openguard archive [--change <id>] --dry-run
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
   openguard archive [--change <id>]
   ```

6. Report: archive location, promoted scripts with anchor paths, knowledge summary, updated suites.
"""


CMD_REPORT_BODY = """\
## /opg:report

Generate a diagnostic report file for issue investigation and developer support.
Use this when the user encounters unexpected behavior, errors, or bugs.

**Usage:** `/opg:report`

### What to do when this command is invoked

1. Run in terminal:
   ```
   openguard report
   ```
   This packages all diagnostic information into a single file:
   - Recent CLI call history (last 50 commands with output)
   - Current change state and `_advance` decision trace
   - Most recent run report and event stream
   - Failed test script output
   - operation_log

2. Read the output line to get the file path, e.g.:
   ```
   上报文件已生成：/your/project/openguard-report-20260502-221800.txt
   ```

3. Tell the user:
   - The report file has been generated at `<path>`
   - All sensitive information (tokens/passwords) has been automatically redacted
   - Please send this file to the developer for analysis

### Options

If the user wants to specify a particular change:
```
openguard report --change <change-id>
```

If the user wants to save the file to a specific location:
```
openguard report --out /path/to/report.txt
```
"""


# ──────────────────────────────────────────────────────────────────────────────
# 命令列表（供 init/slash_commands.py 消费）
# ──────────────────────────────────────────────────────────────────────────────

# 格式：(cmd_name, description, body_markdown)
COMMANDS: list[tuple[str, str, str]] = [
    (
        "opg:run",
        "Start a QA test task; AI drives preparation autonomously until user confirmation.",
        CMD_RUN_BODY,
    ),
    (
        "opg:continue",
        "Manual recovery: resume the drive loop from current state after interruption.",
        CMD_CONTINUE_BODY,
    ),
    (
        "opg:apply",
        "Run code Review and test matrix; collect evidence; generate reports.",
        CMD_APPLY_BODY,
    ),
    (
        "opg:archive",
        "Close and archive a finished change; promote stable knowledge and test scripts.",
        CMD_ARCHIVE_BODY,
    ),
    (
        "opg:report",
        "Generate a diagnostic report file for issue investigation; send to developer for support.",
        CMD_REPORT_BODY,
    ),
]
