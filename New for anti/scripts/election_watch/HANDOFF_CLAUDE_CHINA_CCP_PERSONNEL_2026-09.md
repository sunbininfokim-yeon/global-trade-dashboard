# HANDOFF → Claude — 중국 당 4대 판공 + 국무원 구성부문 인사

**contract_updated:** 2026-09-11  
**as_of:** 2026-09-11  
**작성:** Cursor  
**읽는 이:** Claude Code  
**소유권:** 인사 정본·출처 = Cursor. UI 표시 = Claude (`TASKS` claim 있을 때만).  
**관련 UI 계약:** `HANDOFF_CLAUDE_ELECTIONS_UI_V2.md` §5 중국 탭  
**관련 JSON (오래됨):** `config/china_leadership_extracted.json` (`as_of` 2026-08-09)

이 문서만 읽으면 된다. Obsidian 볼트·Cursor 캔버스는 열지 마라.  
없는 이름은 추측해서 채우지 마라. `null` / TODO / 미확정은 그대로 보여라.

## 0. Claude가 할 것 / 하지 말 것

**할 것**

- 중국 화면 `공산당 / 국무원 / 군`을 그릴 때 이 표의 `confidence`·`status`를 따른다.
- 출처·기준일(`as_of`)을 각주 또는 정보 버튼으로 노출할 수 있다.
- `china_leadership_extracted.json`과 이 문서가 어긋나면 **이 문서가 더 새롭다.** JSON 패치는 Cursor 몫이다. UI는 추측 보강하지 말고 빈 칸·TODO로 둔다.

**하지 말 것**

- `app.js` / `style.css` / `index.html` / `data.js` / `_worker.js` 수정 금지. claim 없는 UI 구현 금지.
- 낙마·조사 루머를 단정 문장으로 바꾸지 마라. 공식 면직만 `removed`, 거취 미발표는 `status: unknown`.
- DoD CMPR·USCC를 인명 1차로 쓰지 마라. 하버드 CBDB를 현직에 쓰지 마라.
- 국무원 구성부문을 23곳으로 줄여 그리지 마라. 공식은 **26곳**. 23곳은 국방·인행·감사 제외 필터다.

## 1. 왜 당 인사가 비는가

국무원 부장은 전국인대 상무위 결정 + 주석령으로 이름이 나온다.  
당 중앙 직속 판공 기구는 그 경로가 없다. 의전 석차·CCTV·강연 직함으로 늦게 확인된다.

| 층 | 무엇을 주나 | 인명 1차인가 |
|---|---|---|
| 신화사·중국정부망·인대망 | 부장 임면, 일부 약력 | 예 (국가) |
| DoD CMPR 2025, USCC 2025 | 군민융합 **전략**, 1260H 기업 | 아니오 |
| 하버드 Ash/Fairbank/CBDB/Dataverse | 조직사·역사 엘리트 | 아니오 |
| Trivium / Caixin / Hoover PRC Leader | 당 판공실 직함 교차 | 2차 (국가매체 인용 후) |

Victor Shih CCP Elite DB는 직위 코드가 촘촘하나 **UCSD/China Data Lab**이지 하버드가 아니다.

## 2. 당 4대 직위 (요청 범위)

기존 JSON `party_state.central_departments`에는 조직·선전·통전·정법만 있다.  
아래 4곳은 **아직 JSON에 없다.** 카드로 넣을 때 이 스키마를 써라.

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

JSON `party_state.state_council`은 지금 총리+부총리 4명만 있다. 부장 전수는 없다.  
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
| 민정부 | 民政部 | 루즈위안 | Lu Zhiyuan | 2023-12-29 | Y | high | |
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

## 4. JSON 대비 갭 (UI가 추측으로 메우지 말 것)

`config/china_leadership_extracted.json` `as_of=2026-08-09` 기준:

| 슬롯 | JSON 지금 | 이 문서 2026-09-11 |
|---|---|---|
| 차이치 | 서기처 1서기만 | + 중앙판공청 주임, 당교 교장 |
| 정책연구실 | 없음 | 탕팡위 |
| 재경위 판공실 | 없음 (허리펑은 부총리만) | 허리펑 주임 + 한원슈 일상 |
| 군민융합 판공실 | 없음 | 명목 주임 unknown, 실무 사오신이 |
| 국무원 부장 26 | 없음 | 위 표 |
| 공신부 | 없음 | 리러청 (2025-04) |
| 농업농촌부 | 없음 | 장주 (2026-04). 한쥔 unknown |
| 응급관리부 | 없음 | 장청중 (2026-04) |

