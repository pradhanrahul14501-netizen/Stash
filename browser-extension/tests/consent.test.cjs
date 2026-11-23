const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "background.js"), "utf8");

async function createHarness(settings) {
  const sent = [];
  const listeners = () => ({ addListener() {} });
  const chrome = {
    storage: {
      local: {
        async get(keys) {
          return Object.fromEntries(keys.filter(key => key in settings).map(key => [key, settings[key]]));
        },
      },
    },
    runtime: {
      onMessage: listeners(),
      onConnect: listeners(),
      onInstalled: listeners(),
    },
    contextMenus: { onClicked: listeners() },
    downloads: { onChanged: listeners() },
  };
  const context = vm.createContext({
    chrome,
    console,
    URL,
    AbortController,
    setTimeout,
    clearTimeout,
    fetch: async (url, options) => {
      sent.push({ url, options });
      return { ok: true, status: 200 };
    },
  });
  vm.runInContext(`${source}\nglobalThis.__testStashFetch = stashFetch;`, context, {
    filename: "browser-extension/background.js",
  });
  return { context, sent };
}

async function run() {
  for (const connection of [
    { stashServerUrl: "http://127.0.0.1:5050", stashLocalAccessToken: "local-token" },
    { stashServerUrl: "https://stash.example", stashAccessToken: "shared-token" },
  ]) {
    const { context, sent } = await createHarness(connection);
    await assert.rejects(
      vm.runInContext("__testStashFetch('browserCopy', { method: 'POST', body: 'fixture content' })", context),
      error => /confirm where chosen copies are sent/.test(error.message),
    );
    assert.equal(sent.length, 0, "content must not leave the device before consent");
  }

  const local = await createHarness({
    stashServerUrl: "http://127.0.0.1:5050",
    stashLocalAccessToken: "local-token",
    stashContentConsent: true,
  });
  await vm.runInContext("__testStashFetch('browserCopy', { method: 'POST', body: 'fixture content' })", local.context);
  assert.equal(local.sent.length, 1);
  assert.equal(local.sent[0].url, "http://127.0.0.1:5050/api/browser-copy");

  const shared = await createHarness({
    stashServerUrl: "https://stash.example",
    stashAccessToken: "shared-token",
    stashContentConsent: true,
  });
  await vm.runInContext("__testStashFetch('browserCopy', { method: 'POST', body: 'fixture content' })", shared.context);
  assert.equal(shared.sent.length, 1);
  assert.equal(shared.sent[0].url, "https://stash.example/api/shared/extensions/browser-copy");
  console.log("PASS: local and shared extension uploads send no request before explicit content consent.");
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
