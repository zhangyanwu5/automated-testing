//
// OpenGuard Runtime Bridge — 常驻脚本，由 openguard init 安装，请勿手动删除。
//
// 双向通信协议（openguard/runtime/ 目录）：
//   request.json   Python 写，本脚本读取后立即删除，处理完毕后写 response.json
//   response.json  本脚本写，Python 读取后删除
//
// request.json 格式：
//   { "id": "req-001", "cmd": "enter_playmode", "args": {} }
//
// response.json 格式：
//   { "id": "req-001", "ok": true, "data": {}, "error": null }
//
// 支持的命令（cmd）：
//   enter_playmode   进入 PlayMode
//   exit_playmode    退出 PlayMode
//   get_status       返回当前 Editor 状态
//
using System;
using System.IO;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public class _OpenGuardBridge
{
    private static readonly string RuntimeDir;
    private static readonly string RequestPath;
    private static readonly string ResponsePath;

    static _OpenGuardBridge()
    {
        string projectRoot = Path.GetFullPath(
            Path.Combine(Application.dataPath, ".."));
        RuntimeDir   = Path.Combine(projectRoot, "openguard", "runtime");
        RequestPath  = Path.Combine(RuntimeDir, "request.json");
        ResponsePath = Path.Combine(RuntimeDir, "response.json");

        EditorApplication.update += PollRequest;
        UnityEngine.Debug.Log("[OpenGuard] Bridge 已就绪，等待请求…");
    }

    // ── 请求轮询（每帧调用）──────────────────────────────────────────────────

    private static void PollRequest()
    {
        if (!File.Exists(RequestPath))
            return;

        // 读取后立即删除，避免重复处理
        string json;
        try
        {
            json = File.ReadAllText(RequestPath, System.Text.Encoding.UTF8);
            File.Delete(RequestPath);
        }
        catch { return; } // 文件被占用，下一帧重试

        // 解析并执行命令
        try
        {
            var req = SimpleJson.Parse(json);
            string id  = req.GetString("id",  "");
            string cmd = req.GetString("cmd", "");

            UnityEngine.Debug.Log($"[OpenGuard] 收到请求: id={id} cmd={cmd}");
            ExecuteCommand(id, cmd, req);
        }
        catch (Exception e)
        {
            WriteResponse("", false, null, $"解析请求失败: {e.Message}");
        }
    }

    // ── 命令执行 ─────────────────────────────────────────────────────────────

    private static void ExecuteCommand(string id, string cmd, SimpleJson req)
    {
        switch (cmd)
        {
            case "enter_playmode":
                HandleEnterPlayMode(id);
                break;

            case "exit_playmode":
                HandleExitPlayMode(id);
                break;

            case "get_status":
                HandleGetStatus(id);
                break;

            default:
                WriteResponse(id, false, null, $"未知命令: {cmd}");
                break;
        }
    }

    private static void HandleEnterPlayMode(string id)
    {
        if (EditorApplication.isPlaying)
        {
            WriteResponse(id, true,
                "{\"state\":\"already_playing\"}",
                null);
            return;
        }
        if (EditorApplication.isCompiling)
        {
            // 等编译完再进入，通过延迟回调实现
            EditorApplication.update += MakeWaitCompileThenPlay(id);
            return;
        }
        UnityEngine.Debug.Log("[OpenGuard] enter_playmode: 进入 PlayMode");
        EditorApplication.isPlaying = true;
        WriteResponse(id, true, "{\"state\":\"entering\"}", null);
    }

    private static EditorApplication.CallbackFunction MakeWaitCompileThenPlay(string id)
    {
        EditorApplication.CallbackFunction fn = null;
        fn = () =>
        {
            if (EditorApplication.isCompiling) return;
            EditorApplication.update -= fn;
            UnityEngine.Debug.Log("[OpenGuard] 编译完成，进入 PlayMode");
            EditorApplication.isPlaying = true;
            WriteResponse(id, true, "{\"state\":\"entering\"}", null);
        };
        return fn;
    }

    private static void HandleExitPlayMode(string id)
    {
        if (!EditorApplication.isPlaying)
        {
            WriteResponse(id, true, "{\"state\":\"already_stopped\"}", null);
            return;
        }
        UnityEngine.Debug.Log("[OpenGuard] exit_playmode: 退出 PlayMode");
        EditorApplication.isPlaying = false;
        WriteResponse(id, true, "{\"state\":\"exiting\"}", null);
    }

    private static void HandleGetStatus(string id)
    {
        bool playing   = EditorApplication.isPlaying;
        bool compiling = EditorApplication.isCompiling;
        string data = $"{{\"is_playing\":{(playing?"true":"false")},"
                    + $"\"is_compiling\":{(compiling?"true":"false")}}}";
        WriteResponse(id, true, data, null);
    }

    // ── 写响应 ───────────────────────────────────────────────────────────────

    private static void WriteResponse(string id, bool ok, string dataJson, string error)
    {
        try
        {
            Directory.CreateDirectory(RuntimeDir);
            string errorStr  = error  != null ? $"\"{EscapeJson(error)}\"" : "null";
            string dataStr   = dataJson ?? "null";
            string json = $"{{\"id\":\"{EscapeJson(id)}\","
                        + $"\"ok\":{(ok ? "true" : "false")},"
                        + $"\"data\":{dataStr},"
                        + $"\"error\":{errorStr}}}";
            File.WriteAllText(ResponsePath, json, System.Text.Encoding.UTF8);
            UnityEngine.Debug.Log($"[OpenGuard] 响应已写入: ok={ok} id={id}");
        }
        catch (Exception e)
        {
            UnityEngine.Debug.LogError($"[OpenGuard] 写响应失败: {e.Message}");
        }
    }

    private static string EscapeJson(string s)
    {
        if (s == null) return "";
        return s.Replace("\\", "\\\\").Replace("\"", "\\\"")
                .Replace("\n", "\\n").Replace("\r", "\\r");
    }

    // ── 极简 JSON 解析（避免依赖 Newtonsoft.Json）────────────────────────────

    private struct SimpleJson
    {
        private readonly string _raw;

        private SimpleJson(string raw) { _raw = raw; }

        public static SimpleJson Parse(string json) => new SimpleJson(json ?? "");

        public string GetString(string key, string def)
        {
            // 匹配 "key": "value"
            string pat = $"\"{key}\"";
            int ki = _raw.IndexOf(pat, StringComparison.Ordinal);
            if (ki < 0) return def;
            int colon = _raw.IndexOf(':', ki + pat.Length);
            if (colon < 0) return def;
            int q1 = _raw.IndexOf('"', colon + 1);
            if (q1 < 0) return def;
            int q2 = _raw.IndexOf('"', q1 + 1);
            if (q2 < 0) return def;
            return _raw.Substring(q1 + 1, q2 - q1 - 1);
        }
    }
}
