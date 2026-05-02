"""CLI messages — English."""
from __future__ import annotations

WELCOME = """\
Welcome to OpenGuard
A lightweight QA automation framework for AI agents

This setup will configure:
  • openguard/ project workspace
  • Project test profile and OpenGuard config
  • OpenGuard ignore rules
  • /opg:* slash commands for AI tools
  • openguard-* skills for AI agent operation
"""

QUICK_START = """\
Quick start:
  /opg:run     Start a test task (AI prepares autonomously, stops for your confirmation)
  /opg:apply   Execute after confirmation
  /opg:archive Close and learn
"""

HELP_USAGE = """\
OpenGuard – A lightweight QA automation framework for AI coding agents

Usage:
  openguard <command> [options]

Commands:
  init        Initialize openguard/ workspace in the current project.
  update      Refresh /opg:* slash commands, schemas and templates.
  new <goal>  Start a new QA change (feature, code change or bug fix).
  continue    Advance the current change to the next missing artifact.
  apply       Run code Review and test matrix, collect evidence, generate report.
  archive     Archive a completed change, promote stable knowledge.
  help        Show this help.

Strategy options:
  --scan-scope   auto | full | incremental   (default: auto)
  --test-suite   smoke | incremental | requirement-full | regression | full
  --review-level off | changed | risk-based | full
  --gate         local | ci | release

Slash Commands (installed by init / update):
  /opg:new <goal>   →  openguard new
  /opg:continue     →  openguard continue
  /opg:apply        →  openguard apply
  /opg:archive      →  openguard archive

Run `openguard <command> --help` for command-specific options.
"""

ALREADY_INIT_MSG = (
    "OpenGuard already initialized at {openguard_dir}.\n"
    "Use `openguard init --reconfigure` to update the project profile,\n"
    "or `openguard update` to refresh /opg:* commands and templates."
)

REQUIRED_INPUT_HEADER = "Required input before real execution:"

SCANNING_PROJECT        = "Scanning project…"
SCANNING_DETECTED       = "Scanning project — detected {type}"
DETECTED_PROJECT        = "Detected {type} project:"
NO_DETECT_PROJECT       = "Could not detect project type:"
RECOMMENDED             = "Recommended decisions:"
SELECT_AI_TOOLS         = "? Select AI coding tools to install skills into (multi-select):"

CREATED_WORKSPACE       = "Created openguard/ workspace at {path}"
WRITING_CONFIG          = "Writing openguard/config.yaml"
WRITTEN_FILE            = "Written {path}"
INSTALLING_COMMANDS     = "Installing /opg:* commands"
INSTALLED_COMMANDS      = "Installed /opg:* commands for {hosts} ({total} files)"
NO_HOST_SKIP_COMMANDS   = "No AI host selected, skipping /opg:* command installation."
NO_HOST_RUN_UPDATE      = "Run `openguard update` after configuring an AI host."
INSTALLING_SKILLS       = "Installing openguard-* skills"
INSTALLED_SKILLS        = "Installed openguard-* skills for {hosts} ({total} files)"
INSTALLED_SKILLS_FALLBACK = "Installed openguard-* skills (fallback: openguard/commands/)"

UNITY_EDITOR_DETECTED  = "  Detected Unity Editor ({source}):"
USE_EDITOR_PROMPT      = "  Use this editor? [Y/n]: "
ENTER_EDITOR_PATH      = "  Enter Unity editor path: "
AUTO_SELECT_EDITOR     = "  Auto-selected Unity Editor (--yes): {path}"
SELECT_UNITY_EDITOR    = "? Select Unity Editor to use:"
SKIPPED_FILL_LATER     = "  ? {item}: (skipped — fill in openguard/config.yaml later)"
SKIPPED_FILL_LATER_INLINE = "    (skipped — fill in openguard/config.yaml later)"
INIT_COMPLETE          = "OpenGuard initialization complete."
