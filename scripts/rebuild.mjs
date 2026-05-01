#!/usr/bin/env node
/**
 * rebuild.mjs — 重新打包 + 重新安装 OpenQA（本地开发用，跨平台）
 *
 * 用法（任意平台）：
 *   node scripts/rebuild.mjs           # pip + npm link（快速，日常开发）
 *   node scripts/rebuild.mjs --pack    # pip + npm pack + npm install -g（模拟真实发布）
 *   node scripts/rebuild.mjs --py-only # 只重装 Python 包
 *
 * 通过 pnpm 执行（需在根目录 package.json 里配置 scripts）：
 *   pnpm rebuild-dev
 *   pnpm rebuild-pack
 *   pnpm rebuild-py
 */

import { spawnSync } from 'child_process';
import { readdirSync, unlinkSync, existsSync } from 'fs';
import { resolve, dirname, join } from 'path';
import { fileURLToPath } from 'url';
import os from 'os';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');
const NPM_DIR = join(ROOT, 'npm');
const IS_WIN = os.platform() === 'win32';

// ── 参数解析 ──────────────────────────────────────────────────────────────────
const args = process.argv.slice(2);
const PACK    = args.includes('--pack');
const PY_ONLY = args.includes('--py-only');

// ── 彩色输出（不依赖任何 npm 包）────────────────────────────────────────────
const c = {
  cyan:  (s) => `\x1b[36m${s}\x1b[0m`,
  green: (s) => `\x1b[32m${s}\x1b[0m`,
  red:   (s) => `\x1b[31m${s}\x1b[0m`,
  yellow:(s) => `\x1b[33m${s}\x1b[0m`,
  bold:  (s) => `\x1b[1m${s}\x1b[0m`,
};

function step(msg)  { console.log('\n' + c.cyan(c.bold(`==> ${msg}`))); }
function ok(msg)    { console.log(c.green(`  [OK] ${msg}`)); }
function fail(msg)  { console.error(c.red(`  [FAIL] ${msg}`)); }
function info(msg)  { console.log(`  ${msg}`); }

// ── 执行命令工具 ─────────────────────────────────────────────────────────────
// Windows 上 npm/pnpm 等包管理器是 .cmd 文件，直接加后缀避免 shell:true
// Python 本身是 .exe，不需要此处理
function npmCmd(cmd) {
  return IS_WIN ? `${cmd}.cmd` : cmd;
}

// Windows 上 npm/pnpm/openqa 均为批处理 .cmd 或 shim，必须通过 shell 执行
// 参数为硬编码常量（非用户输入），安全无虞
// Node 25 中 shell:true + 数组参数会有 DEP0190 警告，改用字符串拼接规避
function run(cmd, args, opts = {}) {
  const cmdStr = IS_WIN ? [cmd, ...args].join(' ') : cmd;
  const argsArr = IS_WIN ? [] : args;
  const result = spawnSync(cmdStr, argsArr, {
    stdio: 'inherit',
    shell: IS_WIN,
    cwd: opts.cwd || ROOT,
    env: process.env,
    ...opts,
  });
  if (result.error) throw result.error;
  return result.status ?? 1;
}

function runCapture(cmd, args, opts = {}) {
  const cmdStr = IS_WIN ? [cmd, ...args].join(' ') : cmd;
  const argsArr = IS_WIN ? [] : args;
  const result = spawnSync(cmdStr, argsArr, {
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: IS_WIN,
    encoding: 'utf8',
    cwd: opts.cwd || ROOT,
    env: process.env,
    ...opts,
  });
  return {
    status: result.status ?? 1,
    stdout: result.stdout || '',
    stderr: result.stderr || '',
  };
}

// runDirect: python 等原生 .exe（不需要 shell，参数安全）
function runDirect(cmd, args, opts = {}) {
  const result = spawnSync(cmd, args, {
    stdio: 'inherit',
    shell: false,
    cwd: opts.cwd || ROOT,
    env: process.env,
    ...opts,
  });
  if (result.error) throw result.error;
  return result.status ?? 1;
}

