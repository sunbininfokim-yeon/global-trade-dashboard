// During 06:00-06:59 KST reserve the entire bounded batch for policy mail.
/** @returns {"policy" | null} */
export function scheduledMailKind(timestamp) {
  return new Date(timestamp).getUTCHours() === 21 ? "policy" : null;
}
// Shared by the scheduled Worker and explicit operator CLI. No implicit sends.
const STAGES = {
  introduced: "발의",
  referred: "위원회 회부",
  subcommittee: "소위원회",
  committee_consideration: "위원회 심사",
  reported: "위원회 보고",
  passed_origin_chamber: "발의 원 통과",
  second_chamber: "다른 원 심사",
  resolving_differences: "양원 이견 조정",
  passed_both_chambers: "양원 통과",
  presented_to_president: "대통령 송부",
  enacted: "법률 제정",
  vetoed: "거부권 행사",
  failed: "부결",
  other: "기타",
};
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
export function safeLink(value) {
  try {
    const u = new URL(value);
    return ["http:", "https:"].includes(u.protocol) ? u.href : null;
  } catch {
    return null;
  }
}
export function renderDelivery(delivery, from) {
  if (!from || /[\r\n]/.test(from)) throw new Error("invalid_sender");
  const rows = delivery.items.map((item) => {
    const c = item.content;
    const title = String(c.title || item.item_id).slice(0, 1000);
    const stage =
      item.item_kind === "bill"
        ? `${STAGES[c.from_stage] || c.from_stage || "이전 상태"} → ${STAGES[c.to_stage] || c.to_stage || "변경 상태"}`
        : item.item_kind === "executive_order"
          ? "공식 요약 변경"
          : c.source_id;
    const detail = String(c.detail || "").slice(0, 600);
    const url = safeLink(c.url);
    return {
      text: `${title}\n${stage || ""}\n${detail}${url ? `\n${url}` : ""}`,
      html: `<li><strong>${esc(title)}</strong><br>${esc(stage)}<br>${esc(detail)}${url ? `<br><a href="${esc(url)}">원문·상세 보기</a>` : ""}</li>`,
    };
  });
  const title =
    delivery.kind === "policy"
      ? "즐겨찾기 정책 변경 알림"
      : "주간 원자재 보고서";
  return {
    from,
    to: delivery.recipient,
    subject: `[ChokePoint Monitor] ${title} ${rows.length}건`,
    text: `${title}\n\n${rows.map((r) => r.text).join("\n\n")}\n\n수신 설정: https://chokemonitor.com/mypage`,
    html: `<div lang="ko"><h2>${esc(title)}</h2><ul>${rows.map((r) => r.html).join("")}</ul><p><a href="https://chokemonitor.com/mypage">메일 수신 설정</a></p></div>`,
  };
}

// Bound response bodies; never log emails, tokens, SQL or provider error bodies.
export async function readJson(response, maxBytes = 256 * 1024) {
  if (!response.body) throw new Error("empty_response");
  const reader = response.body.getReader(),
    chunks = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maxBytes) {
        await reader.cancel();
        throw new Error("response_too_large");
      }
      chunks.push(value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const part of chunks) {
      bytes.set(part, offset);
      offset += part.length;
    }
    return JSON.parse(new TextDecoder().decode(bytes));
  } finally {
    reader.releaseLock();
  }
}
export function createRpc(env, fetcher = fetch) {
  const url = new URL(env.SUPABASE_URL),
    key = env.SUPABASE_SERVICE_ROLE_KEY;
  if (url.protocol !== "https:") throw new Error("invalid_supabase_url");
  if (!key) throw new Error("missing_supabase_key");
  return async (name, args = {}) => {
    const response = await fetcher(`${url.origin}/rest/v1/rpc/${name}`, {
      method: "POST",
      headers: {
        apikey: key,
        ...(key.startsWith("eyJ") ? { Authorization: `Bearer ${key}` } : {}),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(args),
      signal: AbortSignal.timeout(20000),
    });
    if (!response.ok) {
      await response.body?.cancel();
      throw new Error(`database_http_${response.status}`);
    }
    return readJson(response);
  };
}
function retrySeconds(value, now) {
  const seconds = Number(value);
  if (value && Number.isFinite(seconds))
    return Math.max(60, Math.ceil(seconds));
  const ms = Date.parse(value || "") - now;
  return ms > 0 ? Math.max(60, Math.ceil(ms / 1000)) : 600;
}
export async function runMailing(
  env,
  {
    rpc = createRpc(env),
    fetcher = fetch,
    kind = /** @type {"policy" | "commodity" | null} */ (null),
    maxDeliveries = 5,
    now = Date.now,
  } = {},
) {
  if (env.MAIL_SEND_ENABLED !== "true")
    return { mode: "preview", ...(await rpc("mail_status")) };
  if (!env.RESEND_API_KEY) throw new Error("missing_resend_key");
  const sender = env.NOTIFY_FROM_EMAIL || "alerts@chokemonitor.com";
  if (/[\r\n]/.test(sender)) throw new Error("invalid_sender");
  const limit = Math.min(5, Math.max(1, Number(maxDeliveries) || 5));
  const stats = {
    mode: "send",
    claimed: 0,
    accepted: 0,
    failed: 0,
    cancelled: 0,
  };
  for (let i = 0; i < limit; i++) {
    const d = await rpc("mail_claim", { p_kind: kind });
    if (!d) break;
    stats.claimed++;
    const ref = { p_delivery_id: d.delivery_id, p_lease_token: d.lease_token };
    // Persist and reuse the exact request across template/from changes.
    const candidate = d.request_payload || renderDelivery(d, sender);
    const payload = await rpc("mail_prepare", { ...ref, p_payload: candidate });
    if (!payload) {
      stats.cancelled++;
      continue;
    }
    let response;
    try {
      response = await fetcher("https://api.resend.com/emails", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.RESEND_API_KEY}`,
          "Content-Type": "application/json",
          "Idempotency-Key": `mailing/${d.delivery_id}`,
        },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(20000),
      });
    } catch {
      await rpc("mail_fail", {
        ...ref,
        p_state: "retry",
        p_error_code: "provider_network_ambiguous",
        p_retry_seconds: 600,
      });
      stats.failed++;
      continue;
    }
    if (!response.ok) {
      const status = response.status,
        retry = [408, 425, 429].includes(status) || status >= 500;
      const delay = retrySeconds(response.headers.get("retry-after"), now());
      await response.body?.cancel();
      await rpc("mail_fail", {
        ...ref,
        p_state: retry ? "retry" : "failed",
        p_error_code: `provider_http_${status}`,
        p_retry_seconds: delay,
      });
      stats.failed++;
      if ([401, 403, 429].includes(status)) break;
      continue;
    }
    let data;
    try {
      data = await readJson(response, 8192);
      if (typeof data.id !== "string" || !data.id) throw new Error();
    } catch {
      await rpc("mail_fail", {
        ...ref,
        p_state: "retry",
        p_error_code: "provider_response_ambiguous",
        p_retry_seconds: 600,
      });
      stats.failed++;
      continue;
    }
    // Lost DB acknowledgement leaves the lease intact. Retry the SAME job/key.
    const recorded = await rpc("mail_complete", {
      ...ref,
      p_message_id: data.id,
    });
    if (!recorded) throw new Error("delivery_checkpoint_conflict");
    stats.accepted++;
  }
  return { ...stats, queue: await rpc("mail_status") };
}
