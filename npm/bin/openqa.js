#!/usr/bin/env node
/**
 * OpenQA CLI 入口（npm 包壳）
 *
 * 定位本机 Python 环境中安装的 openqa 可执行文件，
 * 将所有参数透传给它。
 *
 * 查找顺序：
 *   1. postinstall 写入的 .openqa-python-path（记录了安装时使用的 pip 路径）
 *   2. PATH 中的 openqa 命令（pip install --user 或系统级安装）
 *   3. 常见 pip scripts 目录（兜底）
 */

import { spawnSync } from 'child_process';
import { existsSync, readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import os from 'os';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PKG_ROOT = dirname(__dirname);

// ─── 1. 读取 postinstall 记录的安装路径 ───────────────────────────────────────
let cachedPythonPath = null;
const cachePath = join(PKG_ROOT, '.openqa-python-path');
if (existsSync(cachePath)) {
  try {
    cachedPythonPath = readFileSync(cachePath, 'utf8').trim();
  } catch {}
}

// ─── 2. 查找 openqa 可执行文件 ────────────────────────────────────────────────
function findOpenqaExecutable() {
  // 2a. 使用 postinstall 记录的 Python 解释器路径，推导 scripts 目录
  if (cachedPythonPath && existsSync(cachedPythonPath)) {
    const pythonDir = dirname(cachedPythonPath);
    const candidates = [
      join(pythonDir, 'openqa'),
      join(pythonDir, 'openqa.exe'),
      join(pythonDir, 'Scripts', 'openqa'),
      join(pythonDir, 'Scripts', 'openqa.exe'),
    ];
    for (const c of candidates) {
      if (existsSync(c)) return { exe: c, args: [] };
    }
    // 用记录的 Python 解释器通过 -m 方式运行
    return { exe: cachedPythonPath, args: ['-m', 'openqa.cli.main'] };
  }

  // 2b. PATH 中直接查找
  const which = spawnSync(os.platform() === 'win32' ? 'where' : 'which', ['openqa'], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'ignore'],
  });
  if (which.status === 0) {
    const p = which.stdout.split(/\r?\n/)[0].trim();
    if (p && existsSync(p)) return { exe: p, args: [] };
  }

  // 2c. 常见兜底路径
  const home = os.homedir();
  const fallbacks = os.platform() === 'win32'
    ? [
        join(home, 'AppData', 'Local', 'Programs', 'Python', 'Scripts', 'openqa.exe'),
        join(home, 'AppData', 'Roaming', 'Python', 'Scripts', 'openqa.exe'),
        'C:\\Python3\\Scripts\\openqa.exe',
        'C:\\Python311\\Scripts\\openqa.exe',
        'C:\\Python312\\Scripts\\openqa.exe',
      ]
    : [
        join(home, '.local', 'bin', 'openqa'),
        '/usr/local/bin/openqa',
        '/usr/bin/openqa',
      ];

  for (const p of fallbacks) {
    if (existsSync(p)) return { exe: p, args: [] };
  }

  return null;
}

// ─── 3. 找不到时引导用户 ──────────────────────────────────────────────────────
function printInstallGuide() {
  console.error('\n[openqa] 未找到 openqa Python 包。');
  console.error('\n请手动安装：');
  console.error('  pip install openqa-agent');
  console.error('  # 或');
  console.error('  pip install --user openqa-agent');
  console.error('\n安装后重新运行命令，或重新执行：');
  console.error('  npm install -g @fission-ai/openqa\n');
}

// ─── 4. 执行 ──────────────────────────────────────────────────────────────────
const found = findOpenqaExecutable();

if (!found) {
  printInstallGuide();
  process.exit(1);
}

const { exe, args: prefixArgs } = found;
const userArgs = process.argv.slice(2);

const result = spawnSync(exe, [...prefixArgs, ...userArgs], {
  stdio: 'inherit',
  shell: false,
  env: process.env,
  // 将工作目录设置为调用者的 cwd，而不是 npm 包目录
  cwd: process.cwd(),
});

// 透传退出码
process.exit(result.status ?? 1);