function runDirectCapture(cmd, args, opts = {}) {
  const result = spawnSync(cmd, args, {
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: false,
    encoding: 'utf8',
    cwd: opts.cwd || ROOT,
    env: process.env,
    ...opts,
  });
  return {
    status: result.status ?? 1,
    stdout: result.stdout || '',
    stderr: result.stderr || '',
  };
}

// ── 检测 python / python3 命令 ───────────────────────────────────────────────
function findPython() {
  for (const cmd of ['python3', 'python', 'py']) {
    const r = runDirectCapture(cmd, ['--version']);
    if (r.status === 0) {
      const ver = (r.stdout + r.stderr).match(/Python (\d+)\.(\d+)/);
      if (ver && (parseInt(ver[1]) > 3 || (parseInt(ver[1]) === 3 && parseInt(ver[2]) >= 10))) {
        return cmd;
      }
    }
  }
  return null;
}

// ── Step 1: 重新安装 Python 包（editable）────────────────────────────────────
step('Reinstalling Python package (editable mode)');

const python = findPython();
if (!python) {
  fail('Python 3.10+ not found. Install from https://www.python.org/downloads/');
  process.exit(1);
}

// 忽略 pip PATH 警告，用 --no-warn-script-location
const pipStatus = runDirect(python, ['-m', 'pip', 'install', '-e', '.[dev]',
  '--quiet', '--no-warn-script-location'], { cwd: ROOT });
if (pipStatus !== 0) {
  fail(`pip install failed (exit ${pipStatus})`);
  process.exit(1);
}
ok('pip install -e .[dev] done');

if (PY_ONLY) {
  console.log('\n' + c.yellow('Python-only reinstall complete.'));
  process.exit(0);
}

// ── Step 2: npm 包安装 ────────────────────────────────────────────────────────
if (PACK) {
  // 完整模拟：npm pack + npm install -g
  step('Packing npm tgz');

  // 清理旧 tgz
  if (existsSync(NPM_DIR)) {
    readdirSync(NPM_DIR)
      .filter(f => f.endsWith('.tgz'))
      .forEach(f => unlinkSync(join(NPM_DIR, f)));
  }

  const packResult = runCapture('npm', ['pack'], { cwd: NPM_DIR });
  if (packResult.status !== 0) {
    fail('npm pack failed:\n' + packResult.stderr);
    process.exit(1);
  }

  // npm pack 最后一行是生成的文件名
  const tgzFile = packResult.stdout.trim().split('\n').pop().trim();
  const tgzPath = join(NPM_DIR, tgzFile);
  ok(`Packed: ${tgzFile}`);

  step(`npm install -g ${tgzFile}`);
  const installStatus = run('npm', ['install', '-g', tgzPath]);
  if (installStatus !== 0) {
    fail('npm install -g failed');
    process.exit(1);
  }
  ok('npm install -g done');

} else {
  // 快速模式：npm link
  step('npm link (fast mode for local dev)');
  const linkStatus = run('npm', ['link', '--force'], { cwd: NPM_DIR });
  if (linkStatus !== 0) {
    fail('npm link failed');
    process.exit(1);
  }
  ok('npm link done');
}

// ── Step 3: 验证 ─────────────────────────────────────────────────────────────
step('Verifying');
const verResult = runCapture('openqa', ['--version']);
if (verResult.status === 0) {
  ok(`openqa is available: ${(verResult.stdout + verResult.stderr).trim()}`);
} else {
  fail('openqa command not found after install.');
  info('Make sure npm global bin directory is in PATH.');
  info('Run: npm config get prefix');
  process.exit(1);
}

// ── 完成 ──────────────────────────────────────────────────────────────────────
console.log('\n' + c.green(c.bold('Rebuild complete!')));
console.log('  cd your-project');
console.log('  openqa init');
