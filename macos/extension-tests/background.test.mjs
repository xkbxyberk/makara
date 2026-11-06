// The background script's menus, against a stand-in as strict as Safari: an id used twice is an
// error, and an error nobody reads in the callback is recorded on the extension. Safari then
// closed the background page (CLAUDE.md gotcha 56). Run with `node --test`.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const SCRIPT = process.env.VD_BACKGROUND ?? new URL('../extension/background.js', import.meta.url);
const tick = () => new Promise((done) => setTimeout(done, 1));

/** Loads the script. `kept`: ids Safari still has from before; `sticky`: removeAll leaves them. */
function load({ kept = [], sticky = false } = {}) {
  const items = new Set(kept);
  const unchecked = [];
  let installed = () => undefined;
  let lastError;
  let read = false;
  const event = { addListener() {} };
  const browser = {
    i18n: { getMessage: (key) => key },
    storage: { local: {}, session: {} },
    tabs: { onUpdated: event, onActivated: event, onRemoved: event },
    runtime: {
      onMessage: event,
      onInstalled: { addListener: (listener) => (installed = listener) },
      get lastError() {
        read = true;
        return lastError;
      },
    },
    contextMenus: {
      onClicked: event,
      // Safari handles calls in order: a removeAll takes effect before a later create, and only
      // its answer comes later.
      removeAll: async () => {
        if (!sticky) items.clear();
        await tick();
      },
      create(item, callback) {
        lastError = items.has(item.id) ? { message: 'Identifier is already used.' } : undefined;
        items.add(item.id);
        read = false;
        callback?.();
        if (lastError && !read) unchecked.push(item.id);
        lastError = undefined;
      },
    },
  };
  vm.runInNewContext(readFileSync(SCRIPT, 'utf8'), { browser, VD: {}, setTimeout, Map, Promise, Date });
  return { items, unchecked, installed: () => installed() };
}

const settled = async () => {
  for (let i = 0; i < 20; i += 1) await tick();
};
const ALL = ['vd-download', 'vd-inspect', 'vd-page'];

test('a load that also gets onInstalled creates each menu once, with no unchecked error', async () => {
  const run = load();
  run.installed();
  await settled();
  assert.deepEqual(run.unchecked, []);
  assert.deepEqual([...run.items].sort(), ALL);
});

test('menus Safari kept from the last load are no failure', async () => {
  const run = load({ kept: ALL, sticky: true });
  await settled();
  assert.deepEqual(run.unchecked, []);
  assert.deepEqual([...run.items].sort(), ALL);
});
