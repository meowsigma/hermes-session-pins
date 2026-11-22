// Pure helper/reducer unit regressions, NOT native UI acceptance.
// Kept for authorized test execution; not run on the owner's PC.
import test from 'node:test';
import assert from 'node:assert/strict';
import { homedir } from 'node:os';
import { resolve } from 'node:path';
import register, { matches, selected, copyCommand, clean, age } from '../tui/pins.mjs';

const rows = [
  { id: 'first-ID', title: 'a'.repeat(200) + ' hidden-tail-needle', pinned: true },
  { id: 'second-ID', title: 'Other project', pinned: false },
];
const base = { rows, query: '', all: false, index: 0, token: 'unit-instance', loading: false, busy: false,
  home: resolve(process.env.HERMES_HOME || resolve(homedir(), '.hermes')) };
function app() {
  let definition;
  register({ defineWidgetApp: a => (definition = a),
    isCtrl: (key, ch, letter) => Boolean(key.ctrl) && ch.toLowerCase() === letter,
    updateWidget: () => { throw new Error('Unexpected asynchronous action in this pure reducer test'); },
  });
  return definition;
}
const input = (key = {}, ch = '') => ({ key, ch });

test('full-title search is independent of label truncation', () => {
  assert.deepEqual(matches({ ...base, query: 'hidden-tail-needle' }), [rows[0]]);
  assert.equal(matches({ ...base, query: 'first-id' }).length, 0);
  assert.deepEqual(matches({ ...base, query: 'first-ID' }), [rows[0]]);
});
test('Pinned/All and exact selection stay in the supplied inventory', () => {
  assert.deepEqual(matches(base), [rows[0]]);
  assert.deepEqual(matches({ ...base, all: true }), rows);
  assert.equal(selected({ ...base, all: true, index: 500 }).id, 'second-ID');
});
test('copyable command preserves the exact key and never launches anything', () => {
  assert.equal(copyCommand(rows[0]), '/resume first-ID');
  assert.equal(copyCommand(rows[0], 'unpin'), '/unpin first-ID');
  assert.equal(copyCommand(rows[1], 'pin'), '/pin second-ID');
  for (const id of ['', '1234', '-x', 'with space', 'line\nbreak', '\u001b[31m', '<wrapped>', 'x\u202ey']) {
    assert.throws(() => copyCommand({ id }));
  }
});
test('public SDK key signature, filtering, backspace and cancellation', () => {
  const a = app();
  assert.equal(a.id, 'pins');
  assert.equal(a.mode, 'modal');
  assert.equal(a.reduce(base, input({ escape: true })), null);
  assert.equal(a.reduce(base, input({ ctrl: true }, 'c')), null);
  const all = a.reduce(base, input({ tab: true }));
  assert.equal(all.all, true);
  assert.equal(a.reduce(all, input({ downArrow: true })).index, 1);
  const typed = a.reduce(base, input({}, 'needle'));
  assert.equal(typed.query, 'needle');
  assert.equal(a.reduce(typed, input({ ctrl: true }, 'u')).query, '');
  assert.equal(a.reduce({ ...base, query: 'a😀' }, input({ backspace: true })).query, 'a');
});
test('Left/Right choose Pinned/All while Tab still toggles, preserving search', () => {
  const a = app();
  for (const loading of [false, true]) {
    const state = { ...base, all: true, index: 1, query: 'project', error: 'previous error', loading };
    const pinned = a.reduce(state, input({ leftArrow: true }));
    assert.equal(pinned.all, false);
    assert.equal(pinned.index, 0);
    assert.equal(pinned.query, state.query);
    assert.equal(pinned.error, '');
    assert.equal(pinned.loading, loading);
    assert.equal(pinned.rows, state.rows);
    assert.equal(pinned.home, state.home);
    assert.equal(pinned.token, state.token);
    assert.equal(a.reduce(pinned, input({ leftArrow: true })).all, false);
    const all = a.reduce({ ...pinned, index: 1, error: 'another error' }, input({ rightArrow: true }));
    assert.equal(all.all, true);
    assert.equal(all.index, 0);
    assert.equal(all.query, state.query);
    assert.equal(all.error, '');
    assert.equal(all.loading, loading);
    assert.equal(all.rows, state.rows);
    assert.equal(all.home, state.home);
    assert.equal(all.token, state.token);
    assert.equal(a.reduce(all, input({ rightArrow: true })).all, true);
    assert.equal(a.reduce(all, input({ tab: true })).all, false);
    assert.equal(a.reduce(pinned, input({ tab: true })).all, true);
  }
});

test('unique instance tokens and safe metadata rendering', () => {
  const a = app();
  assert.notEqual(a.init('').token, a.init('').token);
  assert.equal(clean('hello\u001b[31m\nworld\u202e'), 'hello[31mworld');
  assert.equal(age(1, 61_000), '1m ago');
});

test('launch arguments cannot inject controls and manage opens Pinned', () => {
  const a = app();
  assert.equal(/[\p{C}]/u.test(a.init('query\u001b[31m\nnext').query), false);
  const state = a.init('manage');
  assert.equal(state.query, '');
  assert.equal(state.all, false);
});

test('invalid-home refresh returns the terminal error state, not a stuck loader', () => {
  const original = process.env.HERMES_HOME;
  try {
    process.env.HERMES_HOME = '/invalid/$HOME';
    const a = app();
    const result = a.reduce(a.init(''), input({ ctrl: true }, 'r'));
    assert.equal(result.loading, false);
    assert.match(result.error, /home cannot round-trip/);
    assert.deepEqual(result.rows, []);
  } finally {
    if (original === undefined) delete process.env.HERMES_HOME;
    else process.env.HERMES_HOME = original;
  }
});

test('loading, results and errors reuse one dialog geometry without a viewport scrim', () => {
  let app;
  const sdk = { defineWidgetApp: a => (app = a), React: { useEffect() {} },
    h: (type, props, ...children) => ({ type, props, children }),
    Overlay: 'Overlay', Dialog: 'Dialog', Text: 'Text', Box: 'Box', ShimmerRows: 'ShimmerRows' };
  register(sdk);
  for (const height of [16, 26, 32]) {
    const phases = [{ ...base, rows: [], loading: true }, base, { ...base, rows: [], error: 'Unavailable' }];
    const heights = phases.map(state => {
      const view = app.render({ state, cols: 100, rows: height, t: { color: {} } });
      const component = view.type(view.props);
      const tree = component.type(component.props);
      assert.equal(tree.type, 'Overlay');
      assert.notEqual(tree.props.backdrop, true);
      assert.ok(!JSON.stringify(tree).includes('ShimmerRows'));
      return tree.children[0].children.find(node => node?.props?.height)?.props.height;
    });
    assert.ok(heights[0] > 0);
    assert.ok(heights.every(n => n === heights[0]));
  }
});
