# HANDOFF → Claude — 중국 당 4대 판공 + 국무원 구성부문 인사

**contract_updated:** 2026-09-12  
**as_of:** 2026-09-12  
**작성:** Cursor  
**읽는 이:** Claude Code  
**소유권:** 인사 정본·출처 = Cursor. UI 표시 = Claude (`TASKS` claim 있을 때만).  
**관련 UI 계약:** `HANDOFF_CLAUDE_ELECTIONS_UI_V2.md` §5 중국 탭  
**관련 JSON:** `config/china_leadership_extracted.json` (`as_of` 2026-10-01, version 8. 당조/당위 서기 포함)

이 문서만 읽으면 된다. Obsidian 볼트·Cursor 캔버스는 열지 마라.  
없는 이름은 추측해서 채우지 마라. `null` / TODO / 미확정은 그대로 보여라.

## Claude가 받는 법 (GitHub)

로컬 Cursor 워크트리는 공유되지 않는다. **origin에서 fetch** 한다.

```bash
git fetch origin cursor/china-ccp-personnel
git checkout cursor/china-ccp-personnel
```

읽을 순서:

1. `New for anti/scripts/election_watch/HANDOFF_CLAUDE_CHINA_CCP_PERSONNEL_2026-09.md` (이 파일)
2. `New for anti/scripts/election_watch/config/china_leadership_extracted.json` (`as_of` 2026-09-12, version 7)
3. `New for anti/scripts/election_watch/HANDOFF_CLAUDE_ELECTIONS_UI_V2.md` §5
4. 화면용 복사본: `New for anti/public/data/elections_board_v1.json` → `countries[CHN].leadership.party_state`
5. 골격+이름: `New for anti/public/data/elections_cn_party_v1.json` → `state_council_ministries[]` (`name_ko`, `party_secretary_ko`, `same_as_minister`)

repo: `sunbininfokim-yeon/global-trade-dashboard`  
Cloudflare 배포가 아니다. PR merge 전에도 이 브랜치 fetch면 된다.

## 0.5 왜 국무원 인사가 없어 보였는가 (2026-09-12)

인명이 없었던 게 아니다. **읽는 파일과 UI 매칭이 구식이었다.**

1. 정본 `config/china_leadership_extracted.json` (`as_of` 2026-09-12)에는 총리·부총리 4·국무위원 3·구성부문 **26곳**이 `party_state.state_council`에 있다.
2. 공개 보드 `elections_board_v1.json`의 `countries[CHN].leadership.party_state`는 한동안 2026-08-09 사본이라 **총리·부총리만** 있었다. `build_board.py`를 안 돌렸기 때문이다. 2026-09-12에 추출본을 보드에 복사했다.
3. `chn-org.js`의 `ministryPool()`은 `constituent_departments`를 읽지 않는다. `cmc.defense_minister` + `security_organs`만 본다. 그래서 보드를 맞춰도 화면은 국방·공안·국안 셋만 채우고 나머지는 **「명단 수집 예정」**으로 남는다.
4. UI 계약 `HANDOFF_CLAUDE_ELECTIONS_UI_V2.md` §5 국무원 탭도 「총리·부총리」만 적혀 있다. `constituent_departments`를 읽도록 고치는 건 Claude UI 일이다 (`TASKS` claim).
5. 당장 화면이 비지 않게, 골격 `elections_cn_party_v1.json`의 `state_council_ministries` 26곳에 `name_ko`/`name_en`을 넣었다. 이 파일이 매칭보다 우선한다.

국무위원 3인(왕샤오훙·우정룽·선이친)은 국무원 탭에 단이 없다. 공안 겸직만 부처 칸에 나온다. 비서장·국무위원 단은 Claude가 탭을 열 때 추가한다.

## 0.6 월간 점검 2026-10-01 (version 8)

9월 중 인대 상무위 임면 공지나 부장 임면 주석령은 확인되지 않았다. 변동은 당 쪽 결정과 기율 처분이다.

