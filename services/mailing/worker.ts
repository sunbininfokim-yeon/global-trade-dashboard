import { runMailing, scheduledMailKind } from "./core.mjs";
export default {
  async scheduled(_controller, env, _ctx) {
    const result = await runMailing(env, {
      kind: scheduledMailKind(_controller.scheduledTime),
    });
    console.log(JSON.stringify({ event: "mailing_run", ...result }));
    if (
      "queue" in result &&
      (Number(result.queue?.policy_past_7am) > 0 ||
        Number(result.queue?.states?.uncertain) > 0 ||
        Number(result.queue?.states?.failed) > 0)
    ) {
      console.warn("mailing_queue_needs_attention");
    }
    if (result.failed) throw new Error("mailing_delivery_failed");
  },
  async fetch() {
    return new Response("Not found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;
