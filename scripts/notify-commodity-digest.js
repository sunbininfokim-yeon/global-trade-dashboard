"use strict";
// Preserve the saved RSS snapshot in the durable archive before checking mail.
async function run() {
  require("./lib/load-env").loadLocalEnv();
  const { archiveReports } = require("./archive-mailing-reports");
  console.log(
    JSON.stringify(
      await archiveReports({ dryRun: process.argv.includes("--dry-run") }),
    ),
  );
  if (process.argv.includes("--dry-run")) return;
  const { runMailing } = await import("../services/mailing/core.mjs");
  const result = await runMailing(process.env, { kind: "commodity" });
  console.log(JSON.stringify(result));
  if (result.failed) process.exitCode = 1;
}
if (require.main === module)
  run().catch(() => {
    console.error("commodity_mail_run_failed");
    process.exitCode = 1;
  });
module.exports = { run };