Cursor가 JSON을 패치하기 전에는 UI가 옛 JSON만 읽으면 판공 4곳·부장 26곳이 안 나온다.  
claim이 있으면 이 문서 표를 읽기 전용 데이터로 쓸 수 있다. 없으면 표시하지 말고 이 문서를 읽고 넘어가라.

## 5. 렌더링 규칙 (중국 특수)

기존 선거 UI 계약과 같다.

- `unknown` / TODO / 미확정은 빈 칸이 아니라 **그대로** 표시.
- `confidence: high|medium-high|medium|low`
- 한쥔·진좡룽: 공식 면직만. 조사·낙마 단정 금지. `status: removed`, `next_post: unknown`
- 숙청 문구는 `china_leadership_extracted.json`의 `display: strikethrough`만 따른다. 이 문서 4대 판공에는 해당 없음.
- 중국에 서구 좌우 색을 강제하지 마라.

## 6. 출처 (매달 같은 순서)

1차 국가

- https://www.gov.cn/gwyzzjg/
- http://www.npc.gov.cn/ — 임면. 농업·응급 2026-04-30: `.../202604/t20260430_454282.html`
- 주석령 76호: https://www.gov.cn/yaowen/liebiao/202604/content_7067518.htm
- 신화사 허리펑 약력: http://www.news.cn/politics/leaders/2023-10/30/c_1129280455.htm

1차 미 정부·의회 (구조, 인명 아님)

- DoD CMPR 2025: https://media.defense.gov/2025/Dec/23/2003849070/-1/-1/1/ANNUAL-REPORT-TO-CONGRESS-MILITARY-AND-SECURITY-DEVELOPMENTS-INVOLVING-THE-PEOPLES-REPUBLIC-OF-CHINA-2025.PDF
- USCC 2025: https://www.uscc.gov/sites/default/files/2025-11/2025_Annual_Report_to_Congress.pdf
- CRS: https://crsreports.congress.gov/ (검색 China Communist Party)

하버드·학계

- Chinese Organizational History Dataset: https://doi.org/10.7910/dvn/8nagss
- Political-Legal Leaders (Yuhua Wang): https://doi.org/10.7910/dvn/gfam1t
- Fairbank: https://fairbank.fas.harvard.edu/
- CBDB: https://projects.iq.harvard.edu/cbdb
- Ash Center: https://ash.harvard.edu/

싱크탱크·속보

- Hoover PRC Leader: https://www.prcleader.org/
- Trivium 탕팡위: https://triviumchina.com/2026/01/15/tang-fangyu-takes-the-helm-at-central-policy-research-office/
- Caixin 탕팡위: https://www.caixinglobal.com/2026-01-15/china-names-veteran-theorist-to-lead-top-policy-office-102404191.html
- Foreign Policy 차이치: https://foreignpolicy.com/2026/05/07/china-cai-qi-li-qiang-leadership/
- ANU 판공청 논문: https://doi.org/10.22459/rts.2025.04

## 7. 월간 갱신 (Cursor 담당. Claude는 읽기만)

매월 1일: 인대 임면 → 정부망 → 신화사/강연 직함 → Trivium/Caixin → 1260H/CMPR(12월) → USCC/CRS → Hoover → Dataverse 버전 → 군민융합 명목 주임 TODO.

변동이 이 문서를 고치면 `contract_updated`와 `as_of`를 같은 날로 올린다.

## 8. TODO (열지 말고 남겨둘 것)

- 군민융합 판공실 **명목 주임** (한정 이후)
- 한쥔·진좡룽 거취
- 멍샹펑 외 중난 부주임 전수
- 재경위 판공실 부주임 전수 (축웨이둥 祝卫东, 옌펑청 严鹏程 등 보조)

Obsidian 미러(사람이 볼 때): `~/Documents/기후 모델링/Global Trade/China CCP Personnel/`  
레포 정본은 **이 파일**이다.
