// Cache regressions with disposable files; not native Ink acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, unlinkSync, renameSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { inventoryCache, inventoryStamp } from '../tui/pins.mjs';

const rows = [{ id: 'exact-ID', title: 'Project', pinned: true, model: 'stored', updated: 1 }];
function fixture(t) {
  const home = mkdtempSync(join(tmpdir(), 'pins-cache-'));
  t.after(() => rmSync(home, { recursive: true, force: true }));
  writeFileSync(join(home, 'state.db'), 'synthetic metadata file');
  return home;
}

test('unchanged inventory is reused until the 30-second monotonic deadline', t => {
  const home = fixture(t);
  let clock = 0;
  const cache = inventoryCache(home, { now: () => clock });
  assert.equal(cache.read(), null);
  cache.store(rows, inventoryStamp(home));
  assert.deepEqual(cache.read(), rows);
  clock = 29_999;
  assert.deepEqual(cache.read(), rows);
  clock = 30_000;
  assert.equal(cache.read(), null);
});

test('DB writes invalidate cached pins, titles and visibility results', t => {
  const home = fixture(t), cache = inventoryCache(home);
  cache.store(rows, inventoryStamp(home));
  writeFileSync(join(home, 'state.db'), 'new state with different length');
  assert.equal(cache.read(), null);
});

test('WAL creation, append and removal each invalidate unchanged DB metadata', t => {
  const home = fixture(t), cache = inventoryCache(home);
  const wal = join(home, 'state.db-wal');
  cache.store(rows, inventoryStamp(home));
  writeFileSync(wal, 'first commit');
  assert.equal(cache.read(), null);
  cache.store(rows, inventoryStamp(home));
  writeFileSync(wal, 'second longer commit');
  assert.equal(cache.read(), null);
  cache.store(rows, inventoryStamp(home));
  unlinkSync(wal);
  assert.equal(cache.read(), null);
});

test('DB replacement and deletion invalidate rather than retaining old rows', t => {
  const home = fixture(t), cache = inventoryCache(home);
  cache.store(rows, inventoryStamp(home));
  writeFileSync(join(home, 'replacement'), 'synthetic metadata file');
  renameSync(join(home, 'replacement'), join(home, 'state.db'));
  assert.equal(cache.read(), null);
  cache.store(rows, inventoryStamp(home));
  unlinkSync(join(home, 'state.db'));
  assert.equal(cache.read(), null);
  assert.equal(inventoryStamp(home), null);
});

test('a commit during inventory loading prevents caching that response', t => {
  const home = fixture(t), cache = inventoryCache(home);
  const before = inventoryStamp(home);
  writeFileSync(join(home, 'state.db-wal'), 'concurrent commit');
  cache.store(rows, before);
  assert.equal(cache.read(), null);
});

test('missing or unreadable metadata never qualifies a cache entry', () => {
  const cache = inventoryCache('/synthetic-only', { stamp: () => null });
  cache.store(rows, null);
  assert.equal(cache.read(), null);
});

test('rows are copied on store and read; explicit refresh can clear the entry', t => {
  const home = fixture(t), cache = inventoryCache(home);
  const original = rows.map(row => ({ ...row }));
  cache.store(original, inventoryStamp(home));
  original[0].title = 'mutated caller';
  const first = cache.read();
  first[0].title = 'mutated consumer';
  assert.deepEqual(cache.read(), rows);
  cache.clear();
  assert.equal(cache.read(), null);
});

test('registrations keep inventories separate even with colliding session IDs', t => {
  const first = fixture(t), second = fixture(t);
  const a = inventoryCache(first), b = inventoryCache(second);
  a.store(rows, inventoryStamp(first));
  assert.equal(b.read(), null);
  const other = [{ ...rows[0], title: 'Other profile' }];
  b.store(other, inventoryStamp(second));
  assert.deepEqual(a.read(), rows);
  assert.deepEqual(b.read(), other);
});