| 슬롯 | 변동 | 출처 |
|---|---|---|
| 공신부 부장 | 리러청, 2026-09-23 중앙 결정으로 안후이성위 서기. 부장직은 인대 면직 전까지 법적으로 남아 `status`는 그대로 두고 `transfer`·`note_ko`에 적었다 | news.cn 2026-09-23 |
| 공신부 당조서기 | 후임 미발표 → `status: unknown` | 같은 날 보도 |
| 장유샤·류전리 | 2026-09-21 정치국이 당적 제명 승인 → `expelled_2026-09` (삭선 유지) | 인민일보 2026-09-22 |
| 왕샹시 (전 응급관리부장) | 2026-09-08 쌍개 → 전임자 `expelled_2026-09` | 중신망 2026-09-08 |
| 자연자원부 | 여전히 부장 공석. 류궈훙 직함에 '국가자연자원총독찰' 추가 확인 | 국신판 2026-09-22 |

변동 없음: 판공 4곳, 나머지 24개 부처 부장·당서기, 5대 전구 사령원.  
다음 체크포인트: 5중전회 2026-10-26~29 (당적 제명 추인), 다음 인대 상무위 (공신부 면직·자연자원부 임명 가능).  
차이치 중앙판공청 주임 교체설은 공식 발표가 없어 반영하지 않았다.

## 0. Claude가 할 것 / 하지 말 것

**할 것**

- 중국 화면 `공산당 / 국무원 / 군`을 그릴 때 이 표의 `confidence`·`status`를 따른다.
- 출처·기준일(`as_of`)을 각주 또는 정보 버튼으로 노출할 수 있다.
- `china_leadership_extracted.json` (`as_of` 2026-09-12, version 7)이 이 문서와 같은 패치다. UI는 `party_state.central_departments`의 판공 4곳과 `state_council.constituent_departments` 26곳을 읽으면 된다. 부처 칸에는 부장과 `party_group_secretary`를 같이 보여라. `same_as_minister=true`면 한 사람으로, `false`면 둘로. 없는 칸(`mcf_office.director.status=unknown`, 자연자원 부장 공석, 국방 당조 없음)은 추측하지 마라.

**하지 말 것**

- `app.js` / `style.css` / `index.html` / `data.js` / `_worker.js` 수정 금지. claim 없는 UI 구현 금지.
- 낙마·조사 루머를 단정 문장으로 바꾸지 마라. 공식 면직만 `removed`, 거취 미발표는 `status: unknown`.
- DoD CMPR·USCC를 인명 1차로 쓰지 마라. 하버드 CBDB를 현직에 쓰지 마라.
- **위키백과·바이두백과를 성명 확정·월간 점검에 쓰지 마라.** 의전 추론의 입구로만 봤다면 국가 1차 또는 아래 연구실로 다시 확인하라.
- 국무원 구성부문을 23곳으로 줄여 그리지 마라. 공식은 **26곳**. 23곳은 국방·인행·감사 제외 필터다.

## 1. 왜 당 인사가 비는가

국무원 부장은 전국인대 상무위 결정 + 주석령으로 이름이 나온다.  
당 중앙 직속 판공 기구는 그 경로가 없다. 의전 석차·CCTV·강연 직함으로 늦게 확인된다.

| 층 | 무엇을 주나 | 인명 1차인가 |
|---|---|---|
| 신화사·중국정부망·인대망 주석령 | 부장 임면, 일부 약력 | 예 |
| UCSD China Data Lab / 21st Century China Center | CCP Elite 직위 코드·엘리트 포털 | 교차 (신청제 데이터) |
| China Leadership Monitor (CMC / 구 Hoover) | 당 기구·엘리트 정치 계간 | 해석. 성명은 국가 1차로 재확인 |
| DoD CMPR, USCC, CMSI, CASI | 군·MCF **전략** | 아니오 |
| 하버드 Fairbank·Ash·Dataverse | 조직사·역사. 현직 트래커 아님 | 아니오 |
| Trivium / Caixin / NPC Observer | 당 판공·인대 임면 속보 | 2차 (국가매체 인용 후) |
| 위키백과 | — | **쓰지 않음** |

## 2. 당 4대 직위 (요청 범위)

