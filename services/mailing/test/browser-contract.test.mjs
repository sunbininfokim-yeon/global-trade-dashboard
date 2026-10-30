import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
const source = readFileSync(
  new URL("../../../New for anti/auth.js", import.meta.url),
  "utf8",
);
async function authFixture({
  user = { id: "u" },
  preferences = null,
  saveError = null,
} = {}) {
  const calls = [];
  const client = {
    auth: {
      onAuthStateChange() {},
      async getSession() {
        return { data: { session: user ? { user } : null } };
      },
    },
    from(table) {
      calls.push(["from", table]);
      return {
        select(columns) {
          calls.push(["select", columns]);
          return this;
        },
        eq(column, value) {
          calls.push(["eq", column, value]);
          return this;
        },
        async maybeSingle() {
          return { data: preferences, error: null };
        },
      };
    },
    async rpc(name, args) {
      calls.push(["rpc", name, JSON.parse(JSON.stringify(args))]);
      return { error: saveError };
    },
  };
  const window = { supabase: { createClient: () => client } };
  runInNewContext(source, { window, document: { getElementById: () => null } });
  await new Promise((resolve) => setImmediate(resolve));
  return { auth: window.Auth, calls };
}
test("browser loads only its own preferences and keeps defaults for a new account", async () => {
  const { auth, calls } = await authFixture();
  assert.deepEqual(
    JSON.parse(JSON.stringify(await auth.mailingPreferences())),
    { policy_enabled: true, commodity_enabled: true },
  );
  assert.ok(
    calls.some((c) => c[0] === "eq" && c[1] === "user_id" && c[2] === "u"),
  );
});
test("browser writes only the selected switch through the atomic RPC", async () => {
  const { auth, calls } = await authFixture();
  await auth.setMailingPreference("policy", false);
  assert.deepEqual(calls, [
    [
      "rpc",
      "set_my_mailing_preference",
      { p_kind: "policy", p_enabled: false },
    ],
  ]);
  await assert.rejects(auth.setMailingPreference("invalid", true));
});
test("preference save failure reaches the UI and signed-out calls fail closed", async () => {
  const { auth } = await authFixture({ saveError: Error("rejected") });
  await assert.rejects(
    auth.setMailingPreference("commodity", false),
    /rejected/,
  );
  const loggedOut = await authFixture({ user: null });
  await assert.rejects(loggedOut.auth.mailingPreferences());
  await assert.rejects(loggedOut.auth.setMailingPreference("policy", false));
  assert.equal(loggedOut.calls.length, 0);
});
