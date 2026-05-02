//
// OpenGuard Bridge — 常驻脚本，由 openguard init 安装，请勿手动删除。
//
// 通信文件（openguard/runtime/ 目录）：
//
//   status.json    Bridge 主动写入，Python 只读
//                  格式：{"ready":true,"is_playing":false,"is_compiling":false,"version":"1"}
//                  写入时机：[InitializeOnLoad] 触发后（表示 Bridge 已就绪）
//                            PlayMode 状态变化时更新
//
//   request.json   Python 写 → Bridge 读后删除 → 执行命令 → 写 response.json
//   response.json  Bridge 写 → Python 读后删除
//
// 支持的命令（cmd）：
//   ping               健康检查
//   get_status         返回当前状态（同 status.json 内容）
//   enter_playmode     进入 PlayMode
//   exit_playmode      退出 PlayMode
//   open_scene         打开场景，args: {"scene": "Assets/Scenes/Login.unity"}
//
using System;
using System.IO;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public class _OpenGuardBridge
{
    // ── 路径 ─────────────────────────────────────────────────────────────────

    private static readonly string RuntimeDir;
    private static readonly string RequestPath;
    private static readonly string ResponsePath;
    private static readonly string StatusPath;

    static _OpenGuardBridge()
    {
        string projectRoot = Path.GetFullPath(
            Path.Combine(Application.dataPath, ".."));
        RuntimeDir   = Path.Combine(projectRoot, "openguard", "runtime");
        RequestPath  = Path.Combine(RuntimeDir, "request.json");
        ResponsePath = Path.Combine(RuntimeDir, "response.json");
        StatusPath   = Path.Combine(RuntimeDir, "status.json");

        // 立即写入状态：Bridge 已就绪（Python 轮询此文件判断 Unity 就绪）
        WriteStatus();

        // 监听 PlayMode 状态变化
        EditorApplication.playModeStateChanged += OnPlayModeStateChanged;

        // 开始轮询请求
        EditorApplication.update += PollRequest;

        UnityEngine.Debug.Log("[OpenGuard] Bridge 已就绪，等待请求…");
    }

    // ── 状态管理（主动推送）──────────────────────────────────────────────────

    private static void WriteStatus()
    {
        try
        {
            Directory.CreateDirectory(RuntimeDir);
            bool playing   = EditorApplication.isPlaying;
            bool compiling = EditorApplication.isCompiling;
            string json = $"{{\"ready\":true,"
                        + $"\"is_playing\":{B(playing)},"
                        + $"\"is_compiling\":{B(compiling)},"
                        + $"\"version\":\"1\"}}";
            // 使用不带 BOM 的 UTF-8（避免 Python 解析问题）
            var encoding = new System.Text.UTF8Encoding(false);
            File.WriteAllText(StatusPath, json, encoding);
        }
        catch (Exception e)
        {
            UnityEngine.Debug.LogWarning($"[OpenGuard] 写 status.json 失败: {e.Message}");
        }
    }

    private static void OnPlayModeStateChanged(PlayModeStateChange state)
    {
        // PlayMode 任何状态变化都更新 status.json
        WriteStatus();
        UnityEngine.Debug.Log($"[OpenGuard] PlayMode 状态变化: {state} "
            + $"is_playing={EditorApplication.isPlaying}");
    }

    // ── 请求轮询（每帧）─────────────────────────────────────────────────────

    private static void PollRequest()
    {
        if (!File.Exists(RequestPath))
            return;

        string json;
        try
        {
            json = File.ReadAllText(RequestPath, System.Text.Encoding.UTF8);
            File.Delete(RequestPath);
        }
        catch { return; }

        try
        {
            var req  = JsonDict.Parse(json);
            string id  = req.GetStr("id",  "");
            string cmd = req.GetStr("cmd", "");
            var    args = req.GetDict("args");
            UnityEngine.Debug.Log($"[OpenGuard] 请求: id={id} cmd={cmd}");
            Dispatch(id, cmd, args);
        }
        catch (Exception e)
        {
            WriteResponse("", false, null, $"解析请求失败: {e.Message}");
        }
    }

    // ── 命令分发 ─────────────────────────────────────────────────────────────

    private static void Dispatch(string id, string cmd, JsonDict args)
    {
        switch (cmd)
        {
            case "ping":
                WriteResponse(id, true, "{\"pong\":true}", null);
                break;

            case "get_status":
                WriteResponse(id, true,
                    $"{{\"is_playing\":{B(EditorApplication.isPlaying)},"
                    + $"\"is_compiling\":{B(EditorApplication.isCompiling)}}}",
                    null);
                break;

            case "enter_playmode":
                HandleEnterPlayMode(id);
                break;

            case "exit_playmode":
                HandleExitPlayMode(id);
                break;

            case "open_scene":
                HandleOpenScene(id, args.GetStr("scene", ""));
                break;

            default:
                WriteResponse(id, false, null, $"未知命令: {cmd}");
                break;
        }
    }

    // ── 命令实现 ─────────────────────────────────────────────────────────────

    private static void HandleEnterPlayMode(string id)
    {
        if (EditorApplication.isPlaying)
        {
            WriteResponse(id, true, "{\"state\":\"already_playing\"}", null);
            return;
        }
        if (EditorApplication.isCompiling)
        {
            var pendingId = id;
            EditorApplication.CallbackFunction fn = null;
            fn = () => {
                if (EditorApplication.isCompiling) return;
                EditorApplication.update -= fn;
                EditorApplication.isPlaying = true;
                WriteResponse(pendingId, true, "{\"state\":\"entering\"}", null);
            };
            EditorApplication.update += fn;
            return;
        }
        EditorApplication.isPlaying = true;
        WriteResponse(id, true, "{\"state\":\"entering\"}", null);
    }

    private static void HandleExitPlayMode(string id)
    {
        if (!EditorApplication.isPlaying)
        {
            WriteResponse(id, true, "{\"state\":\"already_stopped\"}", null);
            return;
        }
        EditorApplication.isPlaying = false;
        WriteResponse(id, true, "{\"state\":\"exiting\"}", null);
    }

    private static void HandleOpenScene(string id, string scenePath)
    {
        if (string.IsNullOrEmpty(scenePath))
        {
            WriteResponse(id, false, null, "open_scene: args.scene 不能为空");
            return;
        }
        try
        {
            UnityEditor.SceneManagement.EditorSceneManager.OpenScene(scenePath);
            WriteResponse(id, true, $"{{\"scene\":\"{Esc(scenePath)}\"}}", null);
        }
        catch (Exception e)
        {
            WriteResponse(id, false, null, $"打开场景失败: {e.Message}");
        }
    }

    // ── 响应写入 ─────────────────────────────────────────────────────────────

    private static void WriteResponse(string id, bool ok, string dataJson, string error)
    {
        try
        {
            Directory.CreateDirectory(RuntimeDir);
            string errStr  = error != null ? $"\"{Esc(error)}\"" : "null";
            string dataStr = dataJson ?? "null";
            string json = $"{{\"id\":\"{Esc(id)}\","
                        + $"\"ok\":{B(ok)},"
                        + $"\"data\":{dataStr},"
                        + $"\"error\":{errStr}}}";
            File.WriteAllText(ResponsePath, json, System.Text.Encoding.UTF8);
        }
        catch (Exception e)
        {
            UnityEngine.Debug.LogError($"[OpenGuard] 写响应失败: {e.Message}");
        }
    }

    // ── 辅助 ─────────────────────────────────────────────────────────────────

    private static string B(bool v) => v ? "true" : "false";

    private static string Esc(string s)
    {
        if (s == null) return "";
        return s.Replace("\\", "\\\\")
                .Replace("\"", "\\\"")
                .Replace("\n", "\\n")
                .Replace("\r", "\\r");
    }

    // ── 极简 JSON 解析 ───────────────────────────────────────────────────────

    private struct JsonDict
    {
        private readonly string _raw;
        private JsonDict(string raw) { _raw = raw ?? ""; }
        public static JsonDict Parse(string json) => new JsonDict(json);

        public string GetStr(string key, string def)
        {
            int ki = _raw.IndexOf($"\"{key}\"", StringComparison.Ordinal);
            if (ki < 0) return def;
            int colon = _raw.IndexOf(':', ki);
            if (colon < 0) return def;
            int pos = colon + 1;
            while (pos < _raw.Length && char.IsWhiteSpace(_raw[pos])) pos++;
            if (pos >= _raw.Length || _raw[pos] != '"') return def;
            int q2 = _raw.IndexOf('"', pos + 1);
            if (q2 < 0) return def;
            return _raw.Substring(pos + 1, q2 - pos - 1);
        }

        public JsonDict GetDict(string key)
        {
            int ki = _raw.IndexOf($"\"{key}\"", StringComparison.Ordinal);
            if (ki < 0) return new JsonDict("{}");
            int brace = _raw.IndexOf('{', ki);
            if (brace < 0) return new JsonDict("{}");
            int depth = 0, end = brace;
            for (int i = brace; i < _raw.Length; i++)
            {
                if (_raw[i] == '{') depth++;
                else if (_raw[i] == '}') { depth--; if (depth == 0) { end = i; break; } }
            }
            return new JsonDict(_raw.Substring(brace, end - brace + 1));
        }
    }
}
