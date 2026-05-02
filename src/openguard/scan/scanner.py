"""扫描核心：文件哈希采集、需求指纹、忽略规则、snapshot/delta/full_index 生成。

设计原则（REQ-04）：
- 纯确定性逻辑，不调用大模型。
- 产物落盘为 JSON，可被 impact.py、freshness.py 和矩阵生成器消费。
- 同一输入扫描结果可复现（REQ-04 验收标准）。
- 遵循 openguard/ignore（REQ-04-07）。
- 受 project.type 影响选择扫描入口（REQ-04-08）。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from openguard.utils import now_iso as _now_iso
from openguard.tools.fs.hash import file_hash as _file_hash
from openguard.tools.fs.ignore import load_ignore as _load_ignore_tool, is_ignored as _is_ignored_tool
from openguard.tools.analysis.symbols import detect_language as _detect_language, extract_symbols as _extract_symbols

# 扫描器版本：升级时应同步更新，触发新鲜度失效（REQ-04-06）
ANALYZER_VERSION = "openguard-scanner/0.1.0"


# ──────────────────────────────────────────────────────────────────────────────
# 忽略规则（REQ-04-07）
# ──────────────────────────────────────────────────────────────────────────────

def load_ignore_patterns(openguard_dir: Path) -> list[str]:
    """从 openguard/ignore 加载忽略 glob 模式列表（委托给 tools）。"""
    return _load_ignore_tool(openguard_dir)


def _is_ignored(path: Path, root: Path, patterns: list[str]) -> bool:
    """判断 path 是否匹配任意忽略模式（委托给 tools）。"""
    return _is_ignored_tool(path, root, patterns)


# ──────────────────────────────────────────────────────────────────────────────
# 需求指纹（REQ-04-02）
# ──────────────────────────────────────────────────────────────────────────────

def _requirements_fingerprint(change_dir: Path) -> dict[str, Any]:
    """提取 requirements.md 中每条 EARS 需求的 ID 和指纹。"""
    req_path = change_dir / "requirements.md"
    if not req_path.exists():
        return {"status": "missing", "items": []}

    content = req_path.read_text(encoding="utf-8")
    file_hash = _file_hash(req_path)

    # 提取所有含 ID 的表格行（格式：| ID | EARS 句 | ... |）
    items: list[dict[str, str]] = []
    for line in content.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        id_cell = cells[0]
        ears_cell = cells[1] if len(cells) > 1 else ""
        # 识别含需求 ID 的行（形如 chg-xxx-AC-001 或 REQ-xxx）
        if re.match(r"[\w]+-\w+-\w+", id_cell) and "---" not in id_cell:
            item_hash = hashlib.sha256(ears_cell.encode()).hexdigest()[:16]
            items.append({"id": id_cell, "text_hash": item_hash})

    return {
        "status": "ok",
        "file_hash": file_hash,
        "item_count": len(items),
        "items": items,
    }


# ──────────────────────────────────────────────────────────────────────────────
# test_assets 锚点检查（REQ-04-11）
# ──────────────────────────────────────────────────────────────────────────────

def _check_test_asset_anchors(
    openguard_dir: Path,
    file_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """检查 test_assets/ 中所有脚本的 .meta.yaml 锚点哈希。

    对比当前代码快照：
    - 绑定符号哈希变化 → needs-review
    - 绑定符号文件消失 → stale
    规则参考 REQ-04-11 / REQ-09-10。
    """
    scripts_dir = openguard_dir / "test_assets" / "scripts"
    if not scripts_dir.is_dir():
        return []

    # 建立文件路径 → 哈希快速索引
    file_hash_index: dict[str, str] = {
        r["path"]: r["hash"] for r in file_records
    }

    results: list[dict[str, Any]] = []
    for meta_file in sorted(scripts_dir.glob("**/*.meta.yaml")):
        try:
            with meta_file.open(encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}
        except Exception:
            continue

        script_path = meta.get("script_path", "")
        anchor_hash = meta.get("anchor_hash", "")
        current_status = meta.get("status", "verified")

        # 查找绑定文件当前哈希
        current_hash = file_hash_index.get(script_path)
        new_status = current_status

        if current_hash is None:
            new_status = "stale"      # 绑定文件已消失
        elif current_hash != anchor_hash and anchor_hash:
            new_status = "needs-review"  # 哈希变化

        results.append({
            "meta_file": str(meta_file.relative_to(openguard_dir)),
            "script_path": script_path,
            "anchor_hash": anchor_hash,
            "current_hash": current_hash,
            "previous_status": current_status,
            "new_status": new_status,
            "changed": new_status != current_status,
        })

        # 若状态发生变化，回写 meta.yaml
        if new_status != current_status:
            meta["status"] = new_status
            meta["last_checked_at"] = _now_iso()
            meta_file.write_text(
                yaml.dump(meta, default_flow_style=False, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )

    return results


# ──────────────────────────────────────────────────────────────────────────────
# 全量扫描（REQ-04-01 / REQ-04-08）
# ──────────────────────────────────────────────────────────────────────────────

def _get_scan_include_exclude(
    config: dict[str, Any],
    project_root: Path,
) -> tuple[list[Path], list[str]]:
    """根据 config.yaml 中的 scan 配置确定扫描目录和忽略模式。"""
    scan_cfg = config.get("scan", {})
    include_dirs: list[Path] = []
    for inc in scan_cfg.get("include", ["."]):
        d = project_root / inc.rstrip("/")
        if d.exists():
            include_dirs.append(d)
    if not include_dirs:
        include_dirs = [project_root]

    exclude_patterns: list[str] = scan_cfg.get("exclude", [])
    return include_dirs, exclude_patterns


def _collect_files(
    include_dirs: list[Path],
    project_root: Path,
    ignore_patterns: list[str],
) -> list[dict[str, Any]]:
    """遍历扫描目录，采集文件记录（REQ-04-01）。"""
    records: list[dict[str, Any]] = []
    seen: set[str] = set()

    for scan_dir in include_dirs:
        for path in sorted(scan_dir.rglob("*")):
            if not path.is_file():
                continue
            if _is_ignored(path, project_root, ignore_patterns):
                continue
            rel = str(path.relative_to(project_root)).replace("\\", "/")
            if rel in seen:
                continue
            seen.add(rel)

            lang = _detect_language(path)
            symbols = _extract_symbols(path, lang)
            records.append({
                "path": rel,
                "hash": _file_hash(path),
                "language": lang,
                "symbols": symbols,
                "size_bytes": path.stat().st_size,
            })

    return records


def run_full_scan(
    project_root: Path,
    openguard_dir: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    """执行全量扫描，返回 snapshot 数据（REQ-04-01 / REQ-04-08 / REQ-04-09）。"""
    ignore_patterns = load_ignore_patterns(openguard_dir)
    include_dirs, extra_excludes = _get_scan_include_exclude(config, project_root)
    ignore_patterns = ignore_patterns + [p for p in extra_excludes if p not in ignore_patterns]

    file_records = _collect_files(include_dirs, project_root, ignore_patterns)
    anchor_checks = _check_test_asset_anchors(openguard_dir, file_records)

    project_type = config.get("project", {}).get("type", "unknown")
    scan_hints = _scan_hints_for_type(project_type, file_records)

    return {
        "analyzer_version": ANALYZER_VERSION,
        "project_type": project_type,
        "file_count": len(file_records),
        "files": file_records,
        "scan_hints": scan_hints,
        "test_asset_anchor_checks": anchor_checks,
        "scanned_at": _now_iso(),
    }


def _scan_hints_for_type(
    project_type: str,
    file_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """根据 project.type 提取扫描 hints（REQ-04-08）。"""
    hints: dict[str, Any] = {"project_type": project_type}

    paths = [r["path"] for r in file_records]

    if project_type == "unity":
        hints["scenes"] = [p for p in paths if p.endswith(".unity")][:20]
        hints["test_scripts"] = [p for p in paths if "test" in p.lower() and p.endswith(".cs")][:20]
        hints["entry_points"] = hints["scenes"]

    elif project_type == "unreal":
        hints["maps"] = [p for p in paths if p.endswith(".umap")][:20]
        hints["automation_specs"] = [p for p in paths if "spec" in p.lower() and p.endswith(".cpp")][:10]
        hints["entry_points"] = hints["maps"]

    elif project_type in ("web", "h5"):
        hints["routes"] = [p for p in paths if any(x in p for x in ("router", "routes", "pages"))][:20]
        hints["components"] = [p for p in paths if "component" in p.lower()][:20]
        hints["entry_points"] = [p for p in paths if p.endswith(("index.ts", "index.tsx", "index.js", "main.ts"))][:5]

    elif project_type in ("webgl", "web-game"):
        hints["wasm_files"] = [p for p in paths if p.endswith(".wasm")][:5]
        hints["entry_pages"] = [p for p in paths if p.endswith("index.html")][:5]
        hints["js_bridges"] = [p for p in paths if "bridge" in p.lower() or "ws" in p.lower()][:10]

    elif project_type in ("backend", "api"):
        hints["api_definitions"] = [p for p in paths if any(x in p for x in ("openapi", "swagger", ".proto"))][:10]
        hints["service_entries"] = [p for p in paths if any(x in p for x in ("main.", "app.", "server."))][:5]

    return hints


# ──────────────────────────────────────────────────────────────────────────────
# 增量扫描（REQ-04-03）
# ──────────────────────────────────────────────────────────────────────────────

def run_incremental_scan(
    project_root: Path,
    openguard_dir: Path,
    config: dict[str, Any],
    previous_snapshot: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """执行增量扫描，返回 (新 snapshot 数据, delta 数据)。"""
    current = run_full_scan(project_root, openguard_dir, config)

    if not previous_snapshot or previous_snapshot.get("status") != "complete":
        # 无可信基线，退化为全量
        delta = _empty_delta()
        delta["note"] = "无有效基线快照，delta 为空（视为首次全量扫描）"
        return current, delta

    prev_files: dict[str, str] = {
        r["path"]: r["hash"]
        for r in previous_snapshot.get("files", [])
    }
    curr_files: dict[str, str] = {
        r["path"]: r["hash"]
        for r in current.get("files", [])
    }

    added = [p for p in curr_files if p not in prev_files]
    deleted = [p for p in prev_files if p not in curr_files]
    modified = [
        p for p in curr_files
        if p in prev_files and curr_files[p] != prev_files[p]
    ]

    delta: dict[str, Any] = {
        "schema_version": "openguard/delta/v1",
        "analyzer_version": ANALYZER_VERSION,
        "scanned_at": _now_iso(),
        "added": added,
        "modified": modified,
        "deleted": deleted,
        "renamed": [],   # 简单实现：不做重命名检测
        "change_summary": {
            "added_count": len(added),
            "modified_count": len(modified),
            "deleted_count": len(deleted),
        },
        "status": "complete",
    }
    return current, delta


def _empty_delta() -> dict[str, Any]:
    return {
        "schema_version": "openguard/delta/v1",
        "analyzer_version": ANALYZER_VERSION,
        "scanned_at": _now_iso(),
        "added": [], "modified": [], "deleted": [], "renamed": [],
        "change_summary": {"added_count": 0, "modified_count": 0, "deleted_count": 0},
        "status": "complete",
    }


# ──────────────────────────────────────────────────────────────────────────────
# 产物写入
# ──────────────────────────────────────────────────────────────────────────────

def write_snapshot(
    change_dir: Path,
    scan_data: dict[str, Any],
    requirements_fp: dict[str, Any],
    change_id: str,
    scan_scope: str,
    project_root: Path,
) -> Path:
    """将扫描数据写入 snapshot.json，并更新 requirements 指纹。"""
    snapshot: dict[str, Any] = {
        "schema_version": "openguard/snapshot/v1",
        "change_id": change_id,
        "created_at": scan_data.get("scanned_at", _now_iso()),
        "scan_scope": scan_scope,
        "status": "complete",
        "analyzer_version": scan_data.get("analyzer_version", ANALYZER_VERSION),
        "project_root": str(project_root),
        "project_type": scan_data.get("project_type", "unknown"),
        "requirements": requirements_fp,
        "code_files": scan_data.get("files", []),
        "scan_hints": scan_data.get("scan_hints", {}),
        "test_assets": scan_data.get("test_asset_anchor_checks", []),
        "file_count": scan_data.get("file_count", 0),
    }
    path = change_dir / "snapshot.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_delta(change_dir: Path, delta: dict[str, Any]) -> Path:
    """写入 delta.json。"""
    path = change_dir / "delta.json"
    path.write_text(json.dumps(delta, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_full_index(openguard_dir: Path, scan_data: dict[str, Any]) -> Path:
    """写入全量扫描索引 full_index.json（REQ-04 全量扫描产物）。"""
    full_index: dict[str, Any] = {
        "schema_version": "openguard/full_index/v1",
        "created_at": scan_data.get("scanned_at", _now_iso()),
        "analyzer_version": scan_data.get("analyzer_version", ANALYZER_VERSION),
        "project_type": scan_data.get("project_type"),
        "file_count": scan_data.get("file_count", 0),
        "files": scan_data.get("files", []),
        "scan_hints": scan_data.get("scan_hints", {}),
    }
    path = openguard_dir / "artifacts" / "full_index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(full_index, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ──────────────────────────────────────────────────────────────────────────────
# 主入口：按策略执行扫描
# ──────────────────────────────────────────────────────────────────────────────

def execute_scan(
    change_dir: Path,
    openguard_dir: Path,
    config: dict[str, Any],
    scan_scope: str = "auto",
) -> tuple[Path, Path | None]:
    """按策略执行扫描，写入 snapshot.json / delta.json，返回 (snapshot_path, delta_path)。

    auto 策略：
    - change_dir/snapshot.json 不存在或 status!=complete → 全量
    - 存在可信基线 → 增量
    """
    project_root = openguard_dir.parent
    change_id = change_dir.name
    requirements_fp = _requirements_fingerprint(change_dir)

    # 确定实际扫描模式
    existing_snapshot: dict[str, Any] | None = None
    existing_path = change_dir / "snapshot.json"
    if existing_path.exists():
        try:
            existing_snapshot = json.loads(existing_path.read_text(encoding="utf-8"))
        except Exception:
            existing_snapshot = None

    use_full = (
        scan_scope == "full"
        or existing_snapshot is None
        or existing_snapshot.get("status") != "complete"
    )
    if scan_scope == "incremental":
        use_full = False

    if use_full:
        scan_data = run_full_scan(project_root, openguard_dir, config)
        snapshot_path = write_snapshot(
            change_dir, scan_data, requirements_fp, change_id, "full", project_root
        )
        write_full_index(openguard_dir, scan_data)
        return snapshot_path, None
    else:
        scan_data, delta = run_incremental_scan(
            project_root, openguard_dir, config, existing_snapshot
        )
        snapshot_path = write_snapshot(
            change_dir, scan_data, requirements_fp, change_id, "incremental", project_root
        )
        delta["change_id"] = change_id
        delta_path = write_delta(change_dir, delta)
        return snapshot_path, delta_path


# ──────────────────────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
# init-probe：轻量探测（REQ-04-09）
# ──────────────────────────────────────────────────────────────────────────────

def run_init_probe(
    project_root: Path,
    openguard_dir: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    """执行轻量 init-probe，识别项目结构和控制通道类型（REQ-04-09）。

    不做全量接口深度扫描；只识别主要子系统和控制通道入口。
    结果写入 knowledge/project_profile.yaml 初稿。
    """
    project_type = config.get("project", {}).get("type", "unknown")
    ignore_patterns = load_ignore_patterns(openguard_dir)

    # 轻量扫描：只收集顶层目录和关键标志文件
    structure: dict[str, Any] = {
        "top_dirs": [],
        "control_channel_hints": [],
        "subsystems": [],
    }

    # 扫描顶层目录（深度限制 2）
    for p in project_root.iterdir():
        if p.is_dir() and not _is_ignored(p, project_root, ignore_patterns):
            structure["top_dirs"].append(p.name)

    # 控制通道类型探测
    control_hints = _probe_control_channels(project_root, project_type)
    structure["control_channel_hints"] = control_hints

    # 主要子系统探测
    structure["subsystems"] = _probe_subsystems(project_root, project_type)

    probe_result: dict[str, Any] = {
        "schema_version": "openguard/init_probe/v1",
        "probed_at": _now_iso(),
        "project_type": project_type,
        "structure": structure,
        "note": "init-probe 轻量结果，不含接口深度分析。接口知识由 knowledge-scan 按需建立（REQ-04-09）。",
    }
    return probe_result


def _probe_control_channels(project_root: Path, project_type: str) -> list[str]:
    """探测控制通道类型入口（轻量，不深度解析）。"""
    hints: list[str] = []
    check_patterns: dict[str, list[str]] = {
        "unity": ["**/bridge*", "**/TestBridge*", "**/RpcBridge*", "**/*WebSocket*"],
        "unreal": ["**/TestCommandlet*", "**/*RPC*", "**/*WebSocket*"],
        "web": ["**/playwright.config*", "**/cypress.config*"],
        "webgl": ["**/bridge.js", "**/*ws.js", "**/control.js"],
        "backend": ["**/*.proto", "**/openapi*", "**/swagger*"],
        "api": ["**/*.proto", "**/openapi*"],
    }
    patterns = check_patterns.get(project_type, [])
    for pat in patterns:
        matches = list(project_root.glob(pat))[:3]
        if matches:
            hints.append(f"{pat}: {[str(m.relative_to(project_root)) for m in matches[:2]]}")
    return hints


def _probe_subsystems(project_root: Path, project_type: str) -> list[str]:
    """识别主要子系统目录（轻量）。"""
    subsystems: list[str] = []
    common_subsystem_dirs = {
        "unity": ["Assets/Scripts", "Assets/GamePlay", "Assets/UI", "Assets/Network"],
        "unreal": ["Source", "Content/Blueprints", "Config"],
        "web": ["src", "app", "pages", "components", "api"],
        "backend": ["src", "app", "services", "controllers", "api"],
    }
    dirs = common_subsystem_dirs.get(project_type, ["src", "lib", "app"])
    for d in dirs:
        candidate = project_root / d
        if candidate.is_dir():
            subsystems.append(d)
    return subsystems


# ──────────────────────────────────────────────────────────────────────────────
# knowledge-scan：按需深度扫描（REQ-04-10 / REQ-03-09）
# ──────────────────────────────────────────────────────────────────────────────

def run_knowledge_scan(
    project_root: Path,
    openguard_dir: Path,
    config: dict[str, Any],
    target_description: str = "",
) -> dict[str, Any]:
    """执行 knowledge-scan，提取游戏接口知识（REQ-04-10 / REQ-03-09）。

    提取目标：
    - 事件系统（EventBus / 注册表）→ event_catalog.yaml
    - RPC/网络协议 → protocol_catalog.yaml
    - 控制台命令 → control_channels.yaml
    - 核心状态字段 → state_schema.yaml
    - 日志关键模式 → log_patterns.yaml

    每个条目绑定代码锚点（file_path + symbol + hash）（REQ-04-11）。
    若知识库已有新鲜条目，跳过扫描直接复用（REQ-03-09）。
    """
    project_type = config.get("project", {}).get("type", "unknown")
    ignore_patterns = load_ignore_patterns(openguard_dir)
    knowledge_dir = openguard_dir / "knowledge"

    extracted: dict[str, list[dict[str, Any]]] = {
        "event_catalog": [],
        "protocol_catalog": [],
        "state_schema": [],
        "log_patterns": [],
        "control_channels_update": [],
    }

    # 扫描代码文件，提取接口知识
    include_paths, _ = _scan_paths_for_type_local(config)
    for include_path in include_paths:
        scan_root = project_root / include_path
        if not scan_root.exists():
            continue
        for code_file in scan_root.rglob("*"):
            if not code_file.is_file():
                continue
            if _is_ignored(code_file, project_root, ignore_patterns):
                continue
            suffix = code_file.suffix.lower()
            if suffix not in (".cs", ".cpp", ".py", ".ts", ".js", ".proto", ".go", ".java"):
                continue
            _extract_interface_knowledge(
                code_file, project_root, project_type, extracted
            )

    # 将提取结果写入知识库（REQ-04-10）
    from openguard.knowledge.manager import add_interface_knowledge_item, INTERFACE_KNOWLEDGE_FILES
    catalog_map = {
        "event_catalog": "event_catalog.yaml",
        "protocol_catalog": "protocol_catalog.yaml",
        "state_schema": "state_schema.yaml",
        "log_patterns": "log_patterns.yaml",
    }
    written_counts: dict[str, int] = {}
    for catalog_key, catalog_file in catalog_map.items():
        items = extracted.get(catalog_key, [])
        count = 0
        for item in items:
            if add_interface_knowledge_item(knowledge_dir, catalog_file, item):
                count += 1
        written_counts[catalog_key] = count

    result: dict[str, Any] = {
        "schema_version": "openguard/knowledge_scan/v1",
        "scanned_at": _now_iso(),
        "project_type": project_type,
        "target": target_description,
        "extracted_counts": written_counts,
        "note": "接口知识条目初始状态为 inferred，需经执行验证后升为 verified（REQ-09-15）。",
    }
    return result


def _scan_paths_for_type_local(config: dict[str, Any]) -> tuple[list[str], list[str]]:
    """从 config 提取扫描 include/exclude 路径（scanner 内部用）。"""
    scan_cfg = config.get("scan", {})
    include = scan_cfg.get("include", ["."])
    exclude = scan_cfg.get("exclude", [])
    if isinstance(include, str):
        include = [include]
    if isinstance(exclude, str):
        exclude = [exclude]
    return include, exclude


def _extract_interface_knowledge(
    code_file: Path,
    project_root: Path,
    project_type: str,
    extracted: dict[str, list[dict[str, Any]]],
) -> None:
    """从单个代码文件提取接口知识条目（轻量静态分析）。

    这是一个骨架实现，提取规则按项目类型扩展。
    真正的深度分析由 Agent 宿主负责；这里只做确定性的模式匹配。
    """
    try:
        content = code_file.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return

    rel_path = str(code_file.relative_to(project_root)).replace("\\", "/")
    file_hash = _file_hash(code_file)
    now = _now_iso()

    # 事件系统：查找事件注册模式
    if project_type == "unity":
        _extract_unity_events(content, rel_path, file_hash, now, extracted)
        _extract_unity_rpc(content, rel_path, file_hash, now, extracted)

    elif project_type == "unreal":
        _extract_unreal_events(content, rel_path, file_hash, now, extracted)

    elif project_type in ("backend", "api"):
        # proto 文件
        if code_file.suffix == ".proto":
            _extract_proto_rpc(content, rel_path, file_hash, now, extracted)

    # 日志模式（通用）
    _extract_log_patterns(content, rel_path, file_hash, now, extracted)


def _extract_unity_events(
    content: str, rel_path: str, file_hash: str, now: str,
    extracted: dict[str, list],
) -> None:
    """提取 Unity C# 事件注册模式（轻量）。"""
    # 简单模式：EventBus.Subscribe<EventName> 或 AddListener
    for m in re.finditer(r'(?:Subscribe|AddListener|Register)\s*[<(]\s*(\w+)', content):
        event_name = m.group(1)
        if len(event_name) > 3:  # 过滤过短的名称
            extracted["event_catalog"].append({
                "id": f"evt-{event_name.lower()[:32]}",
                "name": event_name,
                "type": "event",
                "source": "code_scan",
                "evidence": [rel_path],
                "confidence": "medium",
                "status": "inferred",
                "anchor": {"file_path": rel_path, "symbol": event_name, "hash": file_hash},
                "anchor_last_checked": now,
                "created_at": now,
                "last_verified_at": now,
                "scope": "global",
                "expiry_condition": "事件类消失或重构时过期",
            })
            break  # 每文件最多一条（避免噪音）


