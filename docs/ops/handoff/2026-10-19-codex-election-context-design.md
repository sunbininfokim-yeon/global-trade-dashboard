# 2026-10-19 — Silver / Cook / 270toWin 선거 맥락 설계 검토

담당 Codex. 최신 main `58babc59`에서 독립 분기한 `codex/us-election-context-20261019`. 사용자는 Silver·팟캐스트·Cook 연결 가능성, 후보 약력과 유권자 인구 특성, 270toWin 구조 검토, 주지사 선거 대상과 연임 제한을 요청했다. 이 문서는 실제 공개 자료를 대조한 설계 인수이며 구현·자동 수집·배포 완료 보고가 아니다. 기존 polling 확대 PR과 분리한다.

## 1. 출처마다 서로 다른 역할

| 출처 | 쓸 수 있는 내용 | 집계 규칙 / 현재 접근 |
|---|---|---|
| [Silver FLIPR](https://www.natesilver.net/p/nate-silver-2026-midterm-election-polls-model) | 외부 모델의 전망, 조사 원문 발견 | 공개 소개·방법론 확인. 상세 전망은 유료 영역이며 공개 API나 재배포 권한을 확인하지 못했다. 값은 null/접근 제한으로 둔다. 원시 여론조사로 세지 않는다. |
| [FLIPR 방법론](https://www.natesilver.net/p/flipr-midterms-model-methodology) | 조사·기초 변수·전문가 등급을 분리하는 설계 참고 | 알고리즘·가중치·승률을 복제했다고 주장하지 않는다. Lite에도 무조사 선거 추정이 들어가므로 실측 조사와 동일하지 않다. |
| [Still Counting 공식 페이지](https://www.crooked.com/podcast-series/still-counting/) / [공식 RSS](https://audioboom.com/channels/5174627.rss) | 새 방송 제목·날짜·설명·원문 링크를 조사 발견 큐로 | 페이지가 직접 연결하는 RSS 주소를 실제 HTML에서 확인. RSS 자체 수집·음성 전사·정기 실행은 아직 구현하지 않았다. 발언은 원문 검토 전 참고 의견이며 조사 한 건이 아니다. |
| [Cook 주지사 등급](https://www.cookpolitical.com/ratings/governor-race-ratings) | 출처·기준일을 붙인 전문가 등급 | 이번 원문 요청403. 기존 Cook 등급 경로와 별도 비교 필요. 접근 실패를 최신 등급으로 채우지 않는다. |
| [270toWin 주지사](https://www.270towin.com/2026-governor-election/) | 현재/선거 대상/선거 후 구분, 연도 탭, 후보·현직 분리 | 기능·정보 구조 참고. HTML200. 자체 코드·유료 모델 복제 또는 합의 등급을 Cook 단독 등급으로 바꾸는 작업은 하지 않는다. |
| [NYT 조사 목록](https://www.nytimes.com/interactive/polls/latest-polls.html) | Silver가 주요 조사 공급원으로 직접 명시한 추가 발견 경로 | 이번 공개 페이지 읽기 실패. 공개 다운로드/API·이용 조건을 확인하기 전 자동 연동 성공으로 기록하지 않는다. |

팟캐스트 → 조사 발견 항목(URL·방송 GUID·공개일·타임스탬프) → 조사기관/의뢰기관 원문 확인 → 기존 정확한 문서 지문·후보·표본·기간·문항 검토 → 중복 파동 제거 → 여론조사 집계 순서다. 방송·NYT·270toWin·API가 같은 조사를 언급해도 조사 한 건으로 센다. 외부 전망은 `external_forecasts[]`, 전문가 등급은 `expert_ratings[]`, 조사값은 기존 `observations[]`, 해설은 `commentary[]`로 분리한다. 베팅 지표는 기존 사용자 지시대로 후순위다.

## 2. 270toWin 구조를 우리 화면/백엔드에 적용하는 계약

현재 인원/의석, 이번 선거 대상, 선거 후 전망을 각각 다른 합계로 제공한다. 상원은100석 = 비선거65 + 선거35(FL·OH 특별선거 포함), 주지사는50 = 비선거14 + 선거36이다. 하원은 주 색이 아니라435개 지역구 단위다. 독립 후보·공석·결과 미확정은 D/R에 임의 편입하지 않는다. 외부 전문가 등급과 최근7/14일 실제 조사 우세는 별도 기준을 표시한다.

상단 박스는 ‘현황 / 선거 대상 / 전망’이고 클릭 목록은 같은 집계의 정확한 race_id를 사용한다. 주별 상세는 `현직(상원2명)` → `이번 본선 후보` → `최근 조사 지지율` → `후보별 지지/반대 외부지출` → `검증된 약력` 순서다. 현직의 연임 제한은 후보가 없는 이유와 구별하여 선거 맥락에 표시한다. 이번 작업은 UI 변경을 포함하지 않는다.

권장 맥락 예시:

```json
{
  "race_id": "USA:OH:governor",
  "election_in_cycle": true,
  "election_date": "2026-11-03",
  "incumbent": {"name": "Mike DeWine", "status": "term_limited_reported"},
  "eligibility_source": "https://www.nga.org/governors/elections/",
  "legal_rule_source": "https://codes.ohio.gov/ohio-constitution/section-3.2",
  "candidates": [],
  "expert_ratings": [], "external_forecasts": [], "commentary": []
}
```

위 빈 candidates는 계약 예시이며 OH 실제 후보가 없다는 뜻이 아니다. 후보 신원은 기존 `governor_matchups/2026.json`, `federal_matchups/2026.json`의 해당 주별 검토 명부에서 연결한다. 분석 사이트 후보와 명부가 다르면 새 이름으로 덮어쓰지 않고 별도 보류·공식 원문 재검토로 남긴다.

## 3. 주지사 선거 대상과 현직 연임 제한

[NGA 선거 원문](https://www.nga.org/governors/elections/)을 실제 요청해200을 받았다. 페이지의39건에는 미국령GU·MP·VI3곳이 포함된다. 2026년 링크가 붙은 panel만 추출하고50주 catalog와 교차 검증한 결과36개 주가 기존 governor_states와 정확히 일치했다. 과거2022/2024 결과를 현재 선거로 읽지 않았다.

- 2026년 선거36개 주: **AK, AL, AR, AZ, CA, CO, CT, FL, GA, HI, IA, ID, IL, KS, MA, MD, ME, MI, MN, NE, NH, NM, NV, NY, OH, OK, OR, PA, RI, SC, SD, TN, TX, VT, WI, WY**
- 2026년 주지사 선거가 없는14개 주: **DE, IN, KY, LA, MO, MS, MT, NC, ND, NJ, UT, VA, WA, WV**
- 현직 연임 제한15개 주: **AK, AL, CA, CO, FL, GA, KS, ME, MI, NM, OH, OK, SC, TN, WY**

연임 제한은 ‘이 주는 선거가 없다’는 뜻이 아니라 새 후보가 경쟁하는 열린 선거라는 뜻이다. 위15개는 NGA의 해당2026 panel에 붙은 Term Limited 표시를 근거로 하며,50개 주 헌법을 모두 법률 검토했다는 뜻이 아니다. [오하이오 헌법III§2](https://codes.ohio.gov/ohio-constitution/section-3.2)는 주지사의 연속 두 번4년 임기 제한을 직접 확인했다(웹 원문 읽기 성공, 직접HTTP 요청은 별도 장애 기록). 다른 주의 평생/연속 제한 유형까지 추정해 옮기지 않는다. NGA도 CA의 최대 임기를 ‘consecutive’로 설명하지만 법률 유형까지 복사할 근거로 쓰지 않는다.

자진 불출마(IA Reynolds·MN Walz·WI Evers)와 경선 탈락(RI McKee)은270toWin의 명시적 노트이며 위15개 연임 제한과 구분한다. 이 네 사유의 공식 당사자 발표·주별 선거 결과 확인은 후속 구현 전에 보강한다. NH·VT는2년 임기이므로2028년에도 선거가 있다. 이 선거표는2026년 한정이며 미래 특별선거·법 변경 자동 감지를 구현한 것은 아니다.

## 4. 후보 약력과 유권자 인구통계는 별도

후보 비교에는 생년월일(근거 정밀도 유지, 나이는 기준일로 계산), 군 복무(군종·기간·확인된 계급), 직업/산업 경력, 교육, 공직 이력이 유용하다. 인종·민족은 본인의 공개 자기소개·공식 약력 등 명시 근거가 있을 때만 저장하며 이름·사진·출생국으로 추정하지 않는다. 군 경력이 약력에 없다고 `served=false`로 채우지 않는다.

권장 per-field 계약은 `value`, `status: verified|self_reported|not_verified|source_unavailable`, `source_url`, `reviewed_on`, `evidence_locator`, `source_document_sha256`다. 날짜 정밀도가 연도뿐이면 생일을1월1일로 생성하지 않는다. source outage는 기존 유효 사실과 원래 검토일을 보존한다. 한 주의 후보 약력 입력은 그 주 전용 파일/PR에 두고 전국 생성물을 커밋하지 않는다.

확인한 원문 예시(후보 전수 수집 완료가 아님):

- [Sherrod Brown 의회 공식 약력](https://history.house.gov/People/Detail/9996):1952-11-09생, Ohio State 교수1979–1981, 주의회·주 국무장관·연방 하원·상원 경력.2026-10-19기준73세. 군 복무·인종 정보는 이 원문에서 확인되지 않아null.
- [Jon Husted 상원 공식 약력](https://www.husted.senate.gov/about/):Dayton-Area Chamber of Commerce 경제개발 부대표, 주 하원·상원·국무장관·부지사,2025년1월 상원 취임. 이 페이지에서 생년월일·군 경력은 확인되지 않아null. 웹 읽기와 직접HTTP 실패를 구분한다.
- [Amy Acton 캠프 약력](https://actonforgovernor.com/meet-amy/):의사·공중보건·대학 교수·2019년 보건국장 경력. 당사자 캠프 서술로 귀속하며 정책 성과·칭찬 표현은 객관적인 성과 점수로 옮기지 않는다. 가족의 제철소 경력을 후보 본인의 제철소 직업으로 바꾸지 않는다.
- [Mike DeWine NGA 약력](https://www.nga.org/governors/ohio/):1947-01-05생, 가족 종자회사에서 일한 경험과 공직 경력을 서술한다. 현직 연임 제한 설명용이며2026 본선 후보로 추가하지 않는다. 종자회사 경험을 검증 없는 ‘전업 농부’ 표지로 바꾸지 않는다.
- [John James 하원 공식 약력](https://james.house.gov/about/):8년 현역 복무, Ranger 자격의 항공장교·Apache 소대 지휘 경력, James Group 사장과 Detroit 물류회사 CEO 이력. 군 복무와 지역 산업 경력이라는 두 종류의 검증 가능한 사실을 함께 표시할 수 있다. 이를 특정 유권자 집단의 지지나 당선 가산점으로 해석하지 않는다.

지역 맥락을 함께 넣는다면 후보 약력과 분리한 Census ACS/CVAP의 연령·교육·인종/민족·산업/직업 분포가 적절하다. 총주민·투표연령인구·시민권 가진 투표연령인구·등록유권자는 서로 다른 분모다. 연도·지역경계·표본오차·소집단 표본을 보존하고 Census 인구 비중을 정당 투표율이나 득표 의향으로 바꾸지 않는다. 현재는 이 통계를 새로 수집하거나 예측 모델에 넣지 않았다. 인구/직업 정보는 해설용으로 시작하고, 실제 검증 전 당선확률 가중치로 쓰지 않는 것이 적절하다.

## 5. 구현 순서와 남은 접근 문제

1. 현재 진행 중인 실제 조사 확대를 독립 PR로 검증한다. 이는 Silver 모델 복제와 별개다.
2. 기존 주지사36·상원35 선거 universe 위에50주 선거 유무/연임 제한/불출마 사유 계약을 추가한다. 현직과 후보를 별개 identity로 보존한다.
3. 상원·주지사 후보 약력 필드를 주별 입력으로 보강한다. NY·TN·GA·FL 및 경합주 우선, 공식 자료가 없는 필드는null/검토 대기로 공개한다.
4. Still Counting RSS와 공개 기사/등급 목록은 discovery 큐로 연결하고 정확한 원문 조사만 기존 수집기에 편입한다. 방송의 최신화와 실제 여론조사 승인·배포는 별도 상태다.
5. Cook/NYT403·읽기 실패와 Silver 유료 상세는 접근/재배포 허용 경로가 확인된 후 추가한다. 지금 새로운 API key가 필요한 경로는 확인되지 않았다. 공개API가 없는 곳은키만 받아도 해결되지 않을 수 있다.

이 문서와 검토 JSON만 추가했다. 후보 약력·RSS 정기 수집·새 UI 구현이나 기존 전국 생성물 변경은 없다. 사용자 병합/배포 보류를 유지한다.