기존 JSON `party_state.central_departments`에는 조직·선전·통전·정법만 있었다.  
2026-09-12 패치로 아래 4곳이 들어갔다. 카드 스키마:

```text
office: { id, title_ko, title_zh, director, deputies[], confidence, as_of, sources[] }
person: { name_en, name_zh, name_ko, since, rank_ko, status, note_ko }
```

### 2.1 중공중앙판공청 中共中央办公厅

| 필드 | 값 |
|---|---|
| id | `ccp_general_office` |
| director.name_en | Cai Qi |
| director.name_zh | 蔡奇 |
| director.name_ko | 차이치 |
| since | 2023-03 |
| rank_ko | 정치국 상무위원 5위, 서기처 1순위 |
| also_ko | 중앙·국가기관 공위 서기. 2026-05/06 중앙당교 교장·국가행정학원 원장 |
| predecessor | Ding Xuexiang 丁薛祥 딩쉐샹 |
| deputies | Meng Xiangfeng 孟祥锋 멍샹펑 (확인된 부주임. 전수 아님) |
| confidence | high |
| status | incumbent |
| function_ko | 최고지도자 일정·문건·회의·경호·정보 유통. 시진핑 참모장. |

비고: 왕동흥(1977) 이후 상무위원이 이 자리를 겸한 첫 사례. 후계자 아님(연령). JSON PSC 행의 차이치 역할은 지금 `중앙서기처 제1서기`만 있다. 판공청 주임을 빠뜨리지 마라.

### 2.2 중앙정책연구실 中央政策研究室

| 필드 | 값 |
|---|---|
| id | `ccp_policy_research_office` |
| director.name_en | Tang Fangyu |
| director.name_zh | 唐方裕 |
| director.name_ko | 탕팡위 |
| since | 2025-12 (국가매체 직함 공표 2026-01-14) |
| predecessor | Jiang Jinquan 江金权 장진취안 (2020-10 ~ 2025-12) |
| deputies | Hu Jinqi 胡金旗, Deng Maosheng 邓茂生, Zhou Xinqun 周新群 (2026-06) |
| confidence | high |
| status | incumbent |
| function_ko | 당대회 보고·전회 결정·이념 문건 기초 |

출처: Caixin Global 2026-01-15, Trivium China 2026-01-15 (국가매체 강연 직함).

### 2.3 중앙재경위원회 판공실 中央财经委员会办公室

| 필드 | 값 |
|---|---|
| id | `cfeac_office` |
| commission_chair | Xi Jinping |
| commission_vice | Li Qiang |
| director.name_en | He Lifeng |
| director.name_zh | 何立峰 |
| director.name_ko | 허리펑 |
| since | 2023-03 |
| rank_ko | 정치국위원·부총리 |
| also_ko | 중앙금융위 판공실 주임, 중앙금융공위 서기 |
| executive_deputy | Han Wenxiu 韩文秀 한원슈 (정부급, 일상 주재, 중앙농판 주임 겸. 2018-12~) |
| confidence | high |
| status | incumbent |
| function_ko | 거시·금융 의제 설정. 발개위·재정부보다 앞선다. |

출처: 신화사 약력 2023-10-30. 한원슈 직함: 중국발전고위포럼 2026-03-22.

### 2.4 중앙군민융합발전위원회 판공실 中央军民融合发展委员会办公室

| 필드 | 값 |
|---|---|
| id | `mcf_office` |
| commission_chair | Xi Jinping |
| titular_director | **TODO / unknown.** 장가오리(2017–18) → 한정(2018–?) 이후 공식 후임 없음 |
| executive_deputy.name_en | Shao Xinyu |
| executive_deputy.name_zh | 邵新宇 |
| executive_deputy.name_ko | 사오신이 |
| executive_deputy.since | 2025-04-09 |
| executive_deputy.note_ko | 공정원 원사. 전 과기부 부부장·후베이 상무부성장. 정부급 |
| deputies | Pei Jinjia 裴金佳 (퇴역군인부장 겸), Wu Xihua 吴喜铧 (로켓군 소장), Yin Weijun 尹卫军 |
| confidence_titular | low |
| confidence_shao | medium-high |
| status_titular | unknown |
| function_ko | 민군 융합 상설 판공. DoD CMPR은 전략만 서술하고 이 사무실·사오신이 성명은 없음 |

