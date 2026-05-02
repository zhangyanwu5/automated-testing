"""Unity 引擎适配器 — 安装器（``openguard init`` 阶段调用）。

负责在被测 Unity 项目中部署 OpenGuard 所需的运行时文件：

被测项目目录约定
-----------------
::

    <project_root>/
      openguard/
        scripts/          ← OpenGuard 注入脚本常驻目录
          AutoPlayMode.cs ← PlayMode 触发脚本（常驻，随 Unity 启动编译）
          # 未来：LogCapture.cs, ScreenshotHelper.cs …
        runtime/          ← 运行时通信目录（trigger、状态文件等）
          trigger.txt     ← Python 写入，C# 读取后删除（触发 PlayMode）
          # 未来：screenshot_req.txt, status.json …
        reports/          ← 测试产出（截图、日志、报告）
          screenshots/
          logs/

      Assets/Editor/
        _openguard/       ← Junction → openguard/scripts/（对 Git/SVN 不可见）

版本控制安全性
--------------
- Windows: ``mklink /J``（Junction）对 Git 和 SVN **完全不可见**，不会被跟踪
- macOS/Linux: symlink（在 .gitignore 中排除）
- 额外防护：自动向 .gitignore 追加排除规则
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


# Assets 内的 Junction/symlink 名称
_JUNCTION_NAME = "_openguard"

# 项目侧目录名（openguard/ 下的子目录）
_SCRIPTS_DIR  = "scripts"   # 常驻脚本目录（对应 Junction 目标）
_RUNTIME_DIR  = "runtime"   # 运行时通信目录
_REPORTS_DIR  = "reports"   # 测试产出目录


class UnityInstaller:
    """在 Unity 项目中安装 OpenGuard 运行时文件。"""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    # ── 主入口 ────────────────────────────────────────────────────────────────

    def install(self) -> InstallResult:
        """执行完整安装流程，返回 InstallResult。"""
        result = InstallResult()

        # 1. 创建项目侧目录结构
        self._ensure_project_dirs(result)
        if result.has_fatal():
            return result

        # 2. 部署 Assets 文件（脚本等）
        self._deploy_assets(result)
        if result.has_fatal():
            return result

        # 3. 创建 Junction（Assets/Editor/_openguard → openguard/scripts/）
        self._ensure_junction(result)

        # 4. 更新 .gitignore
        self._patch_gitignore(result)

        return result

    def is_installed(self) -> bool:
        """检查安装是否已完成（用于幂等检查）。"""
        junction    = self._junction_path()
        scripts_dir = self._scripts_dir()
        # 兼容新旧脚本名
        has_bridge = (
            (scripts_dir / "_OpenGuardBridge.cs").exists()
            or (scripts_dir / "AutoPlayMode.cs").exists()
        )
        return scripts_dir.exists() and has_bridge and junction.exists()

    def read_status(self) -> dict:
        """读取 Bridge 主动写入的 status.json。

        status.json 格式：
            {"ready": true, "is_playing": false, "is_compiling": false, "version": "1"}

        Returns:
            dict，若文件不存在或解析失败则返回 {"ready": False}
        """
        import json
        status_file = self._runtime_dir() / "status.json"
        if not status_file.exists():
            return {"ready": False}
        try:
            # 用 utf-8-sig 支持 C# 写出的 UTF-8 BOM 文件
            return json.loads(status_file.read_text(encoding="utf-8-sig"))
        except Exception:
            return {"ready": False}

    def clear_status(self) -> None:
        """删除 status.json（launcher 启动前调用，避免读到旧状态）。"""
        f = self._runtime_dir() / "status.json"
        if f.exists():
            try:
                f.unlink()
            except Exception:
                pass

    def check_and_repair(self) -> "RepairResult":
        """检查 Bridge 是否存在且内容最新，不满足则自动修复。

        在 launcher.start() 入口调用，确保 Bridge 始终处于可用状态。

        Returns:
            RepairResult，包含：
            - ok: 是否可以继续（修复成功或无需修复）
            - repaired: 是否执行了修复动作
            - needs_recompile: 是否需要等待 Unity 重新编译
            - error: 失败原因（ok=False 时）
        """
        assets_dir  = Path(__file__).parent / "assets"
        src_bridge  = assets_dir / "_OpenGuardBridge.cs"
        dst_bridge  = self._scripts_dir() / "_OpenGuardBridge.cs"
        old_bridge  = self._scripts_dir() / "AutoPlayMode.cs"  # 旧版兼容

        if not src_bridge.exists():
            return RepairResult(ok=False,
                                error="engines/unity/assets/_OpenGuardBridge.cs 不存在，"
                                      "OpenGuard 安装可能已损坏，请重新安装 OpenGuard")

        src_bytes = src_bridge.read_bytes()

        # 情况1：脚本存在且内容与源一致 → 检查是否需要清理旧版脚本或修复 Junction
        if dst_bridge.exists() and dst_bridge.read_bytes() == src_bytes:
            repaired_detail = []
            repaired = False

            # 始终检查并清理旧版 AutoPlayMode.cs（与新 Bridge 类名冲突会导致编译失败）
            if old_bridge.exists():
                try:
                    old_bridge.unlink()
                    meta = old_bridge.with_suffix(".cs.meta")
                    if meta.exists():
                        meta.unlink()
                    repaired_detail.append("已清理旧版 AutoPlayMode.cs（类名冲突）")
                    repaired = True
                except Exception:
                    pass

            # Junction 是否也存在？
            if not self._junction_path().exists():
                result = InstallResult()
                self._ensure_junction(result)
                if result.has_fatal():
                    return RepairResult(ok=False, error=result.messages()[-1][1])
                repaired_detail.append("Junction 已修复")
                repaired = True

            if not repaired:
                return RepairResult(ok=True, repaired=False)

            # 旧版脚本被清理时，需要等 Unity 重编译（检测到文件删除会触发编译）
            needs_recompile = any("AutoPlayMode" in d for d in repaired_detail)
            return RepairResult(ok=True, repaired=True,
                                needs_recompile=needs_recompile,
                                detail="；".join(repaired_detail))

        # 情况2：脚本不存在或内容过期 → 需要重装
        repaired_detail = []

        # 清理旧版脚本（避免两个脚本同时存在引发冲突）
        if old_bridge.exists():
            try:
                old_bridge.unlink()
                meta = old_bridge.with_suffix(".cs.meta")
                if meta.exists():
                    meta.unlink()
                repaired_detail.append("已删除旧版 AutoPlayMode.cs")
            except Exception:
                pass

        # 写入新脚本
        try:
            self._scripts_dir().mkdir(parents=True, exist_ok=True)
            dst_bridge.write_bytes(src_bytes)
            repaired_detail.append("Bridge 脚本已更新")
        except Exception as e:
            return RepairResult(ok=False, error=f"写入 Bridge 脚本失败：{e}")

        # 确保 Junction 存在
        result = InstallResult()
        self._ensure_junction(result)
        if result.has_fatal():
            return RepairResult(ok=False, error=result.messages()[-1][1])
        repaired_detail.append("Junction 已就绪")

        # 确保 runtime/ 目录存在
        self._runtime_dir().mkdir(parents=True, exist_ok=True)

        return RepairResult(
            ok=True,
            repaired=True,
            needs_recompile=True,   # 脚本变化，Unity 需要重编译
            detail="；".join(repaired_detail),
        )

    # ── 运行时通信（通过 IPCClient）────────────────────────────────────────

    def get_ipc_client(self):
        """返回指向本项目 runtime/ 目录的 IPCClient 实例。

        调用方通过此方法获取 IPC 客户端，无需关心文件路径细节。
        """
        from openguard.ipc import IPCClient
        return IPCClient(self._runtime_dir())

    # ── 路径辅助 ──────────────────────────────────────────────────────────────

    def _scripts_dir(self) -> Path:
        return self.project_root / "openguard" / _SCRIPTS_DIR

    def _runtime_dir(self) -> Path:
        return self.project_root / "openguard" / _RUNTIME_DIR

    def _reports_dir(self) -> Path:
        return self.project_root / "openguard" / _REPORTS_DIR

    def _junction_path(self) -> Path:
        return self.project_root / "Assets" / "Editor" / _JUNCTION_NAME

    # ── 内部步骤 ──────────────────────────────────────────────────────────────

    def _ensure_project_dirs(self, result: "InstallResult") -> None:
        """创建 openguard/{scripts,runtime,reports/screenshots,reports/logs}。"""
        dirs = [
            self._scripts_dir(),
            self._runtime_dir(),
            self._reports_dir() / "screenshots",
            self._reports_dir() / "logs",
        ]
        for d in dirs:
            try:
                d.mkdir(parents=True, exist_ok=True)
                result.add_ok(f"目录已就绪：openguard/{d.relative_to(self.project_root / 'openguard')}")
            except Exception as e:
                result.add_fatal(f"无法创建目录 {d}：{e}")
                return

    def _deploy_assets(self, result: "InstallResult") -> None:
        """将 engines/unity/assets/ 下的文件复制到 openguard/scripts/。

        若目标文件已存在但内容与源不同（版本更新），自动覆盖。
        """
        assets_dir = Path(__file__).parent / "assets"
        if not assets_dir.exists():
            result.add_warn("assets/ 目录不存在，跳过资产部署")
            return

        for src in assets_dir.iterdir():
            if src.suffix in (".cs", ".js", ".lua", ".py"):
                dst = self._scripts_dir() / src.name
                src_bytes = src.read_bytes()
                if dst.exists():
                    if dst.read_bytes() == src_bytes:
                        result.add_ok(f"脚本已是最新，跳过：scripts/{src.name}")
                        continue
                    # 内容不同 → 覆盖更新
                try:
                    dst.write_bytes(src_bytes)
                    action = "已更新" if dst.exists() else "已部署"
                    result.add_ok(f"脚本{action}：scripts/{src.name}")
                except Exception as e:
                    result.add_warn(f"部署 {src.name} 失败：{e}")

    def _ensure_junction(self, result: "InstallResult") -> None:
        """确保 Assets/Editor/_openguard → openguard/scripts/ Junction 存在。"""
        junction = self._junction_path()
        target   = self._scripts_dir().resolve()

        junction.parent.mkdir(parents=True, exist_ok=True)

        # 已存在且指向正确 → 跳过
        if junction.exists() or junction.is_symlink():
            try:
                if junction.resolve() == target:
                    result.add_ok("Assets/Editor/_openguard Junction 已存在，跳过")
                    return
            except Exception:
                pass
            # 指向错误 → 删除重建
            self._remove_junction(junction)

        linked = self._create_junction(junction, target)
        if linked:
            rel_target = (self.project_root / "openguard" / _SCRIPTS_DIR)
            result.add_ok(
                f"Assets/Editor/{_JUNCTION_NAME} → openguard/{_SCRIPTS_DIR}/ Junction 已创建"
            )
        else:
            # 降级：目录复制
            import shutil
            try:
                shutil.copytree(self._scripts_dir(), junction)
                result.add_warn(
                    f"Junction 创建失败，已复制目录到 Assets/Editor/{_JUNCTION_NAME}。\n"
                    "  建议手动将此目录加入 .gitignore 或 SVN ignore。"
                )
            except Exception as e:
                result.add_fatal(f"Junction 和目录复制均失败：{e}")

    def _remove_junction(self, junction: Path) -> None:
        try:
            if junction.is_symlink():
                junction.unlink()
            elif sys.platform == "win32":
                # Windows Junction 需要 rmdir
                subprocess.run(["cmd", "/c", "rmdir", str(junction)],
                               capture_output=True)
            else:
                import shutil
                shutil.rmtree(junction)
        except Exception:
            pass

    def _create_junction(self, junction: Path, target: Path) -> bool:
        """创建 Junction（Windows）或 symlink（其他系统）。返回是否成功。"""
        if sys.platform == "win32":
            # mklink /J 不需要管理员权限，对 Git/SVN 完全不可见
            r = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
                capture_output=True, text=True,
            )
            return r.returncode == 0
        else:
            try:
                junction.symlink_to(target, target_is_directory=True)
                return True
            except Exception:
                return False

    def _patch_gitignore(self, result: "InstallResult") -> None:
        """向 .gitignore 追加排除规则（幂等）。"""
        gi = self.project_root / ".gitignore"
        rule    = f"Assets/Editor/{_JUNCTION_NAME}/"
        comment = "# OpenGuard runtime scripts (managed by openguard init)"
        existing = gi.read_text(encoding="utf-8") if gi.exists() else ""
        if rule in existing:
            return
        sep = "\n" if existing and not existing.endswith("\n") else ""
        gi.write_text(
            existing + sep + f"\n{comment}\n{rule}\n",
            encoding="utf-8",
        )
        result.add_ok(f".gitignore 已追加排除规则：{rule}")



# ── 安装结果 ──────────────────────────────────────────────────────────────────

class InstallResult:
    """收集安装过程中的所有消息（ok / warn / fatal）。"""

    def __init__(self):
        self._messages: list[tuple[str, str]] = []  # (level, message)

    def add_ok(self, msg: str)    -> None: self._messages.append(("ok",    msg))
    def add_warn(self, msg: str)  -> None: self._messages.append(("warn",  msg))
    def add_fatal(self, msg: str) -> None: self._messages.append(("fatal", msg))

    def has_fatal(self) -> bool:
        return any(lvl == "fatal" for lvl, _ in self._messages)

    def messages(self) -> list[tuple[str, str]]:
        return list(self._messages)

    def print_to_cli(self, cmd: str = "init") -> None:
        """用 cli.spinner 输出所有消息。"""
        from openguard.cli.spinner import ok, warn
        for level, msg in self._messages:
            if level == "ok":
                ok(msg, cmd=cmd)
            else:
                warn(msg, cmd=cmd)


# ── 修复结果 ──────────────────────────────────────────────────────────────────

from dataclasses import dataclass, field as dc_field


@dataclass
class RepairResult:
    """check_and_repair() 的返回结果。"""
    ok:               bool        # 修复后是否可以继续执行
    repaired:         bool = False       # 是否执行了修复动作
    needs_recompile:  bool = False       # 是否需要等 Unity 重编译（脚本有变化）
    detail:           str  = ""          # 修复详情描述
    error:            str | None = None  # ok=False 时的错误原因

