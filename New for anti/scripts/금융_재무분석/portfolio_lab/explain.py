"""Plain-language Korean / English copy for the finance UI (no return forecasts)."""

from __future__ import annotations

from typing import Any


def _pct(x: float | None, digits: int = 1) -> str:
    if x is None:
        return "—"
    return f"{100.0 * float(x):.{digits}f}%"


def _krw(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{float(x):,.0f}원"


def _krw_en(x: float | None) -> str:
    if x is None:
        return "—"
    return f"about {float(x):,.0f} KRW"


def build_ui_copy(
    report: dict[str, Any],
    *,
    profile: dict[str, Any],
    profile_id: str,
) -> dict[str, Any]:
    """Human-readable Korean blocks the UI can render as-is."""
    perf = report["performance"]
    risk = report["risk"]
    structure = report["structure"]
    advice = report["advice"]
    profile_check = report.get("profile_check") or {}

    vol = perf.get("ann_volatility_short")
    sharpe = perf.get("sharpe_short")
    var10 = risk["short"].get("var_10d_95")
    var10_krw = risk["short"].get("var_10d_95_krw")
    r1y = (perf.get("horizon_returns") or {}).get("1Y")

    rc = structure.get("risk_contribution") or {}
    top_risk = max(rc.items(), key=lambda kv: kv[1]) if rc else None

    headline_bits = []
    if top_risk and top_risk[1] >= 0.35:
        headline_bits.append(
            f"종목은 여러 개여도, 전체 변동의 약 {_pct(top_risk[1], 0)}가 "
            f"'{top_risk[0]}'에서 나옵니다."
        )
    breaches = profile_check.get("breaches_ko") or []
    if breaches:
        headline_bits.append(
            "선택하신 투자 성향 기준으로는, 한도보다 공격적인 부분이 있습니다."
        )
    else:
        headline_bits.append("선택하신 투자 성향 한도는 대체로 지키는 편입니다.")

    metric_cards = [
        {
            "id": "vol",
            "title_ko": "변동성 (연환산)",
            "value_ko": _pct(vol),
            "plain_ko": (
                f"한 해 기준으로 보면, 포트폴리오 가치가 대략 ±{_pct(vol)} 범위에서 "
                "움직일 수 있다는 뜻입니다. 숫자가 클수록 가격이 더 크게 왔다 갔다 합니다."
            ),
            "analogy_ko": "수익률이 얼마나 크게 흔들리는지를 보여주는 눈금입니다.",
        },
        {
            "id": "sharpe",
            "title_ko": "샤프 비율",
            "value_ko": f"{sharpe:.2f}" if sharpe is not None else "—",
            "plain_ko": (
                "예금·국채 수준을 웃돈 수익을, 변동성으로 나눈 값입니다. "
                "1 근처면 괜찮은 편으로 보는 경우가 많지만, 최근에 잘 간 자산에 많이 실리면 "
                "자연히 높아질 수 있습니다. 앞으로의 보장은 아닙니다."
            ),
            "analogy_ko": "같은 위험을 감수했을 때 얼마나 효율적으로 수익을 냈는지 비교하는 지표입니다.",
        },
        {
            "id": "var10",
            "title_ko": "10일 VaR (95%)",
            "value_ko": f"{_pct(var10)} · 약 {_krw(var10_krw)}",
            "plain_ko": (
                "최근과 비슷한 장세라면, 앞으로 약 2주(10거래일) 동안 "
                "이 정도까지 손실이 날 수 있다고 보는 눈금입니다. "
                "내일 꼭 이만큼 잃는다는 뜻은 아닙니다."
            ),
            "analogy_ko": "‘이 정도까지는 감수할 준비가 됐는지’를 가늠해 보는 참고 숫자입니다.",
        },
        {
            "id": "ret1y",
            "title_ko": "최근 1년 수익률",
            "value_ko": _pct(r1y),
            "plain_ko": (
                "오늘 기준으로 거슬러 약 1년(거래일) 동안의 누적 수익률입니다. "
                "달력 연도(1월~12월)가 아니라, ‘지금 시점에서 본 지난 1년’입니다."
            ),
            "analogy_ko": "이미 지나간 성적이지, 앞으로의 예상이 아닙니다.",
        },
    ]

    how_to_read = [
        "비중(%) = 어디에 돈을 넣었는지",
        "위험 기여(%) = 계좌 변동에 실제로 얼마나 영향을 주는지 (비중과 다를 수 있음)",
        "샤프·수익률 = 과거 성적 · VaR·변동성 = 손실·흔들림 규모",
        "아래 ‘조절 제안’은 미래 수익 예상이 아니라, 위험을 더 고르게 나누는 방향입니다",
        "목표 수익률은 넣지 않습니다. 기대수익 가정이 틀리기 쉽기 때문입니다",
    ]

    move_up = []
    move_down = []
    for name, dw in (advice.get("delta_weights") or {}).items():
        if dw >= 0.015:
            move_up.append(
                {
                    "name_ko": name,
                    "delta": dw,
                    "plain_ko": (
                        f"위험이 한곳에 몰리는 걸 줄이려면 '{name}' 비중을 "
                        f"상대적으로 키우는 방향입니다 (+{_pct(dw)}p)."
                    ),
                }
            )
        elif dw <= -0.015:
            move_down.append(
                {
                    "name_ko": name,
                    "delta": dw,
                    "plain_ko": (
                        f"변동이 여기에 몰려 있어, '{name}' 비중을 줄이면 "
                        f"분산에 도움이 됩니다 ({_pct(dw)}p)."
                    ),
                }
            )
    move_up.sort(key=lambda x: -x["delta"])
    move_down.sort(key=lambda x: x["delta"])

    clusters = structure.get("clusters") or []
    cluster_plain = []
    for c in clusters:
        if c.get("weight_sum", 0) >= 0.15:
            members = ", ".join(c.get("members_ko") or [])
            cluster_plain.append(
                f"‘{c.get('label_ko')}'({members})이 함께 움직이는 편이라, "
                f"종목 수와 달리 사실상 한 덩어리 위험(합 비중 약 {_pct(c.get('weight_sum'))})일 수 있습니다."
            )

    fx = structure.get("currency_exposure") or {}
    fx_plain = (
        f"원화에 직접 묶인 비중 약 {_pct(fx.get('krw_weight'))}, "
        f"달러·환산 자산 등 외화 쪽 약 {_pct(fx.get('foreign_weight'))}입니다. "
        "달러 현금도 안전자산처럼 보여도, 환율만큼은 흔들립니다."
    )

    stress = report.get("stress") or {}
    stress_plain = []
    for s in stress.get("windows") or []:
        stress_plain.append(
            f"{s['label_ko']}: 그 구간에 지금 비중을 유지했다고 가정하면 약 {_pct(s.get('portfolio_return'))} "
            f"(참고용 · 당시 매매는 반영하지 않음)"
        )

    return {
        "headline_ko": " ".join(headline_bits),
        "profile": {
            "id": profile_id,
            "label_ko": profile.get("label_ko"),
            "blurb_ko": profile.get("blurb_ko"),
        },
        "how_to_read_ko": how_to_read,
        "metric_cards": metric_cards,
        "risk_contribution_plain_ko": (
            f"지금 계좌 변동에 가장 큰 영향을 주는 것은 '{top_risk[0]}'입니다 "
            f"(위험 기여 {_pct(top_risk[1])})."
            if top_risk
            else "위험 기여를 계산하지 못했습니다."
        ),
        "clusters_plain_ko": cluster_plain,
        "currency_plain_ko": fx_plain,
        "stress_plain_ko": stress_plain,
        "profile_breaches_ko": breaches,
        "moves_up_ko": move_up[:4],
        "moves_down_ko": move_down[:4],
        "footer_ko": (
            "이 화면의 숫자는 과거 가격으로 돌린 계산 결과입니다. "
            "매수·매도 지시가 아니며, "
            "‘위험이 어디에 몰렸는지’를 보는 데 초점이 있습니다."
        ),
        "rebalance_note_ko": (
            "비중을 옮길 때는 수수료·세금·환전 비용이 있으니, "
            "제안 %를 한 번에 맞추기보다 큰 쏠림부터 줄이는 편이 현실적입니다."
        ),
    }


def build_ui_copy_en(
    report: dict[str, Any],
    *,
    profile: dict[str, Any],
    profile_id: str,
) -> dict[str, Any]:
    """Human-readable English blocks — schema parallel to ui_copy_ko (_en vs _ko)."""
    perf = report["performance"]
    risk = report["risk"]
    structure = report["structure"]
    advice = report["advice"]
    profile_check = report.get("profile_check") or {}

    vol = perf.get("ann_volatility_short")
    sharpe = perf.get("sharpe_short")
    var10 = risk["short"].get("var_10d_95")
    var10_krw = risk["short"].get("var_10d_95_krw")
    r1y = (perf.get("horizon_returns") or {}).get("1Y")

    rc = structure.get("risk_contribution") or {}
    top_risk = max(rc.items(), key=lambda kv: kv[1]) if rc else None

    headline_bits = []
    if top_risk and top_risk[1] >= 0.35:
        headline_bits.append(
            f"Money may look spread around, but about {_pct(top_risk[1], 0)} of the "
            f"portfolio’s swings come from '{top_risk[0]}'."
        )
    breaches = profile_check.get("breaches_en") or []
    if breaches:
        headline_bits.append(
            "Against the risk style you picked, some limits look more aggressive than intended."
        )
    else:
        headline_bits.append("You’re broadly inside the limits for the risk style you picked.")

    metric_cards = [
        {
            "id": "vol",
            "title_en": "How bumpy it feels (volatility)",
            "value_en": _pct(vol),
            "plain_en": (
                f"A thermometer for how much the portfolio might wobble — roughly ±{_pct(vol)} "
                "over a year in either direction. Bigger number, more stomach-churn."
            ),
            "analogy_en": "Closer to ‘how rough is the road?’ than to how fast the car is going.",
        },
        {
            "id": "sharpe",
            "title_en": "Payoff for the hassle (Sharpe)",
            "value_en": f"{sharpe:.2f}" if sharpe is not None else "—",
            "plain_en": (
                "How much you earned above a cash-like rate, divided by how hard it bounced. "
                "Near 1 is often called decent — but a run of strong assets can inflate it. "
                "Not a promise about the future."
            ),
            "analogy_en": "A scorecard for reward per unit of motion sickness (risk).",
        },
        {
            "id": "var10",
            "title_en": "How sore it could get (10-day VaR 95%)",
            "value_en": f"{_pct(var10)} · {_krw_en(var10_krw)}",
            "plain_en": (
                "If markets behave a bit like recently, a loss of this size over about two weeks "
                "is in the ‘bad but not unheard-of’ bucket. It does not mean you will lose "
                "exactly this much tomorrow."
            ),
            "analogy_en": "Like an insurance deductible — ‘could you live with a hit this big?’",
        },
        {
            "id": "ret1y",
            "title_en": "Last 1-year score",
            "value_en": _pct(r1y),
            "plain_en": (
                "Cumulative return over roughly the past year of trading days, counted backward "
                "from today — not a calendar year (Jan 1–Dec 31)."
            ),
            "analogy_en": "Last semester’s grade — not next semester’s forecast.",
        },
    ]

    how_to_read = [
        "Weight (%) = where the money sits",
        "Risk contribution (%) = who actually shakes the account (can differ from weight)",
        "Sharpe & return = past scorecard · VaR & volatility = how painful it can get",
        "‘Suggested moves’ below are about spreading risk more evenly — not a jackpot forecast",
        "No target return is used; expected-return guesses go wrong easily",
    ]

    move_up = []
    move_down = []
    for name, dw in (advice.get("delta_weights") or {}).items():
        if dw >= 0.015:
            move_up.append(
                {
                    "name_en": name,
                    "delta": dw,
                    "plain_en": (
                        f"To pile less risk in one place, leaning relatively more into '{name}' "
                        f"is the direction (+{_pct(dw)}p)."
                    ),
                }
            )
        elif dw <= -0.015:
            move_down.append(
                {
                    "name_en": name,
                    "delta": dw,
                    "plain_en": (
                        f"Swings are concentrated here — trimming '{name}' helps diversification "
                        f"({_pct(dw)}p)."
                    ),
                }
            )
    move_up.sort(key=lambda x: -x["delta"])
    move_down.sort(key=lambda x: x["delta"])

    clusters = structure.get("clusters") or []
    cluster_plain = []
    for c in clusters:
        if c.get("weight_sum", 0) >= 0.15:
            members = ", ".join(c.get("members_ko") or [])
            label = c.get("label_en") or c.get("label_ko") or "cluster"
            cluster_plain.append(
                f"The '{label}' group ({members}) tends to move together, so despite several "
                f"tickers it can act like one lump of risk (combined weight about "
                f"{_pct(c.get('weight_sum'))})."
            )

    fx = structure.get("currency_exposure") or {}
    fx_plain = (
        f"About {_pct(fx.get('krw_weight'))} is tied directly to the won; about "
        f"{_pct(fx.get('foreign_weight'))} sits in dollar / FX-exposed assets. "
        "Even ‘safe’ USD cash still moves with the exchange rate."
    )

    stress = report.get("stress") or {}
    stress_plain = []
    for s in stress.get("windows") or []:
        label = s.get("label_en") or s.get("label_ko") or s.get("id")
        stress_plain.append(
            f"{label}: holding today’s weights through that window would have been about "
            f"{_pct(s.get('portfolio_return'))} (illustrative — ignores trades you made then)"
        )

    return {
        "headline_en": " ".join(headline_bits),
        "profile": {
            "id": profile_id,
            "label_en": profile.get("label_en") or profile.get("label_ko"),
            "blurb_en": profile.get("blurb_en") or profile.get("blurb_ko"),
        },
        "how_to_read_en": how_to_read,
        "metric_cards": metric_cards,
        "risk_contribution_plain_en": (
            f"What shakes the account most right now is '{top_risk[0]}' "
            f"(risk contribution {_pct(top_risk[1])})."
            if top_risk
            else "Could not compute risk contribution."
        ),
        "clusters_plain_en": cluster_plain,
        "currency_plain_en": fx_plain,
        "stress_plain_en": stress_plain,
        "profile_breaches_en": breaches,
        "moves_up_en": move_up[:4],
        "moves_down_en": move_down[:4],
        "footer_en": (
            "Numbers here are a calculator on past prices — not buy/sell orders. "
            "The point is less like a broker order ticket and more like seeing "
            "where risk has piled up."
        ),
        "rebalance_note_en": (
            "Moving weights costs fees, taxes, and FX spreads — so trimming the biggest "
            "concentrations first usually beats chasing every suggested percent in one go."
        ),
    }
