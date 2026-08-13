# Russia export pulse v1

**목적:** 러시아가 흑해 리스크(피격·봉쇄·정책)에 노출됐을 때  
**어느 공식 지표에서 수출량이 빠지는지** 를 스냅샷으로 남긴다.

다크십·피격 AIS·언론 “세계 밀 −15%” 인과는 **넣지 않는다** (무료 공식 데이터로 확인 불가).

## 관측 체인

| 우선 | 지표 | 소스 | 주기 | 역할 |
|------|------|------|------|------|
| 1 | 러시아 밀 **Exports** | USDA FAS PSD CSV zip (무료) | 마케팅연도 | 수출 빠짐 **정본** |
| 1 | 세계 밀 Exports + 러 비중 | 동일 PSD | 마케팅연도 | 세계 교역 **기여분** 환산 |
| 2 | (선택) 해바라기유 등 유지 | PSD oilseeds zip | 마케팅연도 | 에너지·유지 보조 |
| 2 | (선택) HS 월별 | UN Comtrade `freq=M` | 월 | 키 있을 때만 |
| 3 | 보스포루스 dry_bulk | IMF PortWatch | 일→7d/28d | 출구 막힘 **보조** (러 전용 아님) |
| — | 피격·다크십 | — | — | **out of scope** |

기여분 (근사, GE 아님):

```text
implied_world_trade_contribution_pct
  = 100 × (Russia_Exports_t − Russia_Exports_{t−1}) / World_Exports_{t−1}
```

## 실행

```bash
cd "New for anti/scripts/russia_export_pulse"
python3 build_snapshot.py
# PortWatch 포함:
python3 build_snapshot.py --fetch-portwatch
# 해바라기유(선택, 느린 zip):
python3 build_snapshot.py --include-oilseeds
# Comtrade 월별 (키 필요):
COMTRADE_SUBSCRIPTION_KEY=... python3 build_snapshot.py --fetch-comtrade-monthly
```

산출: `../../public/data/russia_export_pulse_v1.json`

## UI

`shipping.js` / `app.js` 는 Claude 소유. 이 패키지는 JSON만 만든다.  
화면 배선은 Claude 핸드오프(PR 노트)로.

## 한계 (정직하게)

- PSD는 **시즌(마케팅연도)** 단위. “이번 주 피격”을 바로 찍지 않는다.
- 보스포루스 벌크는 흑해 **전체** 통과량이다.
- 휘발유 수출금지는 `config/policy_events.json` 이벤트 레이어 (톤수 시계열은 Comtrade 키가 있을 때만).
