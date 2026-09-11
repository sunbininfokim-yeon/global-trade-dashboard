import { test, before, beforeEach, after } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { PGlite } from "@electric-sql/pglite";
import {
  runMailing,
  renderDelivery,
  createRpc,
  readJson,
  scheduledMailKind,
} from "../core.mjs";
import importer from "../../../scripts/archive-mailing-reports.js";

const U = "00000000-0000-0000-0000-000000000001";
const V = "00000000-0000-0000-0000-000000000002";
let db;
const migration = readFileSync(
  new URL(
    "../../../supabase/migrations/20260911010000_mailing_outbox.sql",
    import.meta.url,
  ),
  "utf8",
);
const setup = `
create role anon; create role authenticated; create role service_role bypassrls;
create schema auth;
create function auth.uid() returns uuid language sql as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
create table auth.users(id uuid primary key,email text,email_confirmed_at timestamptz);
create table public.profiles(id uuid primary key,email text);
create table public.user_favorites(user_id uuid,item_kind text,item_id text,title text,created_at timestamptz default now(),primary key(user_id,item_kind,item_id));
create table public.bills(bill_id text primary key,title text,current_stage text,latest_action_text text,status_updated_at timestamptz);
create table public.executive_orders(eo_number integer primary key,title text,summary text,updated_at timestamptz);
create table public.commodity_report_notifications(user_id uuid,report_id text,sent_at timestamptz default now(),primary key(user_id,report_id));
create table public.commodity_digest_source_prefs(user_id uuid,source_id text,primary key(user_id,source_id));
`;
before(async () => {
  db = new PGlite();
  await db.exec(setup);
  await db.exec(migration);
});
after(async () => {
  await db.close();
});
beforeEach(async () => {
  await db.exec(
    "truncate public.mailing_outbox,public.mailing_deliveries,public.mailing_reports,public.mailing_preferences,public.user_favorites,public.bills,public.executive_orders,public.commodity_report_notifications,public.commodity_digest_source_prefs,public.profiles,auth.users cascade",
  );
  await db.query("insert into auth.users values($1,$2,now()),($3,$4,now())", [
    U,
    "verified@example.test",
    V,
    "second@example.test",
  ]);
  await db.query("insert into public.profiles values($1,$2),($3,$4)", [
    U,
    "unverified-profile@example.test",
    V,
    "profile-two@example.test",
  ]);
  await db.exec(
    "insert into public.bills values('119-hr-1','A bill','referred','same day action','2026-09-10')",
  );
});
async function rpc(name, args = {}) {
  const entries = Object.entries(args);
  const params = entries.map(([k], i) => `${k}=>$${i + 1}`).join(",");
  const result = await db.query(
    `select public.${name}(${params}) as value`,
    entries.map(([, v]) =>
      typeof v === "object" && v !== null ? JSON.stringify(v) : v,
    ),
  );
  return result.rows[0].value;
}
const count = async (table) =>
  Number((await db.query(`select count(*) n from public.${table}`)).rows[0].n);
async function favorite(user = U, kind = "bill", id = "119-hr-1") {
  await db.query(
    "insert into public.user_favorites(user_id,item_kind,item_id,created_at)values($1,$2,$3,now()-interval '2 days')",
    [user, kind, id],
  );
}
async function stage(value = "reported") {
  await db.query("update public.bills set current_stage=$1", [value]);
}
async function due() {
  await db.exec(
    "update public.mailing_outbox set due_at=now()-interval '1 minute'",
  );
}
async function claim() {
  return rpc("mail_claim");
}
const env = {
  MAIL_SEND_ENABLED: "true",
  RESEND_API_KEY: "mock",
  NOTIFY_FROM_EMAIL: "alerts@example.test",
};
const success = async () => Response.json({ id: crypto.randomUUID() });