전 상무부주임 진좡룽 金壮龙은 공신부장을 하다 2025-04-30 면직. 거취 `unknown`.

## 3. 국무원 구성부문 — 공식 26곳

JSON `party_state.state_council`에 총리·부총리·국무위원과 구성부문 26곳이 있다.  
23곳 필터: `cabinet_23 = true` 인 행만 (국방·인행·감사 제외).

각 부처 `party_group_secretary`: `same_as_minister=true`면 부장=당서기.  
**분리는 환경부만이 아니다.** 외교부(당위 제위)와 자연자원부(당조 류궈훙, 부장은 공석)도 다르다. 국방부는 민간 당조가 없다.

| 부처 | 장관 | 당서기 | 같음 | 비고 |
|---|---|---|---|---|
| 외교부 | 왕이 | 제위 齐玉 (당위) | 아니오 | fmprc.gov.cn |
| 국방부 | 둥쥔 | 해당 없음 | — | PLA·군위 계통 |
| 발개위 | 정산제 | 정산제 (당조) | 예 | ndrc.gov.cn |
| 교육부 | 화이진펑 | 화이진펑 (당조) | 예 | moe.gov.cn |
| 과학기술부 | 인허쥔 | 인허쥔 (당조) | 예 | most.gov.cn |
| 공신부 | 리러청 (2026-09-23 안후이성위 서기 전출, 인대 면직 대기) | **미발표** | 아니오 | 신화사 2026-09-23. miit.gov.cn 부장 페이지는 아직 갱신 전 |
| 국가민위 | 천루이펑 | 천루이펑 (당조) | 예 | neac.gov.cn |
| 공안부 | 왕샤오훙 | 왕샤오훙 (당위) | 예 | gov.cn 약력 |
| 국가안전부 | 천이신 | 천이신 (당위) | 예 | 중국장안망 2026-09 |
| 민정부 | 리창관 | 리창관 (당조) | 예 | 인민망 부처명단. 주석령 85호는 부장 |
| 사법부 | 허룽 | 허룽 (당조) | 예 | 인민망 부처명단 |
| 재정부 | 란포안 | 란포안 (당조) | 예 | mof.gov.cn |
| 인력자원사회보장부 | 왕샤오핑 | 왕샤오핑 (당조) | 예 | 인민망 부처명단 |
| 자연자원부 | **공석** (2026-06-26~) | 류궈훙 刘国洪 (당조, 2026-07-30) | 아니오 | 주석령 79호 면 관즈어우. 후임 부장 인대 미임명. 관즈어우는 후베이성위 서기 |
| 생태환경부 | 황룬추 | 쑨진룽 孙金龙 (당조) | 아니오 | mee.gov.cn. 부장은 구삼학사 |
| 주택도시농촌건설부 | 니훙 | 니훙 (당조) | 예 | 인민망 부처명단 |
| 교통운수부 | 류웨이 | 류웨이 (당조) | 예 | 인민망 부처명단 |
| 수리부 | 리궈잉 | 리궈잉 (당조) | 예 | 인민망 부처명단 |
| 농업농촌부 | 장주 | 장주 (당조) | 예 | moa.gov.cn |
| 상무부 | 왕원타오 | 왕원타오 (당조) | 예 | 인민망 부처명단 |
| 문화여유부 | 쑨예리 | 쑨예리 (당조) | 예 | mct.gov.cn |
| 국가위생건강위 | 레이하이차오 | 레이하이차오 (당조) | 예 | 인민망 부처명단 |
| 퇴역군인사무부 | 페이진자 | 페이진자 (당조) | 예 | 인민망 부처명단 |
| 응급관리부 | 장청중 | 장청중 (당위) | 예 | mem.gov.cn |
| 중국인민은행 | 판궁성 | 판궁성 (당위) | 예 | pbc.gov.cn |
| 감사서 | 허우카이 | 허우카이 (당조) | 예 | audit.gov.cn |

