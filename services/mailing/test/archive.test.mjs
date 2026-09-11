import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import importer from "../../../scripts/archive-mailing-reports.js";
const report = (id) => ({
  id,
  source_id: "usda",
  title: { original: "Report" },
  published_at: "2026-09-10",
  url: "https://example.test/report",
  commodities: ["wheat"],
});
async function snapshot(items, fn) {
  const dir = mkdtempSync(join(tmpdir(), "mailing-test-"));
  try {
    const file = join(dir, "reports.json");
    writeFileSync(file, JSON.stringify({ items }));
    await fn(file);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}
test("partial archive failure rejects the run; replay keeps every report once", async () => {
  await snapshot(
    Array.from({ length: 51 }, (_, i) => report(String(i))),
    async (file) => {
      const saved = new Map();
      let calls = 0;
      const save = async (table, rows, key) => {
        assert.equal(table, "mailing_reports");
        assert.equal(key, "report_id");
        for (const row of rows) saved.set(row.report_id, row);
      };
      await assert.rejects(
        importer.archiveReports({
          file,
          upsert: async (...args) => {
            if (++calls === 2) throw Error("timeout");
            await save(...args);
          },
        }),
        /timeout/,
      );
      assert.equal(saved.size, 50);
      await importer.archiveReports({ file, upsert: save });
      assert.equal(saved.size, 51);
    },
  );
});
test("preview never persists report data", async () => {
  await snapshot([report("1")], async (file) => {
    let writes = 0;
    const result = await importer.archiveReports({
      file,
      dryRun: true,
      upsert: () => {
        writes++;
      },
    });
    assert.equal(result.reports, 1);
    assert.equal(writes, 0);
  });
});
test("invalid report cannot silently disappear from a successful archive run", async () => {
  await snapshot([report("1"), null], async (file) => {
    let writes = 0;
    await assert.rejects(
      importer.archiveReports({
        file,
        upsert: () => {
          writes++;
        },
      }),
      /invalid_report_rows/,
    );
    assert.equal(writes, 0);
  });
});
