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

## 주식 — A / B / H / 후·선강통

중국 주식은 **한 지수가 아니다.** 시장·통화·투자자 풀이 갈린다.

| 구분 | 뭐냐 | 이 키트 | 빗대면 |
|------|------|---------|--------|
| **A주** | 상해·선전 역내, **CNY**, 본토 투자자 중심 | `sse_composite` · `csi300` | 코스피 / SPX(대형=`CSI300`) |
| **B주** | 과거 외국인용(상해 USD·선전 HKD). **거의 사장** | **칩 없음** (유동성 없어 매크로 신호 약함) | QFII·Connect 이전 유물 |
| **H주** | 홍콩 상장 중국기업, **HKD** | `hscei` | 해외상장/ADR 슬롯. 같은 회사여도 A와 가격 괴리 |
| **후강통·선강통** | HK↔역내 A 연결 | `northbound_flow`(홍콩→A) · `southbound_flow`(본토→HK) | 한국 외국인 순매수 / 거주자 해외주식 |

배치: **A주(상해종합→CSI300) → H주(HSCEI) → 북향→남향**.

## 한계 (4)

공식통계 평활 · LGFV/그림자 불확실 · M2↑+디플레 공존 · 정책 외생변수

API: [`DATA_SOURCES.md`](./DATA_SOURCES.md) §중국