test("migration is rerunnable without duplicating triggers or config", async () => {
  await db.exec(migration);
  await favorite();
  await stage();
  assert.equal(await count("mailing_outbox"), 1);
});
test("favorite creation is baseline; same-day stage events both survive", async () => {
  await favorite();
  assert.equal(await count("mailing_outbox"), 0);
  await stage();
  await stage("passed_origin_chamber");
  await stage("passed_origin_chamber");
  assert.equal(await count("mailing_outbox"), 2);
  assert.equal(await claim(), null);
  await due();
  const d = await claim();
  assert.equal(d.items.length, 2);
  assert.equal(d.recipient, "verified@example.test");
});
test("due date is next KST day at 06:00, including midnight boundary", async () => {
  assert.equal(
    (
      await rpc("mail_next_due", {
        p_kind: "policy",
        p_at: "2026-09-10T14:59:59Z",
      })
    ).toISOString(),
    "2026-09-10T21:00:00.000Z",
  );
  assert.equal(
    (
      await rpc("mail_next_due", {
        p_kind: "policy",
        p_at: "2026-09-10T15:00:00Z",
      })
    ).toISOString(),
    "2026-09-11T21:00:00.000Z",
  );
});
test("weekly report due includes Monday morning before 08:00", async () => {
  const value = await rpc("mail_next_due", {
    p_kind: "commodity",
    p_at: "2026-09-13T22:00:00Z",
  });
  assert.equal(value.toISOString(), "2026-09-13T23:00:00.000Z");
});
test("bill update rollback also rolls back its notification", async () => {
  await favorite();
  await db.exec(
    "begin; update public.bills set current_stage='reported'; rollback;",
  );
  assert.equal(await count("mailing_outbox"), 0);
});
test("unverified Auth email remains pending; profile email never substitutes", async () => {
  await favorite();
  await stage();
  await due();
  await db.query("update auth.users set email_confirmed_at=null where id=$1", [
    U,
  ]);
  assert.equal(await claim(), null);
  assert.equal(await count("mailing_outbox"), 1);
  assert.equal(await count("mailing_deliveries"), 0);
});
test("lease prevents overlapping claims and stale lease reclaims same delivery", async () => {
  await favorite();
  await stage();
  await due();
  const a = await claim();
  assert.equal(await claim(), null);
  await db.exec(
    "update public.mailing_deliveries set lease_until=now()-interval '1 minute'",
  );
  const b = await claim();
  assert.equal(a.delivery_id, b.delivery_id);
  assert.notEqual(a.lease_token, b.lease_token);
  assert.equal(
    await rpc("mail_complete", {
      p_delivery_id: a.delivery_id,
      p_lease_token: a.lease_token,
      p_message_id: "stale",
    }),
    false,
  );
});
test("unfavorite or disabling policy suppresses pending mail", async () => {
  await favorite();
  await stage();
  await due();
  await db.query(
    "insert into public.mailing_preferences values($1,false,true)",
    [U],
  );
  assert.equal(await claim(), null);
  assert.equal(
    Number(
      (
        await db.query(
          "select count(*) n from public.mailing_outbox where suppressed_at is not null",
        )
      ).rows[0].n,
    ),
    1,
  );
});
test("subscription withdrawn between claim and send prevents network send", async () => {
  await favorite();
  await stage();
  await due();
  let calls = 0;
  const guarded = async (name, args) => {
    const result = await rpc(name, args);
    if (name === "mail_claim" && result)
      await db.exec("delete from public.user_favorites");
    return result;
  };
  const result = await runMailing(env, {
    rpc: guarded,
    fetcher: async () => {
      calls++;
      return success();
    },
  });
  assert.equal(calls, 0);
  assert.equal(result.cancelled, 1);
});
test("changed verified email after claim cancels frozen recipient", async () => {
  await favorite();
  await stage();
  await due();
  const d = await claim();
  await db.query("update auth.users set email=$1 where id=$2", [
    "changed@example.test",
    U,
  ]);
  assert.equal(
    await rpc("mail_prepare", {
      p_delivery_id: d.delivery_id,
      p_lease_token: d.lease_token,
      p_payload: renderDelivery(d, "a@example.test"),
    }),
    null,
  );
});
test("successful recipients are checkpointed before next recipient fails", async () => {
  await favorite();
  await favorite(V);
  await stage();
  await due();
  let sends = 0;
  const result = await runMailing(env, {
    rpc,
    fetcher: async () => {
      sends++;
      return sends === 1
        ? Response.json({ id: "accepted-first" })
        : new Response("", { status: 500 });
    },
  });
  assert.equal(result.accepted, 1);
  assert.equal(result.failed, 1);
  const states = (
    await db.query("select state from public.mailing_deliveries order by state")
  ).rows.map((x) => x.state);
  assert.deepEqual(states, ["retry", "sent"]);
});
test("lost checkpoint response retries exact payload and idempotency key", async () => {
  await favorite();
  await stage();
  await due();
  const requests = [];
  let lose = true;
  const lossy = async (name, args) => {
    if (name === "mail_complete" && lose) {
      lose = false;
      throw Error("lost DB request");
    }
    return rpc(name, args);
  };
  const provider = async (url, options) => {
    requests.push(options);
    return Response.json({ id: "same-provider-id" });
  };
  await assert.rejects(runMailing(env, { rpc: lossy, fetcher: provider }));
  await db.exec(
    "update public.mailing_deliveries set lease_until=now()-interval '1 minute'",
  );
  await runMailing(
    { ...env, NOTIFY_FROM_EMAIL: "different@example.test" },
    { rpc, fetcher: provider },
  );
  assert.equal(requests.length, 2);
  assert.equal(requests[0].body, requests[1].body);
  assert.equal(
    requests[0].headers["Idempotency-Key"],
    requests[1].headers["Idempotency-Key"],
  );
});
test("ambiguous attempts older than 23 hours are quarantined, not resent", async () => {
  await favorite();
  await stage();
  await due();
  const d = await claim();
  await rpc("mail_prepare", {
    p_delivery_id: d.delivery_id,
    p_lease_token: d.lease_token,
    p_payload: renderDelivery(d, "a@example.test"),
  });
  await db.exec(
    "update public.mailing_deliveries set first_attempt_at=now()-interval '24 hours',lease_until=now()-interval '1 minute'",
  );
  assert.equal(await claim(), null);
  assert.equal(
    (await db.query("select state from public.mailing_deliveries")).rows[0]
      .state,
    "uncertain",
  );
});
test("429 honors Retry-After and stops batch; no false success", async () => {
  await favorite();
  await stage();
  await due();
  let sends = 0;
  const result = await runMailing(env, {
    rpc,
    fetcher: async () => {
      sends++;
      return new Response("", {
        status: 429,
        headers: { "retry-after": "1200" },
      });
    },
  });
  assert.equal(result.accepted, 0);
  assert.equal(sends, 1);
  const row = (
    await db.query(
      "select state,extract(epoch from(next_attempt_at-now())) seconds from public.mailing_deliveries",
    )
  ).rows[0];
  assert.equal(row.state, "retry");
  assert.ok(Number(row.seconds) > 1190);
});
test("preview does not claim, checkpoint or send", async () => {
  await favorite();
  await stage();
  await due();
  const result = await runMailing(
    {},
    {
      rpc,
      fetcher: () => {
        throw Error("must not send");
      },
    },
  );
  assert.equal(result.mode, "preview");
  assert.equal(await count("mailing_deliveries"), 0);
});
test("EO update timestamp alone does not notify; changed summary does", async () => {
  await db.exec(
    "insert into public.executive_orders values(14000,'EO','same',now())",
  );
  await favorite(U, "executive_order", "14000");
  await db.exec(
    "update public.executive_orders set updated_at=now(),summary='same'",
  );
  assert.equal(await count("mailing_outbox"), 0);
  await db.exec("update public.executive_orders set summary='new summary'");
  assert.equal(await count("mailing_outbox"), 1);
});
async function report(id = "r1") {
  await db.query(
    "insert into public.mailing_reports(report_id,source_id,title,summary,url,published_at,commodities) values($1,'usda','Report','Summary','https://example.test/report',now()-interval '1 day',array['wheat','corn']) on conflict(report_id) do update set title=excluded.title",
    [id],
  );
}
test("RSS archive retries and overlapping commodity favorites create one event", async () => {
  await favorite(U, "commodity", "wheat");
  await favorite(U, "commodity", "corn");
  await report();
  await report();
  assert.equal(await count("mailing_reports"), 1);
  assert.equal(await count("mailing_outbox"), 1);
  await due();
  await runMailing(env, { rpc, fetcher: success });
  assert.equal(await count("commodity_report_notifications"), 1);
});
test("legacy report delivery log prevents cutover duplicates", async () => {
  await favorite(U, "commodity", "wheat");
  await db.query(
    "insert into public.commodity_report_notifications(user_id,report_id)values($1,$2)",
    [U, "r1"],
  );
  await report();
  assert.equal(await count("mailing_outbox"), 0);
});
test("disabled RSS source is not mailed", async () => {
  await favorite(U, "commodity", "wheat");
  await report();
  await due();
  await db.query(
    "insert into public.commodity_digest_source_prefs values($1,$2)",
    [U, "usda"],
  );
  assert.equal(await claim(), null);
});
test("queued report is not lost after the former rolling eight-day window", async () => {
  await favorite(U, "commodity", "wheat");
  await report();
  await due();
  await db.exec(
    "update public.mailing_outbox set created_at=now()-interval '20 days'",
  );
  assert.ok(await claim());
});
test("RLS blocks outbox and privileged RPC access for browsers", async () => {
  await db.exec("set role authenticated");
  await assert.rejects(
    db.query("select public.mail_claim()"),
    /permission denied/,
  );
  await assert.rejects(
    db.query("select * from public.mailing_outbox"),
    /permission denied/,
  );
  await db.exec("reset role");
});
test("email HTML escapes source text and rejects script URLs", () => {
  const payload = renderDelivery(
    {
      kind: "policy",
      recipient: "a@example.test",
      items: [
        {
          item_kind: "bill",
          item_id: "1",
          content: {
            title: "<img src=x onerror=1>",
            detail: "<script>x</script>",
            url: "javascript:alert(1)",
            from_stage: "referred",
            to_stage: "reported",
          },
        },
      ],
    },
    "b@example.test",
  );
  assert.ok(payload.html.includes("&lt;img"));
  assert.ok(!payload.html.includes("javascript:"));
  assert.ok(payload.text.includes("위원회 회부 → 위원회 보고"));
});
test("RSS normalizer rejects missing dates/unsafe URLs and truncates summaries", () => {
  const item = {
    id: "r",
    source_id: "s",
    title: { original: "Title" },
    published_at: "2026-09-10",
    url: "https://example.test",
    commodities: ["wheat"],
    summary: "x".repeat(700),
  };
  assert.equal(importer.normalizeReport(item).summary.length, 600);
  assert.equal(
    importer.normalizeReport({ ...item, published_at: undefined }),
    null,
  );
  assert.equal(
    importer.normalizeReport({ ...item, url: "javascript:1" }),
    null,
  );
});
test("new Supabase secret keys do not become invalid Bearer JWTs", async () => {
  let headers;
  const f = createRpc(
    {
      SUPABASE_URL: "https://project.supabase.co",
      SUPABASE_SERVICE_ROLE_KEY: "sb_secret_mock",
    },
    async (_u, o) => {
      headers = o.headers;
      return Response.json({});
    },
  );
  await f("mail_status");
  assert.equal(headers.apikey, "sb_secret_mock");
  assert.equal(headers.Authorization, undefined);
});
test("oversized provider response is bounded", async () => {
  await assert.rejects(
    readJson(new Response("x".repeat(9000)), 8192),
    /response_too_large/,
  );
});

