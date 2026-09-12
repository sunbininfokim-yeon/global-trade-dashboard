# HANDOFF → Claude — 중국 당 4대 판공 + 국무원 구성부문 인사

**contract_updated:** 2026-09-12  
**as_of:** 2026-09-12  
**작성:** Cursor  
**읽는 이:** Claude Code  
**소유권:** 인사 정본·출처 = Cursor. UI 표시 = Claude (`TASKS` claim 있을 때만).  
**관련 UI 계약:** `HANDOFF_CLAUDE_ELECTIONS_UI_V2.md` §5 중국 탭  
**관련 JSON:** `config/china_leadership_extracted.json` (`as_of` 2026-09-12, version 6. Cursor 패치 완료)

이 문서만 읽으면 된다. Obsidian 볼트·Cursor 캔버스는 열지 마라.  
없는 이름은 추측해서 채우지 마라. `null` / TODO / 미확정은 그대로 보여라.

## 0. Claude가 할 것 / 하지 말 것

**할 것**

- 중국 화면 `공산당 / 국무원 / 군`을 그릴 때 이 표의 `confidence`·`status`를 따른다.
- 출처·기준일(`as_of`)을 각주 또는 정보 버튼으로 노출할 수 있다.
- `china_leadership_extracted.json` (`as_of` 2026-09-12)이 이 문서와 같은 패치다. UI는 `party_state.central_departments`의 판공 4곳과 `state_council.constituent_departments` 26곳을 읽으면 된다. 없는 칸(`mcf_office.director.status=unknown`)은 추측하지 마라.

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

| 부처 | name_zh | 장관 | name_en | 취임 | cabinet_23 | confidence | 비고 |
|---|---|---|---|---|---|---|---|
| 외교부 | 外交部 | 왕이 | Wang Yi | 2023-07-25 | Y | high | 당위 서기는 제위 齐玉. 부장≠당서기 |
| 국방부 | 国防部 | 둥쥔 | Dong Jun | 2023-12-29 | N | high | PLA 별선 |
| 발개위 | 国家发展和改革委员会 | 정산제 | Zheng Shanjie | 2023-03-12 | Y | high | 재경위 아래 실무 |
| 교육부 | 教育部 | 화이진펑 | Huai Jinpeng | 2021-08-20 | Y | high | |
| 과학기술부 | 科学技术部 | 인허쥔 | Yin Hejun | 2023-10-24 | Y | high | |
| 공신부 | 工业和信息化部 | 리러청 | Li Lecheng | 2025-04-30 | Y | high | 진좡룽 면. 주석령 48호 |
| 국가민위 | 国家民族事务委员会 | 천루이펑 | Chen Ruifeng | 2025-09-12 | Y | high | |
| 공안부 | 公安部 | 왕샤오훙 | Wang Xiaohong | 2022-06-24 | Y | high | 국무위원 겸 |
| 국가안전부 | 国家安全部 | 천이신 | Chen Yixin | 2022-10-30 | Y | high | |
| 민정부 | 民政部 | 리창관 | Li Changguan | 2026-08-28 | Y | high | 루즈위안 면. 주석령 85호 |
| 사법부 | 司法部 | 허룽 | He Rong | 2023-02-24 | Y | high | 여성 |
| 재정부 | 财政部 | 란포안 | Lan Fo'an | 2023-10-24 | Y | high | |
| 인력자원사회보장부 | 人力资源和社会保障部 | 왕샤오핑 | Wang Xiaoping | 2022-12-30 | Y | high | 여성 |
| 자연자원부 | 自然资源部 | 관즈어우 | Guan Zhi'ou | 2024-12-25 | Y | high | |
| 생태환경부 | 生态环境部 | 황룬추 | Huang Runqiu | 2020-04-29 | Y | high | 구삼학사. 당조 서기는 쑨진룽 孙金龙 |
| 주택도시농촌건설부 | 住房和城乡建设部 | 니훙 | Ni Hong | 2022-06-24 | Y | high | |
| 교통운수부 | 交通运输部 | 류웨이 | Liu Wei | 2024-11-08 | Y | high | |
| 수리부 | 水利部 | 리궈잉 | Li Guoying | 2021-02-28 | Y | high | |
| 농업농촌부 | 农业农村部 | 장주 | Zhang Zhu | 2026-04-30 | Y | high | 한쥔 면. 거취 unknown. 주석령 76호 |
| 상무부 | 商务部 | 왕원타오 | Wang Wentao | 2020-12-26 | Y | high | |
| 문화여유부 | 文化和旅游部 | 쑨예리 | Sun Yeli | 2023-12-29 | Y | high | |
| 국가위생건강위 | 国家卫生健康委员会 | 레이하이차오 | Lei Haichao | 2024-06-28 | Y | high | |
| 퇴역군인사무부 | 退役军人事务部 | 페이진자 | Pei Jinjia | 2022-06-24 | Y | high | 군민융합 판공실 부주임 겸 |
| 응급관리부 | 应急管理部 | 장청중 | Zhang Chengzhong | 2026-04-30 | Y | high | 왕샹시 2026-02 면. 주석령 76호 |
| 중국인민은행 | 中国人民银行 | 판궁성 | Pan Gongsheng | 2023-07-25 | N | high | 중앙금융위 아래 |
| 감사서 | 审计署 | 허우카이 | Hou Kai | 2020-06-30 | N | high | |

국무원 수뇌 (JSON과 일치, 유지):

- 총리 리창 李强
- 부총리 딩쉐샹, 허리펑, 장궈칭, 류궈중
- 국무위원 왕샤오훙, 우정룽 吴政隆 (비서장 겸), 선이친 谌贻琴

## 4. JSON 패치 (2026-09-12 Cursor)

`config/china_leadership_extracted.json` version 6.

| 슬롯 | 패치 |
|---|---|
| 차이치 | PSC·정치국 `title_ko` = 중앙판공청 주임. also에 당교·행정학원 |
| 판공 4곳 | `central_departments.general_office` / `policy_research_office` / `cfeac_office` / `mcf_office` |
| 군민융합 명목 주임 | `director.status=unknown`, 실무는 사오신이 |
| 국무원 | 총리·부총리 4·국무위원 3 + `constituent_departments` 26 (`cabinet_23` 23곳) |
| 민정부 | 리창관 (2026-08-28 주석령 85호) |

공개 보드 `elections_board_v1.json`은 이 추출 JSON을 `countries[CHN].leadership.party_state`로 복사한다. 이 브랜치는 추출 파일만 고쳤다. 보드 재생성은 `python3 build_board.py` (네트워크 배팅 fetch 있음).

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