국무원 수뇌 (JSON과 일치, 유지):

- 총리 리창 李强
- 부총리 딩쉐샹, 허리펑, 장궈칭, 류궈중
- 국무위원 왕샤오훙, 우정룽 吴政隆 (비서장 겸), 선이친 谌贻琴

## 4. JSON 패치 (2026-09-12 Cursor)

`config/china_leadership_extracted.json` version 7.

| 슬롯 | 패치 |
|---|---|
| 차이치 | PSC·정치국 `title_ko` = 중앙판공청 주임. also에 당교·행정학원 |
| 판공 4곳 | `central_departments.general_office` / `policy_research_office` / `cfeac_office` / `mcf_office` |
| 군민융합 명목 주임 | `director.status=unknown`, 실무는 사오신이 |
| 국무원 | 총리·부총리 4·국무위원 3 + `constituent_departments` 26 (`cabinet_23` 23곳) |
| 민정부 | 리창관 (2026-08-28 주석령 85호) |
| 당조/당위 | 26곳 모두 `party_group_secretary`. 분리: 외교 제위, 생태환경 쑨진룽, 자연자원 류궈훙. 자연자원 부장 공석 |
| 자연자원 | 관즈어우 면 (주석령 79호, 2026-06-26). 후임 후베이성위 서기 |

공개 보드 `elections_board_v1.json`의 `countries[CHN].leadership.party_state`는 2026-09-12에 추출본을 복사했다 (`sync_china_state_council_to_board.py`). 전체 `build_board.py`는 배팅 fetch가 있어 돌리지 않았다. 골격 `elections_cn_party_v1.json` 부처 26곳에도 같은 날 이름을 넣었다.

## 5. 렌더링 규칙 (중국 특수)

기존 선거 UI 계약과 같다.

- `unknown` / TODO / 미확정은 빈 칸이 아니라 **그대로** 표시.
- `confidence: high|medium-high|medium|low`
- 한쥔·진좡룽: 공식 면직만. 조사·낙마 단정 금지. `status: removed`, `next_post: unknown`
- 숙청 문구는 `china_leadership_extracted.json`의 `display: strikethrough`만 따른다. 이 문서 4대 판공에는 해당 없음.
- 중국에 서구 좌우 색을 강제하지 마라.

## 6. 출처 계층 (위키 제외)

성명 확정은 항상 국가 1차. 연구실은 교차·해석·누락 탐지. 위키·바이두백과는 점검 목록에 넣지 않는다.

### 6.1 1차 국가 (성명)

- https://www.gov.cn/gwyzzjg/
- http://www.npc.gov.cn/ — 상무위 임면
- 농업·응급 주석령 76호 (2026-04-30): https://www.gov.cn/yaowen/liebiao/202604/content_7067518.htm
- 민정 주석령 85호 (2026-08-28, 리창관): https://www.gov.cn/yaowen/liebiao/202608/content_7079463.htm
- 신화사 허리펑 약력: http://www.news.cn/politics/leaders/2023-10/30/c_1129280455.htm

### 6.2 1차 미 정부·의회 (구조·전략. 당 판공 성명 아님)

- DoD CMPR 2025: https://media.defense.gov/2025/Dec/23/2003849070/-1/-1/1/ANNUAL-REPORT-TO-CONGRESS-MILITARY-AND-SECURITY-DEVELOPMENTS-INVOLVING-THE-PEOPLES-REPUBLIC-OF-CHINA-2025.PDF
- USCC 2025: https://www.uscc.gov/sites/default/files/2025-11/2025_Annual_Report_to_Congress.pdf
- CRS: https://crsreports.congress.gov/ (검색 China Communist Party)
- ODNI Annual Threat Assessment (연 1회, 인명 트래커 아님)

### 6.3 연구실 — 인사·엘리트 정치 (우선)