def _extract_unity_rpc(
    content: str, rel_path: str, file_hash: str, now: str,
    extracted: dict[str, list],
) -> None:
    """提取 Unity RPC/WebSocket 接口标记（轻量）。"""
    for m in re.finditer(r'\[(?:RPC|Command|ClientRpc|ServerRpc)\]', content):
        # 找到 RPC 标注后取下一个方法名
        rest = content[m.end():]
        method_m = re.search(r'(?:public|private|protected)\s+\w+\s+(\w+)\s*\(', rest[:200])
        if method_m:
            method_name = method_m.group(1)
            extracted["protocol_catalog"].append({
                "id": f"rpc-{method_name.lower()[:32]}",
                "name": method_name,
                "type": "rpc",
                "source": "code_scan",
                "evidence": [rel_path],
                "confidence": "medium",
                "status": "inferred",
                "anchor": {"file_path": rel_path, "symbol": method_name, "hash": file_hash},
                "anchor_last_checked": now,
                "created_at": now,
                "last_verified_at": now,
                "scope": "global",
                "expiry_condition": "RPC 方法消失或签名变更时过期",
            })
            break


def _extract_unreal_events(
    content: str, rel_path: str, file_hash: str, now: str,
    extracted: dict[str, list],
) -> None:
    """提取 Unreal C++ Delegate/Event 模式（轻量）。"""
    for m in re.finditer(r'DECLARE_(?:DYNAMIC_)?(?:MULTICAST_)?DELEGATE(?:_\w+)?\s*\(\s*(\w+)', content):
        delegate_name = m.group(1)
        extracted["event_catalog"].append({
            "id": f"evt-{delegate_name.lower()[:32]}",
            "name": delegate_name,
            "type": "delegate",
            "source": "code_scan",
            "evidence": [rel_path],
            "confidence": "medium",
            "status": "inferred",
            "anchor": {"file_path": rel_path, "symbol": delegate_name, "hash": file_hash},
            "anchor_last_checked": now,
            "created_at": now,
            "last_verified_at": now,
            "scope": "global",
            "expiry_condition": "Delegate 定义消失或重命名时过期",
        })
        break


