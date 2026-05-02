"""Unity Editor PlayMode 启动器（REQ-16-01 ~ REQ-16-12）。

职责：
1. 检测 Unity Editor 进程是否已运行（进程名 + 命令行参数 + 窗口标题）
2. 按需启动或复用 Unity Editor；避免多实例冲突
3. 通过实时监听 editor.log 判断编译就绪和 PlayMode 就绪
4. 根据优先级自动选择入口场景
5. 自动触发 PlayMode（通过 EditorApplication.isPlaying 脚本注入）
6. 执行结束后按配置决定是否关闭进程
7. apply 前感知当前环境状态，灵活处理（不重复启动、必要时先关闭再重启）
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any





# ──────────────────────────────────────────────────────────────────────────────
# 就绪信号（REQ-16-03 / REQ-16-10）
# ──────────────────────────────────────────────────────────────────────────────

# 编辑器编译/启动就绪信号（任一匹配即视为就绪）
_EDITOR_READY_PATTERNS = [
    r"Compilation finished",
    r"All assemblies are up to date",
    r"Reloading assemblies\.\s*$",
    r"Editor application became active",
    r"Loading GUID database",  # 老版本 Unity
    r"Reloading assemblies after script compilation",  # Unity 2019.4+
    r"Compilation was raised",  # 某些 Unity 版本
    r"Loading completed in",  # Unity 2019.4+ 项目加载完成
    r"Refresh completed in",  # Unity 资源刷新完成
    r"Completed reload",  # Unity 脚本重新加载完成
    r"Initializing input",  # Unity 输入系统初始化（通常最后完成）
]

# PlayMode 就绪信号（含 Unity 各版本的格式变体）
_PLAYMODE_READY_PATTERNS = [
    r"Start Play Mode",
    r"Entering Play Mode",
    r"Entered Play Mode",
    r"EnteredPlayMode",               # Unity 2019+ UI 日志格式
    r"Application\.isPlaying:\s*True",  # 进入 PlayMode 时 Editor.log 写入
    r"playmodeStateChanged isPlaying:True",  # 某些版本
]

# 场景加载完成信号（含场景名占位符，调用时替换）
_SCENE_LOADED_PATTERNS = [
    r"Loaded scene '?{scene}'?",
    r"Finished loading scene '?{scene}'?",
    r"UnloadTime:",  # 场景卸载+加载完成后的 GC 日志
]

# 崩溃/严重错误信号
_CRASH_PATTERNS = [
    r"Crash!!!",
    r"Fatal error!",
    r"\[FATAL\]",
]

# 多实例冲突信号（检测到此信号说明出现了多 Unity 实例）
_MULTI_INSTANCE_PATTERNS = [
    r"Multiple Unity instances cannot open the same project",
    r"It looks like another Unity instance is running with this project",
]

# 已在 PlayMode 的信号（日志中搜索，判断当前是否已在 Play 状态）
_ALREADY_IN_PLAYMODE_PATTERNS = [
    r"Entered Play Mode",
    r"Start Play Mode",
    r"EnteredPlayMode",
    r"Application\.isPlaying:\s*True",
    r"playmodeStateChanged isPlaying:True",
]


# ──────────────────────────────────────────────────────────────────────────────
# 进程管理
# ──────────────────────────────────────────────────────────────────────────────

def find_unity_process(project_root: Path) -> "Any | None":
    """查找是否有已运行且打开了正确项目的 Unity Editor 进程。

    策略（按优先级）：
    1. psutil（最完整）：命令行参数精确匹配 → 单进程假设 → 窗口标题
    2. 降级（Windows，无 psutil）：WMI 命令行查询 → tasklist + 单进程假设
    3. 降级（非 Windows，无 psutil）：/proc 命令行扫描

    返回 psutil.Process 对象（如可用）或模拟对象 {"pid": int} 或 None。
    """
    # 优先尝试 psutil
    try:
        import psutil
        return _find_unity_process_psutil(project_root, psutil)
    except ImportError:
        pass

    # psutil 不可用时的降级方案
    if sys.platform == "win32":
        return _find_unity_process_windows(project_root)
    else:
        return _find_unity_process_proc(project_root)


def _find_unity_process_psutil(project_root: Path, psutil: Any) -> "Any | None":
    """使用 psutil 查找 Unity 进程（完整实现）。"""
    project_root_resolved = project_root.resolve()
    project_root_str = str(project_root_resolved).lower()
    project_name = project_root_resolved.name.lower()
    unity_names = {"unity.exe", "unity"}

    unity_procs: list[Any] = []
    matched_by_cmdline: Any = None

    for proc in psutil.process_iter(["name", "cmdline", "pid"]):
        try:
            name = (proc.info["name"] or "").lower()
            if name not in unity_names:
                continue
            unity_procs.append(proc)
            cmdline = proc.info.get("cmdline") or []
            cmdline_str = " ".join(cmdline).lower()
            if project_root_str in cmdline_str:
                matched_by_cmdline = proc
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if matched_by_cmdline is not None:
        return matched_by_cmdline

    if len(unity_procs) == 1:
        return unity_procs[0]

    if sys.platform == "win32" and len(unity_procs) > 1:
        matched = _find_unity_by_window_title(project_name, unity_procs)
        if matched:
            return matched

    return None


def _find_unity_process_windows(project_root: Path) -> "Any | None":
    """无 psutil 时的 Windows 降级：通过 WMIC 获取命令行，通过 tasklist 获取 PID。

    返回一个鸭子类型对象（含 pid / is_running / status 属性），
    与 psutil.Process 接口兼容（_is_process_alive 使用的子集）。
    """
    project_root_str = str(project_root.resolve()).lower()

    # 1. 尝试 WMIC 获取命令行（最精确）
    unity_pids_by_cmdline = _wmic_find_unity_pids(project_root_str)
    if unity_pids_by_cmdline:
        return _make_fake_proc(unity_pids_by_cmdline[0])

    # 2. 通过 tasklist 查找所有 Unity.exe PID
    all_unity_pids = _tasklist_find_unity_pids()
    if len(all_unity_pids) == 1:
        # 只有一个 Unity 进程，假设就是目标
        return _make_fake_proc(all_unity_pids[0])
    elif len(all_unity_pids) > 1:
        # 多个 Unity 进程：通过窗口标题尝试匹配
        project_name = project_root.resolve().name.lower()
        for pid in all_unity_pids:
            title = _get_window_title_for_pid(pid)
            if project_name in title.lower():
                return _make_fake_proc(pid)
        # 无法区分，返回第一个（宁可误判也不要重复启动）
        return _make_fake_proc(all_unity_pids[0])

    return None


def _find_unity_process_proc(project_root: Path) -> "Any | None":
    """无 psutil 时的 Linux/Mac 降级：扫描 /proc/*/cmdline。"""
    project_root_str = str(project_root.resolve()).lower()
    proc_root = Path("/proc")
    if not proc_root.exists():
        return None

    unity_pids: list[int] = []
    for pid_dir in proc_root.iterdir():
        if not pid_dir.name.isdigit():
            continue
        try:
            cmdline = (pid_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="replace").lower()
            if "unity" not in cmdline:
                continue
            if project_root_str in cmdline:
                return _make_fake_proc(int(pid_dir.name))
            if "unity" in cmdline.split("/")[-1]:
                unity_pids.append(int(pid_dir.name))
        except Exception:
            continue

    if len(unity_pids) == 1:
        return _make_fake_proc(unity_pids[0])
    return None


def _wmic_find_unity_pids(project_root_str: str) -> list[int]:
    """通过 WMIC 查询命令行中包含项目路径的 Unity 进程 PID。"""
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='Unity.exe'", "get", "ProcessId,CommandLine", "/format:csv"],
            capture_output=True, text=True, timeout=10, creationflags=0x08000000,
        )
        pids = []
        for line in result.stdout.splitlines():
            if not line.strip() or "CommandLine" in line:
                continue
            # CSV 格式：Node,CommandLine,ProcessId
            parts = line.split(",", 2)
            if len(parts) >= 3:
                cmdline = parts[1].lower()
                pid_str = parts[2].strip()
                if project_root_str in cmdline and pid_str.isdigit():
                    pids.append(int(pid_str))
        return pids
    except Exception:
        return []


def _tasklist_find_unity_pids() -> list[int]:
    """通过 tasklist 查找所有 Unity.exe 进程 PID。"""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Unity.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10, creationflags=0x08000000,
        )
        pids = []
        for line in result.stdout.splitlines():
            line = line.strip().strip('"')
            if not line or "No tasks" in line:
                continue
            parts = [p.strip('"') for p in line.split('","')]
            if len(parts) >= 2 and parts[1].isdigit():
                pids.append(int(parts[1]))
        return pids
    except Exception:
        return []


def _get_window_title_for_pid(pid: int) -> str:
    """获取指定 PID 的主窗口标题（Windows only）。"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).MainWindowTitle"],
            capture_output=True, text=True, timeout=5, creationflags=0x08000000,
        )
        return result.stdout.strip()
    except Exception:
        return ""


class _FakeProc:
    """模拟 psutil.Process 的最小接口，用于无 psutil 时的降级。"""
    def __init__(self, pid: int):
        self.pid = pid

    def is_running(self) -> bool:
        return self._check_alive()

    def status(self) -> str:
        return "running" if self._check_alive() else "zombie"

    def _check_alive(self) -> bool:
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {self.pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5, creationflags=0x08000000,
            )
            return str(self.pid) in result.stdout
        except Exception:
            return False


def _make_fake_proc(pid: int) -> "_FakeProc":
    return _FakeProc(pid)


def find_any_unity_process() -> "list[Any]":
    """返回所有正在运行的 Unity Editor 进程列表（不限项目）。"""
    try:
        import psutil
    except ImportError:
        return []

    unity_names = {"unity.exe", "unity"}
    procs = []
    for proc in psutil.process_iter(["name", "pid"]):
        try:
            name = (proc.info["name"] or "").lower()
            if name in unity_names:
                procs.append(proc)
        except Exception:
            continue
    return procs


def _wait_for_process(project_root: Path, *, timeout: float = 10.0) -> "Any | None":
    """轮询等待目标 Unity 进程出现且存活，返回进程对象或 None。

    用于替代 time.sleep 的"等待进程稳定"场景：
    - 弹窗关闭后等待已有实例可探测
    - 多实例冲突处理后等待进程数收敛

    每 0.5s 探测一次，直到找到存活进程或超时。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        proc = find_unity_process(project_root)
        if proc is not None and _is_process_alive(proc):
            return proc
        time.sleep(0.5)
    return None





def _find_unity_by_window_title(project_name: str, procs: "list[Any]") -> "Any | None":
    """通过窗口标题在多个 Unity 进程中找到打开了目标项目的那个（Windows only）。"""
    try:
        import ctypes
        EnumWindows = ctypes.windll.user32.EnumWindows
        GetWindowText = ctypes.windll.user32.GetWindowTextW
        GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
        GetWindowThreadProcessId = ctypes.windll.user32.GetWindowThreadProcessId
        IsWindowVisible = ctypes.windll.user32.IsWindowVisible

        pid_to_title: dict[int, str] = {}

        def enum_callback(hwnd, _):
            if not IsWindowVisible(hwnd):
                return True
            length = GetWindowTextLength(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            GetWindowText(hwnd, buf, length + 1)
            title = buf.value
            if "unity" in title.lower():
                pid = ctypes.c_ulong()
                GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                pid_to_title[pid.value] = title
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
        EnumWindows(WNDENUMPROC(enum_callback), 0)

        for proc in procs:
            try:
                title = pid_to_title.get(proc.pid, "").lower()
                if project_name in title:
                    return proc
            except Exception:
                continue
    except Exception:
        pass
    return None


def _is_process_alive(proc: Any) -> bool:
    """检查进程是否还在运行（兼容 psutil.Process、_FakeProc、subprocess.Popen）。"""
    if proc is None:
        return False
    # _FakeProc 或 psutil.Process（都有 is_running()）
    if hasattr(proc, "is_running"):
        try:
            return proc.is_running()
        except Exception:
            return False
    # subprocess.Popen 对象
    if hasattr(proc, "poll"):
        return proc.poll() is None
    return False


def _kill_unity_processes(project_root: Path) -> int:
    """关闭所有与该项目相关的 Unity Editor 进程（用于重启前清理）。

    返回关闭的进程数。
    """
    try:
        import psutil
    except ImportError:
        # 无 psutil 时使用 taskkill（Windows）
        if sys.platform == "win32":
            try:
                pids = _tasklist_find_unity_pids()
                for pid in pids:
                    subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                                   capture_output=True, timeout=10)
                return len(pids)
            except Exception:
                pass
        return 0

    project_root_str = str(project_root.resolve()).lower()
    project_name = project_root.resolve().name.lower()
    unity_names = {"unity.exe", "unity"}
    killed = 0

    for proc in psutil.process_iter(["name", "cmdline", "pid"]):
        try:
            name = (proc.info["name"] or "").lower()
            if name not in unity_names:
                continue
            cmdline = proc.info.get("cmdline") or []
            cmdline_str = " ".join(cmdline).lower()
            if project_root_str in cmdline_str or project_name in cmdline_str:
                proc.terminate()
                proc.wait(timeout=10)
                killed += 1
        except Exception:
            continue

    return killed


def _close_unity_multi_instance_dialog() -> bool:
    """检测并自动关闭 Unity 的"多实例冲突"错误弹窗（仅 Windows）。

    弹窗特征：
    - 标题："Error!" 或 "错误!"
    - 内容包含 "Multiple Unity instances" 或 "another Unity instance"
    - 按钮：单个 OK 按钮

    返回 True 表示找到并关闭了弹窗。
    """
    if sys.platform != "win32":
        return False

    try:
        # 方案1：使用 PowerShell + UIAutomation（最可靠）
        ps_script = r"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$desktop = [System.Windows.Automation.AutomationElement]::RootElement
$condition = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::NameProperty, "Error!"
)
$errorDialog = $desktop.FindFirst([System.Windows.Automation.TreeScope]::Children, $condition)
if ($errorDialog -ne $null) {
    $text = $errorDialog.FindAll([System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.Condition]::TrueCondition) | 
        ForEach-Object { $_.Current.Name } | Out-String
    if ($text -match "Multiple Unity" -or $text -match "another Unity") {
        $okBtn = $errorDialog.FindFirst(
            [System.Windows.Automation.TreeScope]::Descendants,
            (New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::NameProperty, "OK"
            ))
        )
        if ($okBtn -ne $null) {
            $invokePattern = $okBtn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
            $invokePattern.Invoke()
            Write-Output "CLOSED"
        }
    }
}
"""
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True, text=True, timeout=8,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        if "CLOSED" in result.stdout:
            return True
    except Exception:
        pass

    try:
        # 方案2：通过 ctypes SendMessage 直接关闭弹窗（更快）
        import ctypes
        user32 = ctypes.windll.user32

        # 查找标题为 "Error!" 的窗口
        hwnd = user32.FindWindowW(None, "Error!")
        if not hwnd:
            hwnd = user32.FindWindowW(None, "错误!")
        if not hwnd:
            return False

        # 获取窗口文本
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(4096)
        # 枚举子窗口获取文本内容
        texts = []

        def enum_child(child_hwnd, _):
            l = user32.GetWindowTextLengthW(child_hwnd)
            if l > 0:
                b = ctypes.create_unicode_buffer(l + 1)
                user32.GetWindowTextW(child_hwnd, b, l + 1)
                texts.append(b.value)
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumChildWindows(hwnd, WNDENUMPROC(enum_child), 0)

        all_text = " ".join(texts)
        if "Multiple Unity" in all_text or "another Unity" in all_text.lower():
            # 找到 OK 按钮并点击（BM_CLICK = 0x00F5）
            for text in texts:
                if text.strip().upper() == "OK":
                    ok_hwnd = user32.FindWindowExW(hwnd, None, "Button", "OK")
                    if ok_hwnd:
                        user32.SendMessageW(ok_hwnd, 0x00F5, 0, 0)  # BM_CLICK
                        return True
            # 直接关闭窗口
            user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
            return True
    except Exception:
        pass

    return False


# ──────────────────────────────────────────────────────────────────────────────
# 日志监听
# ──────────────────────────────────────────────────────────────────────────────

# Unity 编译/刷新进度信号（表示 Editor 正在处理，但还未就绪）
_EDITOR_PROGRESS_PATTERNS = [
    r"Compiling",
    r"Refreshing native plugins",
    r"Importing",
    r"Loading",
    r"Reloading",
    r"Rebuilding Library",
]

# PlayMode 进度信号
_PLAYMODE_PROGRESS_PATTERNS = [
    r"Entering Play Mode",
    r"Loading scene",
    r"Loading player data",
]


def _find_editor_log(project_root: Path, config: dict[str, Any]) -> Path | None:
    """定位 Unity Editor 日志文件路径。"""
    # 1. config 指定
    configured = config.get("runtime", {}).get("log_file")
    if configured:
        p = Path(configured)
        if not p.is_absolute():
            p = project_root / p
        return p

    # 2. 项目内 Logs/ 目录（Unity 2019+ 的默认位置）
    local_log = project_root / "Logs" / "Editor.log"
    if local_log.parent.exists():
        return local_log

    # 3. 用户目录（老版本 Unity）
    if sys.platform == "win32":
        appdata = os.environ.get("LOCALAPPDATA", "")
        if appdata:
            return Path(appdata) / "Unity" / "Editor" / "Editor.log"
    elif sys.platform == "darwin":
        home = Path.home()
        return home / "Library" / "Logs" / "Unity" / "Editor.log"
    else:
        home = Path.home()
        return home / ".config" / "unity3d" / "Editor.log"


from dataclasses import dataclass


@dataclass
class WaitResult:
    """日志等待操作的结构化结果。

    matched: True 表示命中了成功信号。
    matched_line: 命中的日志行（成功时）或空串。
    abort_reason: "crash" / "abort"（立即中止原因），None 表示正常。
    abort_line: 触发中止的日志行。
    timed_out: True 表示等待超时。
    last_progress_line: 超时时最后一条进度日志行（区分"卡死"与"正在进行中超时"）。
    """
    matched: bool = False
    matched_line: str = ""
    abort_reason: str | None = None   # "crash" | "abort" | None
    abort_line: str = ""
    timed_out: bool = False
    last_progress_line: str = ""      # 超时时有内容 → 说明 Editor 在工作，只是很慢

    @property
    def ok(self) -> bool:
        return self.matched

    def timeout_detail(self) -> str:
        """生成超时时的可读原因描述。"""
        if self.last_progress_line:
            return f"超时，但 Editor 仍在处理中（最后进度：{self.last_progress_line.strip()!r}）"
        return "超时，且无任何进度信号（Editor 可能已卡死或未响应）"


def _tail_log_until(
    log_path: Path,
    patterns: list[str],
    *,
    timeout: float,
    crash_patterns: list[str] | None = None,
    abort_patterns: list[str] | None = None,
    progress_patterns: list[str] | None = None,
    poll_interval: float = 0.5,
    start_offset: int = 0,
) -> WaitResult:
    """监听日志文件，直到命中成功信号、中止信号或超时。

    - patterns: 命中即成功，立即返回 matched=True。
    - crash_patterns: 命中立即返回 abort_reason="crash"。
    - abort_patterns: 命中立即返回 abort_reason="abort"（多实例冲突等）。
    - progress_patterns: 命中时记录为最后进度行，超时时用于区分"卡死"与"处理中超时"。
    """
    deadline = time.monotonic() + timeout
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
    compiled_crash = [re.compile(p, re.IGNORECASE) for p in (crash_patterns or [])]
    compiled_abort = [re.compile(p, re.IGNORECASE) for p in (abort_patterns or [])]
    compiled_progress = [re.compile(p, re.IGNORECASE) for p in (progress_patterns or [])]

    offset = start_offset
    last_progress_line: str = ""

    while time.monotonic() < deadline:
        if log_path.exists():
            try:
                with log_path.open("rb") as f:
                    # 检测日志是否被截断（Unity 重新启动时会清空并重写日志）
                    # 若文件大小小于当前 offset，说明日志被重置，从头开始读
                    file_size = log_path.stat().st_size
                    if file_size < offset:
                        offset = 0
                    f.seek(offset)
                    chunk = f.read()
                    if chunk:
                        offset += len(chunk)
                        text = chunk.decode("utf-8", errors="replace")
                        for line in text.splitlines():
                            for cp in compiled_abort:
                                if cp.search(line):
                                    return WaitResult(abort_reason="abort", abort_line=line)
                            for cp in compiled_crash:
                                if cp.search(line):
                                    return WaitResult(abort_reason="crash", abort_line=line)
                            for cp in compiled:
                                if cp.search(line):
                                    return WaitResult(matched=True, matched_line=line)
                            for cp in compiled_progress:
                                if cp.search(line):
                                    last_progress_line = line
            except Exception:
                pass
        time.sleep(poll_interval)

    return WaitResult(timed_out=True, last_progress_line=last_progress_line)


def _scan_log_tail(log_path: Path, *, tail_bytes: int = 65536) -> str:
    """读取日志文件末尾内容用于状态判断（不影响偏移量）。

    tail_bytes=0 表示读取全文。
    """
    if not log_path or not log_path.exists():
        return ""
    try:
        with log_path.open("rb") as f:
            if tail_bytes == 0:
                return f.read().decode("utf-8", errors="replace")
            size = log_path.stat().st_size
            offset = max(0, size - tail_bytes)
            f.seek(offset)
            return f.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def _log_contains(log_path: Path, patterns: list[str], *, tail_bytes: int = 65536) -> bool:
    """检查日志末尾是否含有任一 pattern（用于状态检测）。"""
    content = _scan_log_tail(log_path, tail_bytes=tail_bytes)
    if not content:
        return False
    for p in patterns:
        if re.search(p, content, re.IGNORECASE):
            return True
    return False


# ──────────────────────────────────────────────────────────────────────────────
# 场景选择（REQ-16-04）
# ──────────────────────────────────────────────────────────────────────────────

def _resolve_entry_scene(
    project_root: Path,
    config: dict[str, Any],
    test_knowledge: dict[str, Any],
) -> str | None:
    """按优先级选择入口场景路径。

    优先级：
    1. test_knowledge.scene_map（AI 填写）
    2. config.yaml runtime.entry_scene
    3. ProjectSettings/EditorBuildSettings.asset 第 0 个场景
    4. None（使用编辑器当前场景）
    """
    # 1. test_knowledge.scene_map：取第一个场景作为入口
    scene_map = test_knowledge.get("scene_map", {})
    if scene_map:
        # 优先取 login、main、entry 等常见入口名
        for key in ("login", "main", "entry", "start", "home"):
            if key in scene_map:
                return scene_map[key]
        # 取第一个
        return next(iter(scene_map.values()))

    # 2. config 指定
    entry_scene = config.get("runtime", {}).get("entry_scene")
    if entry_scene:
        return entry_scene

    # 3. EditorBuildSettings.asset
    build_settings = project_root / "ProjectSettings" / "EditorBuildSettings.asset"
    if build_settings.exists():
        try:
            content = build_settings.read_text(encoding="utf-8", errors="replace")
            # 格式：
            #   - enabled: 1
            #     path: Assets/Scenes/XXX.unity
            # 优先找 enabled: 1 的场景
            # 使用非 DOTALL 模式，确保只匹配单行
            enabled_pattern = r"enabled:\s*1\s*\n\s*path:\s*(\S+\.unity)"
            enabled_match = re.search(enabled_pattern, content)
            if enabled_match:
                return enabled_match.group(1).strip()
            #  fallback：找所有 path:
            matches = re.findall(r"path:\s*(\S+\.unity)", content)
            if matches:
                return matches[0].strip()
        except Exception:
            pass

    return None


# ──────────────────────────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────────────────────────

class UnityLauncher:
    """Unity Editor PlayMode 启动器。

    用法：
        launcher = UnityLauncher(project_root, config, test_knowledge)
        with launcher:
            # 此时 Unity 已就绪，可执行测试
            ...
        # with 块结束后按 auto_close 决定是否关闭

    环境感知策略（REQ-16-xx）：
    - 已在 PlayMode → 直接复用，无需任何操作
    - 已启动 Editor 但未在 PlayMode → 选场景 + 自动触发 PlayMode
    - 未启动 Editor → 先启动，再等待就绪，再触发 PlayMode
    - 多实例冲突 → 关闭冲突实例，保留/重启正确的那个
    """

    def __init__(
        self,
        project_root: Path,
        config: dict[str, Any],
        test_knowledge: dict[str, Any],
        *,
        event_sink=None,  # 可选，接受 (step, status, message) 的回调
    ):
        self.project_root = project_root
        self.config = config
        self.test_knowledge = test_knowledge
        self.event_sink = event_sink or (lambda step, status, msg: None)

        runtime = config.get("runtime", {})
        self.unity_path = runtime.get("unity_editor_path", "")
        self.auto_start: bool = runtime.get("auto_start", True)
        self.auto_close: bool = runtime.get("auto_close", True)
        self.startup_timeout: float = float(runtime.get("startup_timeout_seconds", 120))
        self.playmode_timeout: float = float(runtime.get("playmode_timeout_seconds", 120))
        self.custom_ready_pattern: str | None = (
            runtime.get("health_check", {}).get("pattern")
        )

        self._proc = None          # 由我们启动的进程（Popen）
        self._reused_proc = None   # 复用的已有进程（psutil.Process）
        self._log_path: Path | None = None
        self._log_start_offset = 0
        self._we_started = False   # 是否由我们启动
        self._we_entered_playmode = False  # 是否由我们触发了 PlayMode

    # ── context manager ──────────────────────────────────────────────────────

    def __enter__(self):
        result = self.start()
        if not result["ok"]:
            raise RuntimeError(result["error"])
        return self

    def __exit__(self, *_):
        self.stop()

    # ── 公开方法 ──────────────────────────────────────────────────────────────

    def start(self) -> dict[str, Any]:
        """启动 Unity Editor 并等待就绪（含 PlayMode）。

        返回 {"ok": bool, "error": str, "reused": bool, "state": str}

        state 取值：
        - "reused_playmode"  : 复用了已在 PlayMode 的 Editor
        - "reused_editor"    : 复用了已启动但未在 PlayMode 的 Editor，自动触发 PlayMode
        - "fresh_start"      : 全新启动 Editor 并触发 PlayMode
        """
        self._emit("unity_launcher", "running", "检测 Unity Editor 环境状态…")

        # ── 阶段0：确保 Bridge 脚本存在且最新 ───────────────────────────────
        from openguard.engines.unity.installer import UnityInstaller
        installer = UnityInstaller(self.project_root)
        repair = installer.check_and_repair()

        if not repair.ok:
            return {
                "ok": False,
                "error": (
                    f"Bridge 脚本检测失败：{repair.error}\n"
                    "请尝试重新运行 openguard init 修复安装。"
                ),
            }

        if repair.repaired:
            self._emit("unity_launcher", "warn",
                       f"Bridge 脚本已自动修复：{repair.detail}")

        # ── 阶段1：感知当前环境状态 ──────────────────────────────────────────
        env_state = self._detect_env_state()
        self._emit("unity_launcher", "info", f"当前环境状态：{env_state['description']}")

        if env_state["state"] == "in_playmode":
            # 已在 PlayMode，直接复用
            self._reused_proc = env_state.get("proc")
            self._log_path = env_state.get("log_path")
            if self._log_path and self._log_path.exists():
                self._log_start_offset = self._log_path.stat().st_size
            self._emit("unity_launcher", "passed",
                       "Unity Editor 已在 PlayMode，直接复用")
            return {"ok": True, "reused": True, "state": "reused_playmode"}

        elif env_state["state"] == "editor_running":
            # Editor 已运行但未在 PlayMode
            self._reused_proc = env_state.get("proc")
            self._log_path = env_state.get("log_path")
            if self._log_path and self._log_path.exists():
                self._log_start_offset = self._log_path.stat().st_size

            # 若 Bridge 刚被修复，需要等 Unity 重编译后再发 IPC 命令
            if repair.repaired and repair.needs_recompile:
                self._emit("unity_launcher", "running",
                           "Bridge 脚本已更新，等待 Unity 重新编译…")
                ready_result = self._wait_editor_ready()
                if not ready_result["ok"]:
                    return ready_result

            scene = _resolve_entry_scene(
                self.project_root, self.config, self.test_knowledge
            )
            inject_result = self._inject_playmode_trigger(scene)
            if not inject_result["ok"]:
                return inject_result

            pm_result = self._enter_playmode()
            if not pm_result["ok"]:
                return pm_result

            self._we_entered_playmode = True
            self._emit("unity_launcher", "passed", "PlayMode 已启动（复用已运行的 Editor）")
            return {"ok": True, "reused": True, "state": "reused_editor"}

        elif env_state["state"] == "not_running":
            # Editor 未运行，需要启动
            if not self.auto_start:
                return {
                    "ok": False,
                    "error": (
                        "Unity Editor 未运行且 auto_start=false。"
                        "请手动打开 Unity Editor 后重试。"
                    ),
                }

            # 启动 Editor
            launch_result = self._launch_editor()
            if not launch_result["ok"]:
                return launch_result

            # 确定日志路径（_launch_editor 已设置 self._log_path）
            if self._log_path is None:
                self._log_path = _find_editor_log(self.project_root, self.config)
            if self._log_path is None:
                return {"ok": False, "error": "无法定位 Unity Editor 日志文件路径"}

            # 等待编辑器就绪（同时监控多实例弹窗并自动关闭）
            # 此时 AutoPlayMode.cs 已被编译并驻留
            ready_result = self._wait_editor_ready_with_dialog_guard()
            if not ready_result["ok"]:
                return ready_result

            # Unity 就绪后写 trigger.txt，常驻脚本会在下一帧轮询到并进入 PlayMode
            scene = _resolve_entry_scene(
                self.project_root, self.config, self.test_knowledge
            )
            inject_result = self._inject_playmode_trigger(scene)
            if not inject_result["ok"]:
                return inject_result

            # 等待 PlayMode 就绪
            pm_result = self._enter_playmode()
            if not pm_result["ok"]:
                return pm_result

            self._we_entered_playmode = True
            self._emit("unity_launcher", "passed", "Unity Editor 已就绪，PlayMode 已启动")
            return {"ok": True, "reused": False, "state": "fresh_start"}

        else:
            # 未知状态，回退到原有逻辑
            return {"ok": False, "error": f"无法确定 Unity Editor 环境状态：{env_state}"}

    def stop(self) -> None:
        """按配置决定是否关闭 Unity Editor。"""
        # 清理 PlayMode 注入脚本
        self._cleanup_playmode_trigger_script()

        if not self._we_started or not self.auto_close:
            return
        if self._proc is not None and self._proc.poll() is None:
            self._emit("unity_launcher", "running", "关闭 Unity Editor…")
            try:
                self._proc.terminate()
                self._proc.wait(timeout=15)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._emit("unity_launcher", "passed", "Unity Editor 已关闭")

    # ── 环境状态检测 ──────────────────────────────────────────────────────────

    def _detect_env_state(self) -> dict[str, Any]:
        """检测当前 Unity Editor 环境状态。

        返回 {"state": str, "description": str, "proc": ..., "log_path": ...}

        state 取值：
        - "in_playmode"   : Editor 已运行且正在 PlayMode
        - "editor_running": Editor 已运行但不在 PlayMode
        - "not_running"   : Editor 未运行
        """
        proc = find_unity_process(self.project_root)

        if proc is None or not _is_process_alive(proc):
            return {
                "state": "not_running",
                "description": "Unity Editor 未运行",
                "proc": None,
                "log_path": None,
            }

        # Editor 正在运行，通过 status.json 判断是否在 PlayMode
        # status.json 由 Bridge 主动写入，比日志扫描更可靠
        from openguard.engines.unity.installer import UnityInstaller
        log_path = _find_editor_log(self.project_root, self.config)

        in_playmode = False
        installer = UnityInstaller(self.project_root)
        status = installer.read_status()
        if status.get("ready"):
            # Bridge 已就绪，直接读 is_playing
            in_playmode = bool(status.get("is_playing", False))
        elif log_path and log_path.exists():
            # Bridge 未就绪（可能尚未安装或编译），降级用日志扫描
            in_playmode = _log_contains(log_path, _PLAYMODE_READY_PATTERNS, tail_bytes=0)

        if in_playmode:
            return {
                "state": "in_playmode",
                "description": "Unity Editor 正在运行，已在 PlayMode",
                "proc": proc,
                "log_path": log_path,
            }
        else:
            return {
                "state": "editor_running",
                "description": "Unity Editor 正在运行，未在 PlayMode",
                "proc": proc,
                "log_path": log_path,
            }

    # ── 选场景 + 触发 PlayMode ────────────────────────────────────────────────

    def _prepare_and_enter_playmode(self, *, reused: bool) -> dict[str, Any]:
        """选择入口场景，然后自动触发 PlayMode。"""
        # 选择场景
        scene = _resolve_entry_scene(
            self.project_root, self.config, self.test_knowledge
        )
        if scene:
            self._emit("unity_launcher", "info", f"入口场景：{scene}")
        else:
            self._emit("unity_launcher", "info", "未指定入口场景，使用编辑器当前场景")

        # 注入 PlayMode 触发脚本（含场景切换逻辑）
        inject_result = self._inject_playmode_trigger(scene)
        if not inject_result["ok"]:
            # 注入失败不阻断，降级为被动等待
            self._emit("unity_launcher", "warn",
                       f"PlayMode 触发脚本注入失败，将被动等待：{inject_result['error']}")

        # 等待 PlayMode 就绪
        pm_result = self._enter_playmode()
        if not pm_result["ok"]:
            return pm_result

        state = "reused_editor" if reused else "fresh_start"
        self._emit("unity_launcher", "passed", "Unity Editor 已就绪，PlayMode 已启动")
        return {"ok": True, "reused": reused, "state": state}

    # ── PlayMode 注入脚本 ────────────────────────────────────────────────────

    def _inject_playmode_trigger(self, scene_path: str | None) -> dict[str, Any]:
        """通过 IPC 协议向 Bridge 脚本发送 enter_playmode 命令。

        如果提供了 scene_path，先发 open_scene 再发 enter_playmode。
        IPC 命令超时时，降级检查 status.json（Unity 大场景加载时帧更新可能暂停）。
        """
        from openguard.ipc import IPCClient
        from openguard.ipc.protocol import Cmd
        from openguard.engines.unity.installer import UnityInstaller

        client    = IPCClient(self.project_root / "openguard" / "runtime")
        installer = UnityInstaller(self.project_root)

        # 可选：先切换场景（Unity 加载大场景时 IPC 可能超时，这里允许失败）
        if scene_path:
            self._emit("unity_launcher", "running", f"切换场景：{scene_path}")
            resp = client.send(Cmd.OPEN_SCENE,
                               args={"scene": scene_path},
                               timeout=30.0)
            if not resp.ok:
                self._emit("unity_launcher", "warn",
                           f"场景切换失败（将继续尝试进入 PlayMode）：{resp.error}")

        # 发送 enter_playmode
        self._emit("unity_launcher", "running",
                   "向 Unity Bridge 发送 enter_playmode 请求…")
        resp = client.send(Cmd.ENTER_PLAYMODE, timeout=15.0)

        if not resp.ok:
            # IPC 超时时降级：检查 status.json，Unity 可能已经在 PlayMode
            # （大场景加载时 EditorApplication.update 被阻塞，但 playModeStateChanged 仍会触发）
            status = installer.read_status()
            if status.get("is_playing"):
                self._emit("unity_launcher", "info",
                           "IPC 超时，但 status.json 确认已在 PlayMode（正常）")
                return {"ok": True}
            return {"ok": False, "error": resp.error}

        data  = resp.data or {}
        state = data.get("state", "") if isinstance(data, dict) else str(data)
        if state == "already_playing":
            self._emit("unity_launcher", "info", "Unity 已在 PlayMode（Bridge 确认）")
        else:
            self._emit("unity_launcher", "running",
                       f"Bridge 确认：{state}，等待 PlayMode 就绪…")
        return {"ok": True}

    def _cleanup_playmode_trigger_script(self) -> None:
        """清理 runtime/ 通信文件（stop 时调用）。常驻脚本本身保留，不删除。"""
        from openguard.ipc import IPCClient
        IPCClient(self.project_root / "openguard" / "runtime").cleanup()

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    def _resolve_unity_path(self) -> tuple[str, str | None]:
        """解析最终使用的 Unity Editor 路径。

        优先级：
        1. config.yaml 中 runtime.unity_editor_path（显式配置，直接校验）
        2. tools/runtime/unity.find_unity_editors() 自动发现（按优先级取第一个）

        返回 (path, error)：path 为空串且 error 不为 None 时表示失败。
        """
        from openguard.tools.runtime.process import check_executable
        from openguard.tools.runtime.unity import find_unity_editors

        if self.unity_path:
            # 显式配置：校验文件存在且可执行
            if not check_executable(self.unity_path):
                return "", f"unity_editor_path 不存在或不可执行：{self.unity_path}"
            return self.unity_path, None

        # 未配置：自动发现
        self._emit("unity_launcher", "running",
                   "config.yaml 未配置 unity_editor_path，尝试自动发现…")
        unity_version = self.config.get("runtime", {}).get("unity_version")
        candidates = find_unity_editors(str(self.project_root), unity_version)
        if not candidates:
            return "", (
                "未配置 unity_editor_path，且在本机未能自动发现 Unity Editor。"
                "请在 config.yaml 中设置 runtime.unity_editor_path，"
                "或设置环境变量 UNITY_EDITOR_PATH。"
            )
        chosen = candidates[0]
        self._emit("unity_launcher", "info",
                   f"自动发现 Unity Editor：{chosen['label']} → {chosen['path']}")
        return chosen["path"], None

    def _launch_editor(self) -> dict[str, Any]:
        """启动 Unity Editor 进程。"""
        resolved_path, err = self._resolve_unity_path()
        if err:
            return {"ok": False, "error": err}

        # 清理旧 status.json，避免启动后读到上次运行的旧状态
        from openguard.engines.unity.installer import UnityInstaller
        UnityInstaller(self.project_root).clear_status()

        # 日志输出到项目 Logs/ 目录，确保我们能监听
        log_dir = self.project_root / "Logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "Editor.log"

        cmd = [
            resolved_path,
            "-projectPath", str(self.project_root),
            "-logFile", str(log_file),
        ]
        self._emit("unity_launcher", "running", f"启动 Unity Editor: {resolved_path}")

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._we_started = True
            self._log_path = log_file
            # start_offset=0：从头监听，_wait_editor_ready 会等旧日志被清空后再开始
            self._log_start_offset = 0
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": f"Unity Editor 启动失败：{e}"}

    def _wait_editor_ready_with_dialog_guard(self) -> dict[str, Any]:
        """等待编辑器就绪，同时在后台监控多实例弹窗并自动关闭。

        如果新进程启动后出现 "Multiple Unity instances" 弹窗：
        1. 自动关闭弹窗（点击 OK）
        2. 关闭我们刚启动的冲突进程
        3. 切换到复用已有实例的模式
        """
        import threading

        dialog_closed = threading.Event()
        dialog_found = threading.Event()

        def _monitor_dialog():
            """后台线程：每 1s 检查一次是否有 Unity 多实例弹窗。"""
            deadline = time.monotonic() + self.startup_timeout
            while time.monotonic() < deadline and not dialog_closed.is_set():
                if _close_unity_multi_instance_dialog():
                    dialog_found.set()
                    dialog_closed.set()
                    return
                time.sleep(1.0)

        monitor_thread = threading.Thread(target=_monitor_dialog, daemon=True)
        monitor_thread.start()

        # 等待编辑器就绪（同时弹窗监控线程在后台跑）
        result = self._wait_editor_ready()

        dialog_closed.set()  # 通知监控线程退出

        if dialog_found.is_set():
            # 出现了多实例弹窗，已自动关闭弹窗
            self._emit("unity_launcher", "warn",
                       "检测到并自动关闭了多实例冲突弹窗，切换到复用已有实例模式…")
            # 关闭我们启动的冲突进程
            if self._proc is not None and self._proc.poll() is None:
                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=10)
                except Exception:
                    pass
                self._proc = None
                self._we_started = False

            # 轮询等待已有实例可探测（进程存活 + 日志可读），最多 10s
            existing = _wait_for_process(self.project_root, timeout=10.0)
            if existing and _is_process_alive(existing):
                self._reused_proc = existing
                new_log = _find_editor_log(self.project_root, self.config)
                if new_log and new_log.exists():
                    self._log_path = new_log
                    self._log_start_offset = new_log.stat().st_size
                self._emit("unity_launcher", "info", "成功切换到已有 Unity 实例")
                return {"ok": True}
            else:
                return {
                    "ok": False,
                    "error": "关闭多实例弹窗后无法找到有效的 Unity Editor 实例（等待 10s 仍未就绪），请重试",
                }

        return result

    def _wait_editor_ready(self) -> dict[str, Any]:
        """等待编辑器就绪。

        策略（方案4）：
        - Bridge 启动时主动写 openguard/runtime/status.json {"ready": true, ...}
        - Python 轮询此文件，不依赖日志格式
        - 同时检测 Unity 进程是否存活，进程死亡立即报错而不等超时
        - 超时分层：进程死 → 立即；无进展 N 秒 → 警告；硬性超时 → 报错
        """
        from openguard.engines.unity.installer import UnityInstaller

        installer   = UnityInstaller(self.project_root)
        timeout     = self.startup_timeout
        no_progress = 60.0   # 60 秒无任何进展（日志不增长）→ 警告

        self._emit("unity_launcher", "running",
                   f"等待 Unity Bridge 就绪（超时 {timeout:.0f}s，进程死亡立即报错）…")

        deadline       = time.monotonic() + timeout
        last_log_size  = 0
        last_progress  = time.monotonic()
        warned_slow    = False
        elapsed_report = 0.0

        while time.monotonic() < deadline:
            elapsed = time.monotonic() - (deadline - timeout)

            # ── 1. 进程存活检测 ──────────────────────────────────────────────
            proc = self._proc or self._reused_proc
            if proc is not None and not _is_process_alive(proc):
                return {
                    "ok": False,
                    "error": (
                        f"Unity Editor 进程已退出（等待就绪时，已等 {elapsed:.0f}s）。"
                        "可能原因：许可证失效、项目损坏或启动参数错误。"
                        f"请查看 {self._log_path} 了解详情。"
                    ),
                }

            # ── 2. 检查 status.json ──────────────────────────────────────────
            status = installer.read_status()
            if status.get("ready"):
                self._emit("unity_launcher", "info",
                           f"Bridge 已就绪（is_playing={status.get('is_playing', False)}，"
                           f"耗时 {elapsed:.0f}s）")
                # 记录当前日志偏移（后续 PlayMode 检测从此处开始）
                if self._log_path and self._log_path.exists():
                    self._log_start_offset = self._log_path.stat().st_size
                return {"ok": True}

            # ── 3. 无进展检测（日志文件大小是否增长）───────────────────────
            if self._log_path and self._log_path.exists():
                try:
                    cur_size = self._log_path.stat().st_size
                    if cur_size != last_log_size:
                        last_log_size = cur_size
                        last_progress = time.monotonic()
                except Exception:
                    pass

            no_progress_elapsed = time.monotonic() - last_progress
            if no_progress_elapsed > no_progress and not warned_slow:
                warned_slow = True
                self._emit("unity_launcher", "warn",
                           f"Unity 已等待 {elapsed:.0f}s，最近 {no_progress:.0f}s 无日志增长，"
                           "可能加载较慢或卡住。继续等待…")

            # ── 4. 定期进度报告 ──────────────────────────────────────────────
            if elapsed - elapsed_report >= 30.0:
                elapsed_report = elapsed
                self._emit("unity_launcher", "running",
                           f"等待 Unity 就绪中（已等 {elapsed:.0f}s，进程存活）…")

            # ── 5. 多实例冲突检测（仍保留日志扫描，因为这是启动阶段唯一可靠方式）
            if self._log_path and self._log_path.exists():
                try:
                    with self._log_path.open("rb") as f:
                        f.seek(self._log_start_offset)
                        chunk = f.read(65536)
                        if chunk:
                            text = chunk.decode("utf-8", errors="replace")
                            for p in _MULTI_INSTANCE_PATTERNS:
                                import re as _re
                                if _re.search(p, text, _re.IGNORECASE):
                                    self._emit("unity_launcher", "warn",
                                               "检测到多实例冲突…")
                                    return self._handle_multi_instance_conflict()
                            for p in _CRASH_PATTERNS:
                                if _re.search(p, text, _re.IGNORECASE):
                                    return {"ok": False,
                                            "error": f"Unity 启动时崩溃，请查看日志"}
                except Exception:
                    pass

            time.sleep(0.5)

        return {
            "ok": False,
            "error": (
                f"Unity Editor 启动超时（>{timeout:.0f}s）：Bridge 未就绪。\n"
                "可能原因：项目过大导致编译/加载耗时过长。\n"
                f"提示：可在 config.yaml 中增大 runtime.startup_timeout_seconds（当前 {timeout:.0f}s）。"
            ),
        }

    def _handle_multi_instance_conflict(self) -> dict[str, Any]:
        """处理多实例冲突：终止我们启动的冲突进程，切换到复用已有实例。

        策略：
        1. 终止由我们新启动的进程（旧进程才是"正确"的那个）
        2. 轮询等待进程数收敛到 1（最多 10s）
        3. 切换到复用已有实例，检查日志确认就绪状态
        """
        # 终止我们刚启动的进程
        if self._proc is not None and self._proc.poll() is None:
            self._emit("unity_launcher", "running", "终止新启动的冲突进程，复用已有实例…")
            try:
                self._proc.terminate()
                self._proc.wait(timeout=10)
            except Exception:
                pass
            self._proc = None
            self._we_started = False

        # 轮询等待进程数收敛（冲突进程退出后才能找到"正确"的那个）
        existing = _wait_for_process(self.project_root, timeout=10.0)
        if existing is None or not _is_process_alive(existing):
            return {
                "ok": False,
                "error": (
                    "多实例冲突：等待 10s 后仍无法找到有效的 Unity Editor 实例。"
                    "请手动关闭所有 Unity 实例，然后重试。"
                ),
            }

        self._reused_proc = existing
        # 更新日志路径（可能和我们预期的不同）
        new_log = _find_editor_log(self.project_root, self.config)
        if new_log and new_log.exists():
            self._log_path = new_log
            # 读取已有日志末尾，检查是否已就绪
            if _log_contains(new_log, _EDITOR_READY_PATTERNS):
                self._log_start_offset = new_log.stat().st_size
                self._emit("unity_launcher", "info", "已有 Unity 实例已就绪，复用")
                return {"ok": True}

        # 等待已有实例就绪
        self._emit("unity_launcher", "running", "等待已有 Unity 实例就绪…")
        r = _tail_log_until(
            self._log_path,
            _EDITOR_READY_PATTERNS,
            timeout=self.startup_timeout,
            crash_patterns=_CRASH_PATTERNS,
            progress_patterns=_EDITOR_PROGRESS_PATTERNS,
            start_offset=0,  # 从头搜索，因为是已有实例
        )

        if not r.ok:
            detail = f"Unity 崩溃：{r.abort_line}" if r.abort_reason == "crash" else r.timeout_detail()
            return {"ok": False, "error": f"复用已有 Unity 实例失败：{detail}"}

        if self._log_path and self._log_path.exists():
            self._log_start_offset = self._log_path.stat().st_size

        self._emit("unity_launcher", "info", "已有 Unity 实例已就绪，复用")
        return {"ok": True}

    def _open_scene(self, scene_path: str) -> dict[str, Any]:
        """通过 Unity Editor 打开指定场景。

        当前实现：写入一个临时 EditorScript 通过 [InitializeOnLoad] 调用。
        这是进程外驱动 Unity 打开场景的标准方式。
        """
        script_dir = self.project_root / "Assets" / "Editor" / "_openguard_temp"
        script_dir.mkdir(parents=True, exist_ok=True)
        script_file = script_dir / "OpenSceneHelper.cs"
        scene_path_escaped = scene_path.replace("\\", "/")

        script_content = f"""\
using UnityEditor;
using UnityEditor.SceneManagement;

public class OpenSceneHelper {{
    [MenuItem("OpenGuard/OpenScene")]
    public static void OpenScene() {{
        EditorSceneManager.OpenScene("{scene_path_escaped}");
    }}
}}
"""
        script_file.write_text(script_content, encoding="utf-8")
        self._emit("unity_launcher", "running", f"打开场景：{scene_path}（等待 Unity 检测到新脚本…）")

        # 等待 Unity 检测到新 .cs 文件并开始编译（检测日志中的 Compilation 信号，最多 15s）
        compile_start = _tail_log_until(
            self._log_path,
            [r"Compilation started", r"Compiling", r"Refreshing native plugins", r"Reloading"],
            timeout=15.0,
            crash_patterns=_CRASH_PATTERNS,
            start_offset=self._log_start_offset,
        )
        if compile_start.abort_reason == "crash":
            self._cleanup_scene_helper_script(script_dir)
            return {"ok": False, "error": f"写入脚本后 Unity 崩溃：{compile_start.abort_line}"}
        if compile_start.timed_out:
            # Unity 没有检测到文件变化（可能是文件监视延迟或权限问题），继续等场景加载
            self._emit("unity_launcher", "warn",
                       "未检测到编译开始信号（可能 Unity 已跳过编译），继续等待场景加载…")
        if compile_start.matched:
            if self._log_path and self._log_path.exists():
                self._log_start_offset = self._log_path.stat().st_size

        # 等待场景加载完成
        r = _tail_log_until(
            self._log_path,
            [r"Loaded scene", r"Finished loading", r"Entered Play Mode"],
            timeout=30,
            crash_patterns=_CRASH_PATTERNS,
            progress_patterns=_EDITOR_PROGRESS_PATTERNS,
            start_offset=self._log_start_offset,
        )
        if self._log_path and self._log_path.exists():
            self._log_start_offset = self._log_path.stat().st_size

        self._cleanup_scene_helper_script(script_dir)

        if r.abort_reason == "crash":
            return {"ok": False, "error": f"打开场景时 Unity 崩溃：{r.abort_line}"}
        if r.timed_out:
            return {"ok": False, "error": f"场景加载超时（>30s）：{r.timeout_detail()}"}

        return {"ok": True}

    def _cleanup_scene_helper_script(self, script_dir: Path) -> None:
        """清理临时场景打开脚本（避免污染项目）。"""
        try:
            import shutil
            shutil.rmtree(script_dir, ignore_errors=True)
            meta = script_dir.with_suffix(".meta")
            if meta.exists():
                meta.unlink(missing_ok=True)
        except Exception:
            pass

    def _enter_playmode(self) -> dict[str, Any]:
        """等待 PlayMode 就绪。

        策略（方案4）：
        - Bridge 在 PlayMode 状态变化时更新 status.json
        - Python 轮询 status.json.is_playing，不依赖日志
        - 同时检测进程存活，进程死亡立即报错
        """
        from openguard.engines.unity.installer import UnityInstaller

        installer      = UnityInstaller(self.project_root)
        timeout        = self.playmode_timeout
        elapsed_report = 0.0

        self._emit("unity_launcher", "running",
                   f"等待 PlayMode 就绪（超时 {timeout:.0f}s）…")

        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            elapsed = time.monotonic() - (deadline - timeout)

            # ── 进程存活检测 ──────────────────────────────────────────────────
            proc = self._proc or self._reused_proc
            if proc is not None and not _is_process_alive(proc):
                return {
                    "ok": False,
                    "error": (
                        f"Unity Editor 进程在等待 PlayMode 时退出（已等 {elapsed:.0f}s）。"
                        "可能原因：游戏启动脚本报错导致崩溃。"
                    ),
                }

            # ── 读取 Bridge 状态 ──────────────────────────────────────────────
            status = installer.read_status()
            if status.get("is_playing"):
                self._emit("unity_launcher", "info",
                           f"PlayMode 已就绪（耗时 {elapsed:.0f}s）")
                return {"ok": True}

            # ── 定期进度报告 ──────────────────────────────────────────────────
            if elapsed - elapsed_report >= 15.0:
                elapsed_report = elapsed
                self._emit("unity_launcher", "running",
                           f"等待 PlayMode 中（已等 {elapsed:.0f}s）…")

            time.sleep(0.5)

        return {
            "ok": False,
            "error": (
                f"PlayMode 启动超时（>{timeout:.0f}s）。\n"
                "可能原因：游戏初始化时间过长、场景配置错误或登录逻辑异常。\n"
                f"提示：可在 config.yaml 中增大 runtime.playmode_timeout_seconds（当前 {timeout:.0f}s）。"
            ),
        }

    def _emit(self, step: str, status: str, message: str) -> None:
        try:
            self.event_sink(step, status, message)
        except Exception:
            pass



# ──────────────────────────────────────────────────────────────────────────────
# 便捷函数：从 config + test_knowledge 读取就绪状态（供 preflight 使用）
# ──────────────────────────────────────────────────────────────────────────────

def check_unity_config(config: dict[str, Any]) -> dict[str, Any]:
    """校验 Unity 启动器所需配置是否完整，返回 {"ok": bool, "missing": [...]}。

    路径解析优先级与 _launch_editor 保持一致：
    1. config 中 runtime.unity_editor_path（显式配置）
    2. find_unity_editors() 自动发现（未配置时）
    """
    from openguard.tools.runtime.process import check_executable
    from openguard.tools.runtime.unity import find_unity_editors

    runtime = config.get("runtime", {})
    missing = []

    unity_path = runtime.get("unity_editor_path", "")
    if unity_path:
        if not check_executable(unity_path):
            missing.append(f"runtime.unity_editor_path 不存在或不可执行：{unity_path}")
    else:
        # 未配置时尝试自动发现，发现不到才算缺失
        project_root = runtime.get("project_root", "")
        unity_version = runtime.get("unity_version")
        candidates = find_unity_editors(project_root, unity_version) if project_root else []
        if not candidates:
            missing.append(
                "runtime.unity_editor_path（未配置且本机未能自动发现 Unity Editor）"
            )

    return {"ok": len(missing) == 0, "missing": missing}