| ID | 기관 | URL | 쓰는 이유 | 한계 |
|---|---|---|---|---|
| UCSD-21CCC | UC San Diego 21st Century China Center (Susan Shirk 창립, 2026-07부터 Margaret Roberts 소장, Victor Shih 전 소장) | https://china.ucsd.edu/ | 미국 대학 중국 정치 허브. 엘리트·당국가 | 현직 명단을 매월 안 냄 |
| UCSD-CDL | UCSD China Data Lab / CCP Elite Database (Victor Shih, Jonghyuk Lee) | https://chinadatalab.ucsd.edu/ · Dataverse | 당·정·군 직위 코드가 가장 촘촘 | 신청제. 하버드 아님 |
| CLM | China Leadership Monitor — Claremont McKenna, 편집 Minxin Pei. 2002 Hoover Alice Miller 창간, 2018 CMC로 이전 | https://www.prcleader.org/ | 당 기구·엘리트 정치 계간. 2026-09 Issue 89 | 성명은 국가 1차로 재확인 |
| HARV-FAIRBANK | Harvard Fairbank Center | https://fairbank.fas.harvard.edu/ | 중국학 본산. 세미나·연구 | 현직 내각 트래커 아님 |
| HARV-ASH | Harvard Kennedy School Ash Center | https://ash.harvard.edu/ | 거버넌스·중국 프로그램 | 현직 명단 아님 |
| HARV-COHD | Chinese Organizational History Dataset (Hao Chen, Yuhua Wang 등) | https://doi.org/10.7910/dvn/8nagss | 조직사 이력 | 역사. 2026 내각 아님 |
| HARV-PL | Chinese Political-Legal Leaders (Yuhua Wang) | https://doi.org/10.7910/dvn/gfam1t | 정법 엘리트 | 현직 판공실에 약함 |
| HARV-CBDB | China Biographical Database | https://projects.iq.harvard.edu/cbdb | 제정·근현대 | **당대 판공실에 쓰지 말 것** |
| STAN-SCCEI | Stanford Center on China's Economy and Institutions | https://sccei.fsi.stanford.edu/ | 중국 경제·산업·혁신 | 인사보다 구조 |
| STAN-DIGI | Stanford DigiChina (Graham Webster) | https://digichina.stanford.edu/ | 사이버·디지털 거버넌스 문건 | 판공청·망신위 교차 |
| SAIS | Johns Hopkins SAIS China Studies | https://sais.jhu.edu/ | 외교·안보 중국 전공 | 명단 아님 |
| COL-WEAI | Columbia Weatherhead East Asian Institute | https://weai.columbia.edu/ | 동아시아 정치 | 명단 아님 |
| ANU-GO | Wen-Hsuan Tsai, CCP General Office | https://doi.org/10.22459/rts.2025.04 | 판공청 기능 논문 | 단편 |

### 6.4 연구실 — 군·군민융합

| ID | 기관 | URL | 쓰는 이유 |
|---|---|---|---|
| CMSI | US Naval War College China Maritime Studies Institute (Andrew Erickson) | https://www.usnwc.edu/Research-and-Wargaming/Research-Centers/China-Maritime-Studies-Institute | 중문 원문 기반 해군·해경. MCF 해양 |
| CASI | USAF China Aerospace Studies Institute | https://www.airuniversity.af.edu/CASI/ | PLA 항공우주·이중용도 |
| RAND | RAND China | https://www.rand.org/topics/china.html | PLA·MCF 구조 |
| CSIS | CSIS China Power / Freeman Chair / Trustee Chair (Scott Kennedy) | https://www.csis.org/programs/china-power-project | 군사·산업정책 |
| CNAS | Center for a New American Security | https://www.cnas.org/ | 기술·안보 |
| NBR | National Bureau of Asian Research | https://www.nbr.org/ | 아시아 안보 |

### 6.5 연구실 — 경제·통상·유럽 보조

