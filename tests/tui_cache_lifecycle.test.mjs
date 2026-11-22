// Public-SDK lifecycle shims and controlled I/O; NOT native Ink acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import cp from 'node:child_process';
import fs from 'node:fs';
import { syncBuiltinESMExports } from 'node:module';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import register from '../tui/pins.mjs';

function harness(t) {
  const originalHome = process.env.HERMES_HOME;
  const home = fs.mkdtempSync(join(tmpdir(), 'pins-lifecycle-'));
  fs.writeFileSync(join(home, 'state.db'), 'synthetic metadata file');
  process.env.HERMES_HOME = home;
  const effects = [], pending = [];
  let state, app;
  t.mock.method(cp, 'execFile', (_file, _args, options, callback) => {
    assert.equal(options.env.HERMES_HOME, home);
    pending.push(callback);
    return { kill() {}, stdin: { end() {} } };
  });
  syncBuiltinESMExports();
  register({ h: (type, props) => ({ type, props }), React: { useEffect: fn => effects.push(fn) },
    defineWidgetApp: a => (app = a),
    updateWidget: (_app, fn) => { if (state) state = fn(state); },
    isCtrl: (key, ch, target) => key.ctrl && ch.toLowerCase() === target });
  t.after(() => {
    t.mock.restoreAll();
    syncBuiltinESMExports();
    if (originalHome === undefined) delete process.env.HERMES_HOME;
    else process.env.HERMES_HOME = originalHome;
    fs.rmSync(home, { recursive: true, force: true });
  });
  const h = {
    get state() { return state; }, pending, home,
    open() { state = app.init(''); const view = app.render({ state }); view.type(view.props); },
    mount() { effects.shift()(); },
    key(key, ch = '') { state = app.reduce(state, { key, ch }); },
    succeed() { pending.shift()(null, JSON.stringify({ home, rows: [{ id: 'exact-key', title: 'Project', pinned: true }] })); },
  };
  h.open(); h.mount(); h.succeed();
  assert.equal(h.state.loading, false);
  h.key({ escape: true });
  assert.equal(h.state, null);
  return h;
}

test('a cached mount makes one metadata decision, not a second racy cache read', t => {
  const h = harness(t);
  const real = fs.statSync;
  let checks = 0;
  t.mock.method(fs, 'statSync', (...args) => {
    if (/\/state\.db(?:-wal)?$/.test(args[0]) && ++checks > 2) {
      throw Object.assign(new Error('synthetic second-check failure'), { code: 'EIO' });
    }
    return real(...args);
  });
  syncBuiltinESMExports();
  h.open();
  assert.equal(h.state.loading, false);
  h.mount();
  assert.equal(checks, 2, 'one DB + WAL check; no gap between two cache decisions');
  assert.equal(h.pending.length, 0);
  assert.equal(h.state.loading, false);
  h.key({ escape: true });
});

test('cache rejection clears selectable rows before reload, and late replies stay closed', t => {
  const h = harness(t);
  t.mock.method(fs, 'statSync', () => { throw Object.assign(new Error('synthetic metadata failure'), { code: 'EIO' }); });
  syncBuiltinESMExports();
  h.open();
  h.mount();
  assert.equal(h.state.loading, true);
  assert.deepEqual(h.state.rows, []);
  assert.equal(h.pending.length, 1);
  h.key({ return: true });
  assert.equal(h.state.loading, true);
  h.key({ escape: true });
  h.succeed();
  assert.equal(h.state, null);
});

test('forced refresh bypasses cache and a failed refresh cannot restore old rows', t => {
  const h = harness(t);
  h.open(); h.mount();
  assert.equal(h.pending.length, 0);
  h.key({ ctrl: true }, 'r');
  assert.equal(h.pending.length, 1);
  assert.equal(h.state.loading, true);
  assert.deepEqual(h.state.rows, []);
  h.pending.shift()(new Error('synthetic CLI failure'), '');
  assert.equal(h.state.loading, false);
  assert.deepEqual(h.state.rows, []);
  assert.match(h.state.error, /Could not read chats/);
  h.key({ escape: true });
  h.open();
  assert.equal(h.state.loading, true);
  assert.deepEqual(h.state.rows, []);
});

test('a profile enablement edit invalidates a warm reopen and fences an in-flight reply', t => {
  const h = harness(t);
  const config = join(h.home, 'config.yaml');
  fs.writeFileSync(config, 'plugins: {enabled: [session-pins]}');
  h.open();
  assert.equal(h.state.loading, true);
  assert.deepEqual(h.state.rows, []);
  h.mount();
  fs.writeFileSync(config, 'plugins: {disabled: [session-pins]}');
  h.succeed();
  assert.equal(h.state.loading, false);
  assert.deepEqual(h.state.rows, []);
  assert.match(h.state.error, /configuration changed/);
});
