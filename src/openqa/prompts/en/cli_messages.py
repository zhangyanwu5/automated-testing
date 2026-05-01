"""CLI messages — English."""
from __future__ import annotations

WELCOME = """\
Welcome to OpenQA
A lightweight QA automation framework for AI agents

This setup will configure:
  • openqa/ project workspace
  • Project test profile and OpenQA config
  • OpenQA ignore rules
  • /oqa:* slash commands for AI tools
  • openqa-* skills for AI agent operation
"""

QUICK_START = """\
Quick start:
  /oqa:run     Start a test task (AI prepares autonomously, stops for your confirmation)
  /oqa:apply   Execute after confirmation
  /oqa:archive Close and learn
"""

HELP_USAGE = """\
OpenQA – A lightweight QA automation framework for AI coding agents

Usage:
  openqa <command> [options]

Commands:
  init        Initialize openqa/ workspace in the current project.
  update      Refresh /oqa:* slash commands, schemas and templates.
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
  /oqa:new <goal>   →  openqa new
  /oqa:continue     →  openqa continue
  /oqa:apply        →  openqa apply
  /oqa:archive      →  openqa archive

Run `openqa <command> --help` for command-specific options.
"""

ALREADY_INIT_MSG = (
    "OpenQA already initialized at {openqa_dir}.\n"
    "Use `openqa init --reconfigure` to update the project profile,\n"
    "or `openqa update` to refresh /oqa:* commands and templates."
)

REQUIRED_INPUT_HEADER = "Required input before real execution:"

SCANNING_PROJECT        = "Scanning project…"
SCANNING_DETECTED       = "Scanning project — detected {type}"
DETECTED_PROJECT        = "Detected {type} project:"
NO_DETECT_PROJECT       = "Could not detect project type:"
RECOMMENDED             = "Recommended decisions:"
SELECT_AI_TOOLS         = "? Select AI coding tools to install skills into (multi-select):"

CREATED_WORKSPACE       = "Created openqa/ workspace at {path}"
WRITING_CONFIG          = "Writing openqa/config.yaml"
WRITTEN_FILE            = "Written {path}"
INSTALLING_COMMANDS     = "Installing /oqa:* commands"
INSTALLED_COMMANDS      = "Installed /oqa:* commands for {hosts} ({total} files)"
NO_HOST_SKIP_COMMANDS   = "No AI host selected, skipping /oqa:* command installation."
NO_HOST_RUN_UPDATE      = "Run `openqa update` after configuring an AI host."
INSTALLING_SKILLS       = "Installing openqa-* skills"
INSTALLED_SKILLS        = "Installed openqa-* skills for {hosts} ({total} files)"
INSTALLED_SKILLS_FALLBACK = "Installed openqa-* skills (fallback: openqa/commands/)"

UNITY_EDITOR_DETECTED  = "  Detected Unity Editor ({source}):"
USE_EDITOR_PROMPT      = "  Use this editor? [Y/n]: "
ENTER_EDITOR_PATH      = "  Enter Unity editor path: "
AUTO_SELECT_EDITOR     = "  Auto-selected Unity Editor (--yes): {path}"
SELECT_UNITY_EDITOR    = "? Select Unity Editor to use:"
SKIPPED_FILL_LATER     = "  ? {item}: (skipped — fill in openqa/config.yaml later)"
SKIPPED_FILL_LATER_INLINE = "    (skipped — fill in openqa/config.yaml later)"
INIT_COMPLETE          = "OpenQA initialization complete."