def _extract_proto_rpc(
    content: str, rel_path: str, file_hash: str, now: str,
    extracted: dict[str, list],
) -> None:
    """提取 Protobuf RPC 服务定义（轻量）。"""
    for m in re.finditer(r'rpc\s+(\w+)\s*\(', content):
        rpc_name = m.group(1)
        extracted["protocol_catalog"].append({
            "id": f"rpc-{rpc_name.lower()[:32]}",
            "name": rpc_name,
            "type": "grpc",
            "source": "code_scan",
            "evidence": [rel_path],
            "confidence": "high",
            "status": "inferred",
            "anchor": {"file_path": rel_path, "symbol": rpc_name, "hash": file_hash},
            "anchor_last_checked": now,
            "created_at": now,
            "last_verified_at": now,
            "scope": "global",
            "expiry_condition": "proto 定义变更时过期",
        })


def _extract_log_patterns(
    content: str, rel_path: str, file_hash: str, now: str,
    extracted: dict[str, list],
) -> None:
    """提取日志关键模式（通用，轻量）。"""
    # 查找明显的关键日志字符串（含 error/fail/success 等关键字）
    for m in re.finditer(
        r'(?:Log|Debug|Error|Warn|Info)\s*\.\s*\w+\s*\(\s*["\']([^"\']{10,80})["\']',
        content,
    ):
        pattern = m.group(1)
        if any(kw in pattern.lower() for kw in ("error", "fail", "success", "complete", "init")):
            extracted["log_patterns"].append({
                "id": f"log-{hashlib.sha256(pattern.encode()).hexdigest()[:16]}",
                "pattern": pattern,
                "type": "log_string",
                "source": "code_scan",
                "evidence": [rel_path],
                "confidence": "low",
                "status": "inferred",
                "anchor": {"file_path": rel_path, "symbol": pattern[:32], "hash": file_hash},
                "anchor_last_checked": now,
                "created_at": now,
                "last_verified_at": now,
                "scope": "global",
                "expiry_condition": "日志语句删除或修改时过期",
            })
            break  # 每文件最多一条
