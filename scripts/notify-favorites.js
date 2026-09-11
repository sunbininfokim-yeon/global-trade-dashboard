"use strict";
// Preview unless MAIL_SEND_ENABLED=true is explicit. No item timestamp diffing.
async function run() {
  require("./lib/load-env").loadLocalEnv();
  const { runMailing } = await import("../services/mailing/core.mjs");
  const env = {
    ...process.env,
    ...(process.argv.includes("--dry-run")
      ? { MAIL_SEND_ENABLED: "false" }
      : {}),
  };
  const result = await runMailing(env, { kind: "policy" });
  console.log(JSON.stringify(result));
  if (result.failed) process.exitCode = 1;
}
if (require.main === module)
  run().catch(() => {
    console.error("policy_mail_run_failed");
    process.exitCode = 1;
  });
module.exports = { run };