| ID | 기관 | URL | 쓰는 이유 |
|---|---|---|---|
| PIIE | Peterson Institute | https://www.piie.com/ | 중국 거시·무역 |
| BROOKINGS | John L. Thornton China Center | https://www.brookings.edu/center/john-l-thornton-china-center/ | 당국가 해석 |
| CARNEGIE | Carnegie China | https://carnegieendowment.org/regions/china | 외교·기술 |
| WILSON | Wilson Center Kissinger Institute | https://www.wilsoncenter.org/program/kissinger-institute-china-and-united-states | 미중 관계 |
| CFR | Council on Foreign Relations China | https://www.cfr.org/china | 정책 브리프 |
| MERICS | Mercator Institute for China Studies (Berlin) | https://merics.org/ | 유럽 측 당국가·산업. 영문 보고서 |
| ASPI | Australian Strategic Policy Institute | https://www.aspi.org.au/ | 국방기술·MCF 기업 맵 |
| IISS | International Institute for Strategic Studies | https://www.iiss.org/ | 군사균형 |

### 6.6 속보 교차 (국가 1차 인용 후에만 성명)

| ID | 기관 | URL | 쓰는 이유 |
|---|---|---|---|
| TRIVIUM | Trivium China | https://triviumchina.com/ | 당 인사에 빠름. 탕팡위 2026-01-15 |
| CAIXIN | Caixin Global | https://www.caixinglobal.com/ | 동일. 유료 |
| NPC-OBS | NPC Observer (Changhao Wei) | https://npcobserver.com/ | 인대 상무위 임면·법률. 위키 대체 |
| JAMESTOWN | China Brief | https://jamestown.org/programs/cb/ | 인사·파벌 속보성 분석 |
| SCMP | South China Morning Post | https://www.scmp.com/ | 의전·겸직 보도 |
| FP-CAI | Foreign Policy | https://foreignpolicy.com/2026/05/07/china-cai-qi-li-qiang-leadership/ | 차이치 역할 해석 |
| CLT | China Law Translate | https://www.chinalawtranslate.com/ | 법령 영문. 인사 아님 |
| CACR | Center for Advanced China Research / Party Watch | https://www.ccpwatch.org/ | 당 기구 오픈소스. 인력 축소 가능 — 살아 있는 호만 |

MacroPolo The Committee는 20기 중앙위 이력이 좋았으나 사이트 중단 위험이 있어 **정본으로 두지 않는다.**

## 7. 월간 갱신 체크리스트 (위키 없음)

Cursor 담당. Claude는 읽기만. 매월 1일, 이 순서만. 한 항이 침묵하면 다음 항. 위키로 메우지 말 것.

1. 인대망 최근 임면 + 주석령 + 중국정부망 조직 페이지
2. 신화사 지도자 약력: 차이치, 허리펑. 국가매체 강연 직함: 탕팡위, 한원슈, 사오신이
3. NPC Observer 상무위 세션 임면 요약 (국가 1차 URL로 재확인)
4. Trivium / Caixin 인사 브리프 (당 판공실)
5. China Leadership Monitor 최신호 (prcleader.org)
6. UCSD China Data Lab / 21CCC 신규 노트·데이터셋 버전
7. Stanford SCCEI Briefs · DigiChina 문건 (디지털·산업만)
8. DoD 1260H. CMPR은 12월만 본문 대조. CMSI/CASI 신규 리포트 (군·MCF)
9. USCC 청문회·CRS 개정일
10. MERICS / CSIS / RAND 중 당국가·MCF 신규만
11. 군민융합 **명목 주임** TODO — 안 풀리면 빈칸 유지

합격: 고=주석령·신화사 약력·국가매체 직함. 중=전문매체 2곳 + 국가 1차. 저/TODO=한 곳만.  
변동이 있으면 `contract_updated`와 `as_of`를 같은 날로 올린다.

## 8. TODO (열지 말고 남겨둘 것)

- 군민융합 판공실 **명목 주임** (한정 이후)
- 한쥔·진좡룽 거취
- 멍샹펑 외 중난 부주임 전수
- 재경위 판공실 부주임 전수 (축웨이둥 祝卫东, 옌펑청 严鹏程 등 보조)

Obsidian 미러(사람이 볼 때): `~/Documents/기후 모델링/Global Trade/China CCP Personnel/`  
레포 정본은 **이 파일**이다.
