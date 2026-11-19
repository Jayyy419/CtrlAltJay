#!/usr/bin/env node
// Claude Code hook for the Upkeep lamp. It reads the hook event on stdin and
// records the session's state and how many prompts it has had:
//   on the Mac   -> a small file in ~/.upkeep-lamp/sessions, read by the lamplighter
//                   (which can forward it to Upkeep for the project's history)
//   in the cloud -> a POST to Upkeep, which the lamplighter polls
// Prompts and output are never recorded, only states, times and the count.
// It always exits 0 and never prints, so it can't block or clutter a session.
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import { basename, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const cloudOnly = process.argv.includes('--cloud-only');
const remote = process.env.CLAUDE_CODE_REMOTE === 'true';

export function stateFor(event) {
  const name = event.hook_event_name;
  const tool = event.tool_name;
  const kind = event.notification_type;
  switch (name) {
    case 'UserPromptSubmit':
      return 'working';
    case 'PreToolUse':
      return tool === 'AskUserQuestion' ? 'question' : 'working';
    case 'PostToolUse':
    case 'PostToolUseFailure':
      return 'working';
    case 'PermissionRequest':
      return 'permission';
    case 'Notification':
      if (kind === 'permission_prompt') return 'permission';
      if (kind === 'elicitation_dialog' || kind === 'agent_needs_input') return 'question';
      return null;
    case 'Stop':
      return 'done';
    case 'StopFailure':
      return 'failed';
    case 'SessionEnd':
      return 'ended';
    default:
      return null;
  }
}

function readStdin(ms = 1500) {
  return new Promise((resolve) => {
    let text = '';
    const timer = setTimeout(() => resolve(text), ms);
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (c) => (text += c));
    process.stdin.on('end', () => {
      clearTimeout(timer);
      resolve(text);
    });
    process.stdin.on('error', () => resolve(text));
  });
}

const hash = (s) => createHash('sha256').update(String(s)).digest('hex');

function readJsonFile(file) {
  try {
    return JSON.parse(readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
}

// An ended session is kept as "ended" so the lamplighter can pass that on,
// then it removes the file.
export function writeLocal(session, state, label, turn, dir = join(homedir(), '.upkeep-lamp', 'sessions')) {
  mkdirSync(dir, { recursive: true, mode: 0o700 });
  const file = join(dir, `${hash(session).slice(0, 32)}.json`);
  const prev = readJsonFile(file);
  const turns = (prev?.turns ?? 0) + (turn ? 1 : 0);
  const tmp = `${file}.${process.pid}.tmp`;
  writeFileSync(tmp, JSON.stringify({ state, label: label ?? prev?.label ?? null, turns, at: Date.now() }), { mode: 0o600 });
  renameSync(tmp, file);
}

async function sendCloud(session, state, label, turn) {
  const base = process.env.UPKEEP_LAMP_URL;
  if (!base || !/^https:\/\//.test(base)) return;
  // Only changes are sent, to keep Upkeep's function calls low.
  const memo = join(tmpdir(), `upkeep-lamp-${hash(session).slice(0, 16)}`);
  const last = readJsonFile(memo) ?? { state: '', turns: 0 };
  const turns = last.turns + (turn ? 1 : 0);
  if (last.state === state && turns === last.turns) return;
  // The X-Upkeep-Key header is added by the cloud network proxy for this host.
  const body = JSON.stringify({ session, state: state === 'ended' ? 'done' : state, label, ended: state === 'ended', turns, source: 'cloud' });
  const res = await fetch(new URL('/api/lamp/report', base), {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-amz-content-sha256': createHash('sha256').update(body).digest('hex') },
    body,
    signal: AbortSignal.timeout(3000),
  });
  if (res.ok) writeFileSync(memo, JSON.stringify({ state, turns }));
}

async function main() {
  if (cloudOnly && !remote) return;
  let event;
  try {
    event = JSON.parse(await readStdin());
  } catch {
    return;
  }
  const state = stateFor(event);
  const session = event.session_id;
  if (!state || !session) return;
  const label = event.cwd ? basename(event.cwd).slice(0, 60) : null;
  const turn = event.hook_event_name === 'UserPromptSubmit';
  if (remote) await sendCloud(session, state, label, turn);
  else writeLocal(session, state, label, turn);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  main()
    .catch(() => {})
    .finally(() => process.exit(0));
}
