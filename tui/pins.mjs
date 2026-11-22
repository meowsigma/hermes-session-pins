// Session Pins native user widget — public SDK only; no Hermes core imports.
import { execFile, execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { statSync } from 'node:fs';
import { performance } from 'node:perf_hooks';
import { homedir, platform } from 'node:os';
import { resolve, dirname, basename, isAbsolute } from 'node:path';

export const clean = value => String(value ?? '').replace(/[\p{C}]/gu, '').replace(/\s+/gu, ' ').trim();
export function matches(state) {
  const q = state.query.toLocaleLowerCase();
  return state.rows.filter(row => (state.all || row.pinned) && (!q || row.title.toLocaleLowerCase().includes(q) || row.id.includes(state.query)));
}
export function selected(state) {
  const rows = matches(state);
  return rows[Math.min(state.index, Math.max(0, rows.length - 1))];
}
export function copyCommand(row, action = 'resume') {
  const id = row?.id;
  // Do not rewrite an opaque key or pass option-like, numeric/menu or wrapped
  // identifiers into a different surface's parser. Refuse instead.
  if (typeof id !== 'string' || !id || /[\p{C}\s]/u.test(id) || id.startsWith('-') || /^\d+$/.test(id) || /^[<\["']/.test(id)) {
    throw new Error('This session ID cannot be copied safely. Use the full ID with the CLI.');
  }
  if (!['resume', 'pin', 'unpin'].includes(action)) throw new Error('Unknown command.');
  return `/${action} ${id}`;
}
export function age(stamp, now = Date.now()) {
  const seconds = Math.max(0, (now - Number(stamp) * 1000) / 1000);
  if (!Number.isFinite(seconds) || !stamp) return 'unknown time';
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

// Read metadata only. SQLite may commit to either the DB or its WAL; watching
// just state.db would keep stale pin/visibility/title results in WAL mode.
export function inventoryStamp(home) {
  try {
    const stamp = path => {
      try {
        const s = statSync(path, { bigint: true });
        return [s.dev, s.ino, s.size, s.mtimeNs, s.ctimeNs].join(':');
      } catch (error) {
        if (error.code === 'ENOENT' && path.endsWith('-wal')) return 'absent';
        throw error;
      }
    };
    return `${stamp(resolve(home, 'state.db'))}/${stamp(resolve(home, 'state.db-wal'))}`;
  } catch { return null; } // A failed check is a cache miss, never cached truth.
}

// One short-lived, profile-local entry, kept only in this widget registration.
// No disk cache, transcript previews, timers, startup prefetch or extra process.
export function inventoryCache(home, { now = () => performance.now(), stamp = inventoryStamp } = {}) {
  let entry;
  return {
    clear() { entry = undefined; },
    read() {
      if (!entry) return null;
      if (now() >= entry.expires || stamp(home) !== entry.stamp) {
        entry = undefined;
        return null;
      }
      return entry.rows.map(row => ({ ...row }));
    },
    store(rows, before) {
      entry = undefined;
      if (before === null || stamp(home) !== before) return;
      entry = { rows: rows.map(row => ({ ...row })), stamp: before, expires: now() + 30_000 };
    },
  };
}

// Frozen at registration: an ambient/profile change can never redirect a list
// or refresh. A response from a different home is rejected, not relabelled.
export default function register(sdk) {
  const { h, Box, Text, Dialog, Overlay, ShimmerRows, React } = sdk;
  const rawHome = process.env.HERMES_HOME || resolve(homedir(), '.hermes');
  const validHome = isAbsolute(rawHome) && rawHome === rawHome.trim() && !rawHome.includes('$') && !rawHome.startsWith('~');
  const home = resolve(rawHome);
  const profile = basename(dirname(home)) === 'profiles' ? [] : ['--profile', 'default'];
  const cache = inventoryCache(home);

  const children = new Map();
  const cancel = token => {
    const child = children.get(token);
    if (child) child.kill(); // Only this widget's exact child; never a host process.
    children.delete(token);
  };
  const cancelAll = () => { for (const token of children.keys()) cancel(token); };
  const land = (token, fn) => sdk.updateWidget(app, state => state.token === token ? fn(state) : state);
  function load(state, force = false) {
    if (!validHome || state.home !== home) {
      land(state.token, s => ({ ...s, rows: [], index: 0, loading: false, error: 'This profile home cannot round-trip safely.' }));
      return;
    }
    cancel(state.token);
    const cached = !force && cache.read();
    if (cached) {
      land(state.token, s => ({ ...s, rows: cached, loading: false, error: '' }));
      return;
    }
    cache.clear();
    // One cache decision owns both display validity and subprocess admission.
    // Never leave rows actionable after this load has rejected their cache.
    land(state.token, s => ({ ...s, rows: [], index: 0, loading: true, error: '' }));
    const before = inventoryStamp(home);
    const child = execFile('hermes', [...profile, 'pins', 'data'], {
      env: { ...process.env, HERMES_HOME: home, HERMES_DISABLE_LAZY_INSTALLS: '1' },
      timeout: 20000, maxBuffer: 32 * 1024 * 1024, encoding: 'utf8',
    }, (error, stdout) => {
      if (children.get(state.token) !== child) return;
      children.delete(state.token);
      try {
        if (error) throw new Error('Could not read chats. Check that Session Pins is enabled; Ctrl+R retries.');
        const data = JSON.parse(stdout);
        if (data.home !== home || !Array.isArray(data.rows)) throw new Error('Profile mismatch; refusing these chats.');
        const seen = new Set();
        const rows = data.rows.map(row => {
          if (!row || typeof row.id !== 'string' || !row.id || seen.has(row.id) || typeof row.title !== 'string') throw new Error('Invalid chat inventory.');
          seen.add(row.id);
          return { ...row, title: clean(row.title) || 'Untitled chat', model: clean(row.model) || 'model not recorded', pinned: Boolean(row.pinned) };
        });
        cache.store(rows, before);
        land(state.token, s => ({ ...s, rows, loading: false, error: '', index: Math.min(s.index, Math.max(0, matches({ ...s, rows }).length - 1)) }));
      } catch (err) { land(state.token, s => ({ ...s, rows: [], index: 0, loading: false, error: clean(err.message) })); }
    });
    children.set(state.token, child);
    child.stdin?.end();
  }
  function copy(state, action) {
    let command;
    try { command = copyCommand(selected(state), action); }
    catch (error) { return { ...state, error: error.message }; }
    // The public SDK closes through reduce() returning null, not an async
    // updateWidget(null). A short, bounded clipboard call lets that supported
    // close path run only after success. The backend agent keeps running.
    // No synthetic input, composer access or raw OSC writes to the renderer.
    const os = platform();
    if (os === 'win32') return { ...state, error: 'This preview needs a POSIX clipboard utility.' };
    if ((process.env.HERMES_HOME || resolve(homedir(), '.hermes')) !== rawHome) return { ...state, error: 'Profile changed. Close and reopen the picker.' };
    const executable = os === 'darwin' ? 'pbcopy' : process.env.WAYLAND_DISPLAY ? 'wl-copy' : 'xclip';
    const args = executable === 'xclip' ? ['-selection', 'clipboard'] : [];
    try {
      execFileSync(executable, args, { input: command, timeout: 1500, stdio: ['pipe', 'ignore', 'ignore'] });
      return null;
    } catch {
      return { ...state, error: 'Clipboard unavailable. Check your clipboard utility; Esc closes without a change.' };
    }
  }
  function View({ state, t, cols, rows }) {
    React.useEffect(() => () => cancel(state.token), [state.token]);
    if (cols < 40 || rows < 16) return h(Overlay, { backdrop: true }, h(Dialog, { width: Math.max(8, cols - 2) },
      h(Text, { color: t.color.muted, wrap: 'truncate-end' }, 'Enlarge terminal to 40×16; Esc closes.')));
    const width = Math.max(12, Math.min(112, cols - 4));
    const inner = Math.max(1, width - 6);
    const compact = rows < 26;
    const room = Math.max(1, Math.min(10, Math.floor((rows - (compact ? 14 : 17)) / (compact ? 1 : 2))));
    const filtered = matches(state);
    const index = Math.min(state.index, Math.max(0, filtered.length - 1));
    const start = Math.max(0, Math.min(index - Math.floor(room / 2), filtered.length - room));
    const row = filtered[index];
    const pinCount = state.rows.filter(r => r.pinned).length;
    const text = (value, props = {}) => h(Text, { color: t.color.muted, wrap: 'truncate-end', ...props }, value);
    return h(Overlay, { backdrop: true }, h(Dialog, { width },
      h(Box, { justifyContent: 'space-between', width: inner },
        text('Session Pins', { bold: true, color: t.color.primary }), text('Esc close')),
      h(Box, { gap: 3, marginTop: compact ? 0 : 1 },
        text(`Pinned ${pinCount}`, { bold: !state.all, color: !state.all ? t.color.primary : t.color.muted }),
        text(`All chats ${state.rows.length}`, { bold: state.all, color: state.all ? t.color.primary : t.color.muted }),
        text('Tab / ←→ switch')),
      h(Box, { marginTop: compact ? 0 : 1 }, text(`Search: ${state.query || 'type a title or ID…'}`, { color: state.query ? t.color.label : t.color.muted })),
      state.loading ? h(ShimmerRows, { rows: Math.min(3, room), width: Math.max(1, inner), t }) : h(Box, { flexDirection: 'column', marginTop: compact ? 0 : 1 },
        text(`${filtered.length} matching ${state.all ? 'chats' : 'pins'}${filtered.length ? ` · ${index + 1}/${filtered.length}` : ''}${start ? ` · ↑ ${start} above` : ''}`),
        ...filtered.slice(start, start + room).map((r, offset) => {
          const active = start + offset === index;
          const color = active ? t.color.primary : t.color.label;
          return h(Box, { key: r.id, flexDirection: 'column', width: inner, backgroundColor: active ? t.color.selectionBg : undefined },
            text(`${active ? '›' : ' '} ${r.pinned ? '★' : '·'} ${r.title}`, { bold: active, color }),
            !compact && text(`    ${r.model} · ${age(r.updated)}`));
        }),
        !filtered.length && text(state.query ? 'No matching chats. Backspace edits; Ctrl+U clears.' : state.all ? 'No visible chats yet.' : 'No visible pins. Tab browses all chats.'),
        start + room < filtered.length && text(`↓ ${filtered.length - start - room} more below`)),
      !compact && h(Box, { marginTop: 1 }, text(row ? `ID: ${clean(row.id)}` : 'ID: —')),
      state.error && text(state.error, { color: t.color.error }),
      h(Box, { marginTop: compact ? 0 : 1, flexDirection: 'column' },
        text(state.busy ? 'Copying…' : '↑↓ select · Enter copy resume · Ctrl+P copy pin/unpin'),
        text('Ctrl+R refresh · Esc close · then paste + Enter in this chat'),
        !compact && text('Stored model shown; no model changes. Copy actions do not open or pin a chat.')),
    ));
  }
  const app = sdk.defineWidgetApp({
    id: 'pins', help: '★ Native pinned-chat picker; Enter copies the resume command', mode: 'modal',
    init: arg => {
      cancelAll();
      const input = clean(arg);
      const cached = validHome ? cache.read() : null;
      return { token: randomUUID(), home, rows: cached ?? [], query: ['all', 'find', 'list', 'manage'].includes(input) ? '' : input,
        all: ['all', 'find'].includes(input), index: 0, loading: cached === null, busy: false, error: '' };
    },
    reduce: (state, { ch, key }) => {
      if (key.escape || sdk.isCtrl(key, ch, 'c')) { cancel(state.token); return null; }
      if (!validHome || state.home !== home) return { ...state, rows: [], index: 0, loading: false, error: 'This profile home cannot round-trip safely. Close and reopen the picker.' };
      if (state.busy) return state;
      if (sdk.isCtrl(key, ch, 'r')) { load(state, true); return { ...state, rows: [], index: 0, loading: true, error: '' }; }
      if (key.tab || key.leftArrow || key.rightArrow) return {
        ...state, all: key.leftArrow ? false : key.rightArrow ? true : !state.all, index: 0, error: '',
      };
      if (sdk.isCtrl(key, ch, 'u')) return { ...state, query: '', index: 0, error: '' };
      if (key.backspace || key.delete) return { ...state, query: Array.from(state.query).slice(0, -1).join(''), index: 0, error: '' };
      if (key.upArrow) return { ...state, index: Math.max(0, state.index - 1) };
      if (key.downArrow) return { ...state, index: Math.min(Math.max(0, matches(state).length - 1), state.index + 1) };
      if (key.pageUp) return { ...state, index: Math.max(0, state.index - 8) };
      if (key.pageDown) return { ...state, index: Math.min(Math.max(0, matches(state).length - 1), state.index + 8) };
      if (!state.loading && selected(state)) {
        if (key.return) return copy(state, 'resume');
        if (sdk.isCtrl(key, ch, 'p')) return copy(state, selected(state).pinned ? 'unpin' : 'pin');
      }
      if (ch && !key.ctrl && !key.meta && !/[\p{C}]/u.test(ch)) return { ...state, query: state.query + ch, index: 0, error: '' };
      return state;
    },
    render: props => h(LoadedView, props),
  });
  function LoadedView(props) {
    React.useEffect(() => { load(props.state); }, [props.state.token]);
    return h(View, props);
  }
}
