"use strict";
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { spawnSync } = require("node:child_process");
function githubSnapshot({ repo = "sunbininfokim-yeon/global-trade-dashboard", ref = "main", gh = path.join(os.homedir(), ".local/bin/gh"), run = spawnSync } = {}) {
  const result = run(gh, ["api", `repos/${repo}/contents/New%20for%20anti/public/data/commodity_reports_v1.json?ref=${encodeURIComponent(ref)}`], { encoding: "utf8", timeout: 30000, maxBuffer: 4 * 1024 * 1024 });
  if (result.status !== 0) throw new Error("report_snapshot_unavailable");
  const response = JSON.parse(result.stdout);
  if (response.encoding !== "base64" || !response.content || !response.sha) throw new Error("invalid_github_snapshot");
  return { document: JSON.parse(Buffer.from(response.content, "base64").toString("utf8")), sha: response.sha };
}
function reportOmission(item) {
  if (!item) return null;
  let url; try { url = new URL(item.url); } catch { return false; }
  if (!(item.id && item.source_id && item.title?.original && ["https:", "http:"].includes(url.protocol) && Array.isArray(item.commodities))) return null;
  const undated = item.published_at == null || (typeof item.published_at === "string" && !item.published_at.trim());
  if (!undated && (typeof item.published_at !== "string" || !Number.isFinite(new Date(item.published_at).valueOf()))) return null;
  const unclassified = !item.commodities.some(x => typeof x === "string" && x);
  return undated || unclassified ? { undated, unclassified } : null;
}
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
async function archiveReports({ file, document, upsert, dryRun = false, skipUndated = false, skipUnclassified = false } = {}) {
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
  const data = document || JSON.parse(fs.readFileSync(source, "utf8"));
  if (!Array.isArray(data.items)) throw new Error("invalid_reports_document");
  const normalized = data.items.map(normalizeReport);
  const rows = [
    ...new Map(
      normalized.filter(Boolean).map((row) => [row.report_id, row]),
    ).values(),
  ];
  const omissions = data.items.map(reportOmission);
  const undated = omissions.filter(x => x?.undated).length;
  const unclassified = omissions.filter(x => x?.unclassified).length;
  const invalid = normalized.filter((row, i) => !row && !(omissions[i] && (!omissions[i].undated || skipUndated) && (!omissions[i].unclassified || skipUnclassified))).length;
  if (!dryRun && invalid)
    throw new Error("invalid_report_rows");
  if (!dryRun) {
    const save = upsert || require("./lib/sync-utils").supabaseUpsert;
    for (let i = 0; i < rows.length; i += 50)
      await save("mailing_reports", rows.slice(i, i + 50), "report_id");
  }
  return {
    reports: rows.length,
    skipped: normalized.filter((x) => !x).length,
    skipped_undated: undated,
    skipped_unclassified: unclassified,
    partial: normalized.some(x => !x),
    source_generated_at: data.generated_at || null,
    mode: dryRun ? "preview" : "archive",
  };
}
module.exports = { normalizeReport, archiveReports, githubSnapshot };
if (require.main === module)
  Promise.resolve().then(async () => {
    const snapshot = process.argv.includes("--github") ? githubSnapshot() : null;
    const result = await archiveReports({ document: snapshot?.document, dryRun: process.argv.includes("--dry-run"), skipUndated: process.argv.includes("--skip-undated"), skipUnclassified: process.argv.includes("--skip-unclassified") });
    console.log(JSON.stringify({ ...result, source_sha: snapshot?.sha || null }));
  })
    .catch(() => {
      console.error("mailing_report_archive_failed");
      process.exitCode = 1;
    });