test("preference RPC updates only the caller and preserves the other switch", async () => {
  await db.query("select set_config('request.jwt.claim.sub',$1,false)", [U]);
  await db.exec("set role authenticated");
  try {
    await rpc("set_my_mailing_preference", {
      p_kind: "policy",
      p_enabled: false,
    });
    await rpc("set_my_mailing_preference", {
      p_kind: "commodity",
      p_enabled: false,
    });
    await rpc("set_my_mailing_preference", {
      p_kind: "policy",
      p_enabled: true,
    });
    await assert.rejects(
      rpc("set_my_mailing_preference", { p_kind: null, p_enabled: true }),
      /invalid preference/,
    );
    await assert.rejects(
      db.query(
        "insert into public.mailing_preferences values($1,false,false)",
        [V],
      ),
      /row-level security/,
    );
  } finally {
    await db.exec("reset role");
  }
  const rows = (await db.query("select * from public.mailing_preferences"))
    .rows;
  assert.deepEqual(rows, [
    { user_id: U, policy_enabled: true, commodity_enabled: false },
  ]);
  await db.query("select set_config('request.jwt.claim.sub','',false)");
  await assert.rejects(
    rpc("set_my_mailing_preference", { p_kind: "policy", p_enabled: true }),
    /authentication required/,
  );
});
test("weekly schedule after Monday 08:00 advances to the next Monday", async () => {
  const value = await rpc("mail_next_due", {
    p_kind: "commodity",
    p_at: "2026-09-13T23:00:00Z",
  });
  assert.equal(value.toISOString(), "2026-09-20T23:00:00.000Z");
});
test("report predating subscription and old initial archive do not create backlogs", async () => {
  await favorite(U, "commodity", "wheat");
  await db.exec("update public.user_favorites set created_at=now()");
  await report();
  assert.equal(await count("mailing_outbox"), 0);
  await db.exec(
    "update public.user_favorites set created_at=now()-interval '100 days'",
  );
  await db.exec(
    "insert into public.mailing_reports values('old','usda','Old','Summary','https://example.test/old',now()-interval '30 days',array['wheat'],now())",
  );
  assert.equal(await count("mailing_outbox"), 0);
});
test("batch limit leaves remaining events available for the next delivery", async () => {
  await favorite();
  for (let i = 0; i < 21; i++) await stage(i % 2 ? "reported" : "referred");
  await stage("enacted");
  await due();
  assert.equal(await count("mailing_outbox"), 21);
  const first = await claim(),
    second = await claim();
  assert.equal(first.items.length, 20);
  assert.equal(second.items.length, 1);
  assert.notEqual(first.delivery_id, second.delivery_id);
  assert.equal(await claim(), null);
});
test("re-adding a favorite cannot revive events from a previous subscription", async () => {
  await favorite();
  await stage();
  await due();
  await db.exec("delete from public.user_favorites");
  await db.query(
    "insert into public.user_favorites(user_id,item_kind,item_id)values($1,'bill','119-hr-1')",
    [U],
  );
  assert.equal(await claim(), null);
});
test("malformed reports are rejected rather than dated at the Unix epoch", () => {
  assert.equal(importer.normalizeReport(null), null);
  assert.equal(importer.normalizeReport({ published_at: null }), null);
  assert.equal(
    importer.normalizeReport({
      id: "1",
      source_id: "x",
      title: { original: "t" },
      published_at: "2026-09-10",
      url: "https://example.test",
      commodities: [null],
    }),
    null,
  );
});

test("06:00-06:59 KST batches reserve capacity for policy mail", () => {
  assert.equal(scheduledMailKind("2026-09-10T21:00:00Z"), "policy");
  assert.equal(scheduledMailKind("2026-09-10T21:59:59Z"), "policy");
  assert.equal(scheduledMailKind("2026-09-10T22:00:00Z"), null);
});
