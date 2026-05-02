#!/usr/bin/env node
/**
 * postinstall.js
 *
 * npm install -g @fission-ai/openguard 后自动执行：
 *   1. 检测本机 Python（3.10+）
 *   2. pip install openguard-agent（来自 PyPI，或本地开发时从 src/ 安装）
 *   3. 将 Python 解释器路径写入 .openguard-python-path 供 bin/openguard.js 使用
 *
 * 设计原则：
 *   - 永远不会让 npm install 失败（所有错误都被捕获）
 *   - CI 环境（CI=true）跳过 pip install
 *   - 安装失败时打印清晰的手动安装指引
 */

import { spawnSync, execSync } from 'child_process';
import { writeFileSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import os from 'os';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PKG_ROOT = dirname(__dirname);
// PyPI 包名
const PYPI_PACKAGE = 'openguard-agent';
// 最低 Python 版本
const MIN_PYTHON_MAJOR = 3;
const MIN_PYTHON_MINOR = 10;

// ─── CI / opt-out 跳过 ────────────────────────────────────────────────────────
if (process.env.CI === 'true' || process.env.CI === '1' || process.env.OPENGUARD_NO_PYTHON === '1') {
  process.exit(0);
}

// ─── 工具函数 ─────────────────────────────────────────────────────────────────

/** 在 PATH 中查找可用的 Python 解释器，返回命令字符串或 null */
function findPython() {
  // Windows 上优先 py launcher，其次 python3 / python
  const candidates = os.platform() === 'win32'
    ? ['py', 'python3', 'python']
    : ['python3', 'python'];

  for (const cmd of candidates) {
    try {
      const result = spawnSync(cmd, ['--version'], { encoding: 'utf8', stdio: 'pipe' });
      if (result.status === 0) {
        const versionStr = (result.stdout || result.stderr || '').trim();
        const m = versionStr.match(/Python (\d+)\.(\d+)/);
        if (m) {
          const major = parseInt(m[1]);
          const minor = parseInt(m[2]);
          if (major > MIN_PYTHON_MAJOR || (major === MIN_PYTHON_MAJOR && minor >= MIN_PYTHON_MINOR)) {
            return cmd;
          }
        }
      }
    } catch {}
  }
  return null;
}

/** 获取 Python 解释器的完整路径（用于写入缓存） */
function getPythonFullPath(pythonCmd) {
  try {
    const result = spawnSync(
      pythonCmd,
      ['-c', 'import sys; print(sys.executable)'],
      { encoding: 'utf8', stdio: 'pipe' }
    );
    if (result.status === 0) return result.stdout.trim();
  } catch {}
  return pythonCmd;
}

/** 检查 openguard 是否已安装且版本可用 */
function isOpenguardInstalled(pythonCmd) {
  try {
    const result = spawnSync(
      pythonCmd,
      ['-c', 'import openguard; print("ok")'],
      { encoding: 'utf8', stdio: 'pipe' }
    );
    return result.status === 0 && result.stdout.includes('ok');
  } catch {}
  return false;
}

/** 用 pip 安装 openguard-agent */
function pipInstall(pythonCmd) {
  console.log(`\n[openguard] 正在安装 Python 包 ${PYPI_PACKAGE}…`);

  // 检查是否有本地 src/（开发模式）
  const localSrc = join(PKG_ROOT, '..', 'pyproject.toml');
  const installTarget = existsSync(localSrc)
    ? ['-e', join(PKG_ROOT, '..')] // 开发模式：从本地安装
    : [PYPI_PACKAGE];              // 生产模式：从 PyPI 安装

  const pipArgs = ['-m', 'pip', 'install', '--quiet', ...installTarget];

  const result = spawnSync(pythonCmd, pipArgs, {
    stdio: 'inherit',
    encoding: 'utf8',
  });

  return result.status === 0;
}

/** 将 Python 路径写入缓存文件 */
function writePythonPathCache(pythonPath) {
  try {
    writeFileSync(join(PKG_ROOT, '.openguard-python-path'), pythonPath, 'utf8');
  } catch {}
}

// ─── 主流程 ───────────────────────────────────────────────────────────────────

async function main() {
  console.log('\n[openguard] 检测 Python 环境…');

  // 1. 查找 Python
  const pythonCmd = findPython();
  if (!pythonCmd) {
    console.error('\n[openguard] 未找到 Python 3.10+。');
    console.error('请先安装 Python：https://www.python.org/downloads/');
    console.error('\n安装 Python 后，运行：');
    console.error('  pip install openguard-agent');
    console.error('  npm install -g @fission-ai/openguard\n');
    // 不让 npm install 失败
    return;
  }

  const pythonPath = getPythonFullPath(pythonCmd);
  console.log(`[openguard] 找到 Python：${pythonPath}`);

  // 2. 检查是否已安装
  if (isOpenguardInstalled(pythonCmd)) {
    console.log('[openguard] openguard Python 包已安装，跳过重复安装。');
    writePythonPathCache(pythonPath);
    printSuccess();
    return;
  }

  // 3. pip install
  const ok = pipInstall(pythonCmd);
  if (!ok) {
    console.error('\n[openguard] pip install 失败。请手动安装：');
    console.error(`  ${pythonCmd} -m pip install openguard-agent`);
    console.error('\n安装完成后直接运行 openguard 命令即可。\n');
    return;
  }

  // 4. 写缓存
  writePythonPathCache(pythonPath);
  printSuccess();
}

function printSuccess() {
  console.log('\n[openguard] 安装完成！');
  console.log('\n快速开始：');
  console.log('  cd your-project');
  console.log('  openguard init');
  console.log('  openguard new "验证某个功能"');
  console.log('  openguard continue');
  console.log('  openguard apply');
  console.log('  openguard archive\n');
}

main().catch((err) => {
  // 永远不让 npm install 失败
  console.error('[openguard] postinstall 发生意外错误（不影响安装）:', err.message);
  process.exit(0);
});
