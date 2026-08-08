# China Macro Kit (`cn_macro_v1`)

PBOC **구조적 유동성**(금리보다 총량·RRR) · **부동산/LGFV** · **PPI 디플레 수출** 파급 추적.

## 핵심 칩

| id | 의미 |
|----|------|
| `tsf_yoy` | 사회융자총량 — 최광의 신용 (**최중요**) |
| `rrr` | 지급준비율 |
| `m1_m2_spread` | M1−M2 가위표 (유동성 함정) |
| `lpr_1y` / `lpr_5y` | 기업대출 / 모기지 기준 |
| `us_chn_10y_spread` | 미−중 10Y (유출 압력) |
| `lgfv_spread` / `cn_hy_prop_spread` | 지방부채 · 부동산 $HY |
| `usdcny` / `usdcnh` / `pboc_fixing` | 역내·역외·고시 |
| `ppi_yoy` | 글로벌 디플레 수출 신호 |

## 한계 (4)

공식통계 평활 · LGFV/그림자 불확실 · M2↑+디플레 공존 · 정책 외생변수

API: [`DATA_SOURCES.md`](./DATA_SOURCES.md) §중국
