"use strict";
const fs = require("node:fs");
const path = require("node:path");
function normalizeReport(item) {
  if (
    !item ||
    typeof item.published_at !== "string" ||
    !item.published_at.trim()
  )
    return null;
  const date = new Date(item.published_at);
  let url;
  try {
    url = new URL(item.url);
  } catch {
    return null;
  }
  if (
    !item.id ||
    !item.source_id ||
    !item.title?.original ||
    !Number.isFinite(date.valueOf()) ||
    !["https:", "http:"].includes(url.protocol) ||
    !Array.isArray(item.commodities) ||
    !item.commodities.length
  )
    return null;
  const commodities = [
    ...new Set(item.commodities.filter((x) => typeof x === "string" && x)),
  ];
  if (!commodities.length) return null;
  return {
    report_id: String(item.id),
    source_id: String(item.source_id),
    title: String(item.title.original).slice(0, 1000),
    summary: String(item.summary || "").slice(0, 600),
    url: url.href,
    published_at: date.toISOString(),
    commodities,
  };
}
async function archiveReports({ file, upsert, dryRun = false } = {}) {
  const source =
    file ||
    path.join(
      __dirname,
      "..",
      "New for anti",
      "public",
      "data",
      "commodity_reports_v1.json",
    );
  const data = JSON.parse(fs.readFileSync(source, "utf8"));
  if (!Array.isArray(data.items)) throw new Error("invalid_reports_document");
  const normalized = data.items.map(normalizeReport);
  const rows = [
    ...new Map(
      normalized.filter(Boolean).map((row) => [row.report_id, row]),
    ).values(),
  ];
  if (!dryRun && normalized.some((row) => !row))
    throw new Error("invalid_report_rows");
  if (!dryRun) {
    const save = upsert || require("./lib/sync-utils").supabaseUpsert;
    for (let i = 0; i < rows.length; i += 50)
      await save("mailing_reports", rows.slice(i, i + 50), "report_id");
  }
  return {
    reports: rows.length,
    skipped: normalized.filter((x) => !x).length,
    mode: dryRun ? "preview" : "archive",
  };
}
module.exports = { normalizeReport, archiveReports };
if (require.main === module)
  archiveReports({ dryRun: process.argv.includes("--dry-run") })
    .then((result) => console.log(JSON.stringify(result)))
    .catch(() => {
      console.error("mailing_report_archive_failed");
      process.exitCode = 1;
    });
