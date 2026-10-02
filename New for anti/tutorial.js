// 튜토리얼 (/tutorial): 원자재 · 금융 · 정치&정책 · 해운 화면 사용설명서.
// The selected tab lives in ?tab= rather than the hash: app.js strips the
// hash on first load (see the initialView block), but keeps the query.
(function () {
  const IMG = '/public/tutorial/';

  const TABS = [
    { id: 'commodities', label: '원자재', sub: '작황&nbsp;· 무역 흐름&nbsp;· RSS', hue: 'amber' },
    { id: 'finance', label: '금융', sub: '매크로&nbsp;· 미시구조&nbsp;· 계산기', hue: 'sky' },
    { id: 'politics', label: '정치 & 정책', sub: '법안&nbsp;· 선거&nbsp;· 슈퍼팩', hue: 'violet' },
    { id: 'shipping', label: '해운', sub: '선대&nbsp;· 항로&nbsp;· 초크포인트', hue: 'teal' },
  ];

  const shot = (href, src, alt, cls = '') => `
    <a class="tut-shot ${cls}" href="${href}" target="_blank" rel="noopener" aria-label="${alt} — 실제 화면 열기">
      <img src="${IMG}${src}" alt="${alt}" loading="lazy">
      <span class="tut-open">실제 화면 ↗</span>
    </a>`;

  // A screen we have no screenshot of yet: send the reader to the live page
  // instead of showing an empty frame.
  const noShot = (href, name, cls = '') => `
    <a class="tut-noshot ${cls}" href="${href}" target="_blank" rel="noopener">
      <span class="tut-noshot-name">${name}</span>
      <span class="tut-noshot-cta">실제 화면에서 보기 ↗</span>
    </a>`;

  const card = (label, body) => `
    <div class="tut-card"><div class="tut-label">${label}</div>${body}</div>`;

  const steps = (items, cls = '') => `
    <ol class="tut-steps ${cls}">${items.map(([t, d]) => `
      <li><div><h4>${t}</h4><p>${d}</p></div></li>`).join('')}
    </ol>`;

  const feats = (items) => `
    <ul class="tut-feats">${items.map(([t, d]) => `<li><span><b>${t}</b> — ${d}</span></li>`).join('')}</ul>`;

  const chips = (items, on = []) => `
    <div class="tut-chips">${items.map((c) => `<span class="tut-chip${on.includes(c) ? ' on' : ''}">${c}</span>`).join('')}</div>`;

  const head = (eyebrow, title, intro) => `
    <div class="tut-eyebrow">${eyebrow}</div>
    <h2>${title}</h2>
    <p class="tut-intro">${intro}</p>`;

  const sub = (title, text) => `
    <div class="tut-block tut-sub"><h3>${title}</h3>${text ? `<p class="tut-muted">${text}</p>` : ''}</div>`;

  // Numbered step heading; its id is what the jump chips scroll to.
  const stepHead = (n, title, text) => `
    <div class="tut-block tut-sub tut-step" id="tut-step-${n}">
      <div class="tut-step-h"><span class="tut-step-n">0${n}</span><h3>${title}</h3></div>
      ${text ? `<p class="tut-muted">${text}</p>` : ''}
    </div>`;

  const jumps = (names) => `
    <nav class="tut-jump" aria-label="단계 바로가기">${names.map((t, i) => `
      <button type="button" data-tut-jump="${i + 1}"><span class="tut-jump-n">${i + 1}</span>${t}</button>`).join('')}
    </nav>`;

  const PANELS = {
    commodities: () => `
      ${head('COMMODITY FLOWS', '원자재 — 네 단계로 따라가기',
        '산지 작황을 보고, 품목의 무역 흐름을 읽고, 챙길 리포트는 별로 담아 메일로 받습니다. 나라를 누르면 그 나라 데이터로 들어갑니다.')}
      ${jumps(['작황 모니터', '무역 흐름', '★ → 메일', '국가별 화면'])}

      ${stepHead(1, '작황 모니터 — 세계에서 나라로', '지도에서 나라를 누르면 내려가고, 빈 바다를 누르면 올라옵니다. 원자재 메뉴의 모니터링 열에 있습니다.')}
      <div class="tut-block tut-two">
        ${card('WORLD VIEW', `${shot('/climate', 'climate-world.webp', '작황 모니터 세계 화면')}
          <h4>전체 화면</h4><p>작황 모델이 있는 산지국과 해수면 수온 편차를 색으로 먼저 봅니다. 수출통제는 바로 옆 수출통제 모니터로 옮겼습니다.</p>`)}
        ${card('COUNTRY VIEW', `${shot('/climate', 'climate-country.webp', '브라질을 누른 국가별 작황 화면')}
          <h4>국가별 화면</h4><p>산지별 기상·작황 예측이 왼쪽 패널에 붙고, 나라 안에서 지역을 다시 고릅니다.</p>`)}
      </div>

      ${stepHead(2, '원자재 무역 흐름 — 누가 누구에게 파나', '품목을 고르면 수출국에서 수입국으로 가는 흐름선이 그려집니다. UN Comtrade <b>최신 연간 통계</b> 기준이고, 아직 신고하지 않은 나라는 그 전 해 값으로 채웁니다.')}
      <div class="tut-block">
        <div class="tut-strip">
          <p><b>에너지 4</b> 원유&nbsp;· 천연가스&nbsp;· 석탄 2종</p>
          <p><b>금속 16</b> 금&nbsp;· 은&nbsp;· 구리&nbsp;· 니켈&nbsp;· 리튬&nbsp;· 희토류 …</p>
          <p><b>농산물 5</b> 밀&nbsp;· 옥수수&nbsp;· 대두&nbsp;· 설탕&nbsp;· 커피</p>
        </div>
        ${shot('/oil', 'oil-flows.webp', '원유 무역 흐름 세계 지도', 'tut-shot-natural')}
        <div class="tut-facts">
          <p><b>왼쪽 순위</b> 글로벌 물동량, 최대 수출국, 주요 수출국·수입국 비중</p>
          <p><b>선 굵기·밝기</b> 물동량 낮음·중간·높음. 주황색 나라는 수출 제한</p>
          <p><b>마우스</b> 올리면 교역량, 누르면 그 나라 노선만, 배경은 처음으로</p>
        </div>
      </div>

      ${stepHead(3, '★ 즐겨찾기 → 메일로 받기', '')}
      <div class="tut-block tut-callout">
        ${steps([
          ['로그인', '헤더 오른쪽에서 가입·로그인합니다.'],
          ['리포트에서 ★', '4번 국가별 화면 오른쪽 리포트 목록에서 별을 누릅니다.'],
          ['마이페이지', '출처별로 모이고, 항목별로 메일만 끌 수 있습니다.'],
          ['바뀌면 메일', '계정 단위 전체 일시정지도 됩니다.'],
        ], 'tut-steps-4')}
      </div>

      ${stepHead(4, '나라를 누르면 — 국가별 화면', '그 나라 데이터가 지도 양옆에 붙습니다. 아래는 천연가스에서 미국을 누른 화면입니다.')}
      <div class="tut-block">
        <div class="tut-marked">
          ${shot('/gas', 'gas-usa-country.webp', '천연가스 미국 국가별 화면과 EIA 저장 통계', 'tut-shot-natural')}
          <span class="tut-mark" style="left: 1.2%" aria-hidden="true">A</span>
          <span class="tut-mark" style="left: 52.2%" aria-hidden="true">B</span>
          <span class="tut-mark" style="left: 77%" aria-hidden="true">C</span>
        </div>
        <div class="tut-facts">
          <p><b class="tut-key">A</b> <b>교역&nbsp;· 집중도</b> 수출·수입·순수지, 연간·월별 전환. 판로 상위 3개국 CR3 28.7%&nbsp;· HHI 0.060 '낮음'</p>
          <p><b class="tut-key">B</b> <b>기관 리포트</b> 그 품목·나라에 연결된 발표 목록. 제목을 누르면 원문, ★로 담기</p>
          <p><b class="tut-key">C</b> <b>저장 통계</b> 천연가스는 EIA 지역별 지하 저장(Bcf)과 전주 대비</p>
        </div>
        <p class="tut-fine">집중도는 상대국의 정치적 신뢰도를 넣지 않은 순수 집중도이고, 위험도 자체는 아닙니다.</p>
      </div>`,

    finance: () => `
      ${head('MACRO &amp; MICROSTRUCTURE', '금융 — 보는 화면과 계산하는 화면',
        '금융 메뉴는 성격이 다른 두 묶음입니다. 시장을 보는 화면(매크로 모니터, 시장 미시구조)과, 직접 숫자를 넣어 계산하는 화면(계산기 두 개)입니다.')}

      ${sub('매크로 모니터 — 나라별 핵심 지표를 한 화면에', '야간광 지도에서 나라를 누르면 그 나라 창이 열립니다. 미국·한국·일본·중국·유로존 등 <b>19개국</b>의 유동성·금리·환율·주식·성장·물가 지표를 여섯 탭으로 모아 보여 줍니다. 나라마다 구할 수 있는 지표가 달라 카드 수는 다릅니다.')}
      <div class="tut-block">
        ${card('6 TABS&nbsp;· 미국 예시', `<div class="tut-facts">
            <p><b>유동성</b> 연준 총자산&nbsp;· 역레포(RRP)&nbsp;· TGA&nbsp;· QRA 국채 발행</p>
            <p><b>금리</b> 기준금리(EFFR)&nbsp;· 2년·10년 국채&nbsp;· 10Y−3M 스프레드&nbsp;· 하이일드 OAS</p>
            <p><b>환율</b> 달러지수(DXY)&nbsp;· EUR/USD&nbsp;· USD/JPY</p>
            <p><b>주식</b> S&amp;P 500&nbsp;· 나스닥 100&nbsp;· 러셀 2000&nbsp;· VIX</p>
            <p><b>성장</b> 실질GDP&nbsp;· GDPNow&nbsp;· ISM&nbsp;· 비농업고용&nbsp;· 실업률</p>
            <p><b>물가</b> CPI&nbsp;· 근원 CPI&nbsp;· PCE&nbsp;· 10년 기대인플레(BEI)</p>
          </div>`)}
      </div>
      <div class="tut-block">
        ${card('예시&nbsp;· 미국 유동성 → QRA 발행', `<div class="tut-media">
          ${shot('/macro_monitor', 'qra.webp', 'QRA 발행 비교 패널')}
          <div class="tut-media-text">
            <p>카드를 누르면 그 지표의 차트가 열립니다. QRA는 재무부가 분기마다 공시하는 국채 순발행 계획으로, 세 줄을 나란히 비교합니다.</p>
            ${feats([
              ['전분기 실적', '지난 분기에 실제로 찍은 양.'],
              ['직전 공시 예측', '지난번 발표 때 이번 분기로 잡았던 양.'],
              ['당기 공시', '이번 발표에서 새로 잡은 양. 예측보다 크면 시중 유동성을 더 빨아들이는 쪽입니다.'],
            ])}
            <p class="tut-fine">다른 카드도 같은 방식으로 추이·이동평균·구성 같은 보기를 고릅니다.</p>
          </div>
        </div>`)}
      </div>

      ${sub('시장 미시구조 — 파생과 외국인이 코스피를 얼마나 움직이나', '두 질문으로 나뉩니다. 파생상품(선물·옵션·레버리지 ETF)이 코스피에 얼마나 힘을 싣는지, 그리고 외국인·해외 거래가 코스피에 어떻게 번지는지.')}
      <div class="tut-block tut-two">
        ${card('DERIVATIVES → KOSPI&nbsp;· 파생 영향력', feats([
          ['파생 수급', '외국인 K200 선물·콜·풋 순매수, 풋/콜 비율, 선물 거래대금.'],
          ['수급 불균형', '레버리지·인버스 ETF가 코스피 현물 대비 얼마나 큰지, 그중 삼성전자·SK하이닉스 단일종목 비중, 상위 종목 집중도.'],
          ['해외 LETF', '해외에 상장된 삼성전자·SK하이닉스 레버리지 상품의 거래와 추정 리밸런싱.'],
        ]))}
        ${card('FOREIGN FLOW → KOSPI&nbsp;· 외국인 파급', feats([
          ['해외-국내 선행', '미국 옵션 시장의 흐름과 VIX가 한국으로 넘어오는지 봅니다.'],
          ['가격대별 체결', '외국인·개인·기관이 어느 가격대에서 사고팔았는지 (아래 예시).'],
          ['종가일 수급', '시총 상위 종목마다 그날 외국인이 몇 주를 순매수했는지.'],
        ]))}
      </div>
      <div class="tut-block">
        ${card('예시&nbsp;· 가격대별 체결 — 누가 어느 가격에서 샀나', `${shot('/fin_derivatives', 'ms-levels-3m.webp', '가격대별 누적 수급 차트: 투자자별 가격대 막대, 종가, 예탁금·신용공여 추이', 'tut-shot-natural')}
          <div class="tut-two tut-two-tight">
            ${feats([
              ['막대', '가격대마다 <b>개인</b>(파랑)·<b>외국인</b>(분홍)·<b>기관</b>(보라)이 순매수(오른쪽)·순매도(왼쪽)한 금액.'],
              ['흰 선', '같은 기간의 종가. 막대와 같은 세로축(가격)을 씁니다.'],
              ['점선 네 개', "'예탁금&nbsp;· 신용공여' 버튼을 켜면 투자자 예탁금·신용융자·미수금·반대매매가 같은 날짜축에 겹쳐집니다."],
            ])}
            ${feats([
              ['종목&nbsp;· 기간', '위 칩으로 코스피 지수나 종목을, 아래 버튼으로 1·2·3·6개월·전체를 고릅니다.'],
              ['점선은 기울기만', '네 값은 규모가 100배 넘게 차이 나서 각자의 범위로 그렸습니다. 선끼리 높이를 비교하지 마세요.'],
              ['매집도가 아닙니다', '실측 일별 수급을 종가 가격대에 쌓은 것이고, 체결 단위 데이터는 공개되지 않습니다.'],
            ])}
          </div>`)}
      </div>
      <div class="tut-block tut-two">
        ${card('WHO&nbsp;· WHEN', `${shot('/fin_derivatives', 'ms-flows.webp', '종가일 수급 표')}
          <h4>종가일 수급</h4><p>시총 상위 종목마다 그날 <b>개인·외국인·기관</b>이 몇 주를 순매수했는지. 행의 '그 주 →'를 누르면 그 주의 날짜별 흐름이 열립니다.</p>`)}
        ${card('CREDIT&nbsp;· MARGIN', `${shot('/fin_derivatives', 'ms-credit.webp', '투자자 예탁금·신용공여 카드')}
          <h4>투자자 예탁금&nbsp;· 신용공여</h4><p>대기 중인 돈(예탁금)과 빌려서 산 돈(<b>신용융자&nbsp;· 미수금</b>), 강제 청산(<b>반대매매</b>)의 최신 값. 금융투자협회 FreeSIS 공개 집계라 시장 전체 합계이고, 종목별 숫자는 아닙니다.</p>`)}
      </div>

      <div class="tut-block">
        <h3>계산기 두 개</h3>
        <div class="tut-two">
          ${card('COMPANY VALUATION', `<h4>기업 가치 계산기</h4>
            <p>종목을 검색하면 OpenDART 연결재무제표를 불러와 최근 회계연도들을 나란히 놓습니다. 회계상 이익과 실제 현금흐름(영업활동현금흐름&nbsp;· 이익의 질)을 나눠 봅니다.</p>
            <a class="tut-link" href="/fin_valuation" target="_blank" rel="noopener">기업 가치 계산기 열기 ↗</a>`)}
          ${card('PORTFOLIO LAB', `<h4>포트폴리오 계산기</h4>
            <p>과거 전략을 돌려보는 <b>시나리오 백테스트</b>와, 지금 보유 자산의 위험 쏠림을 보는 <b>직접 입력</b> 두 모드입니다. 어느 쪽도 수익 예측이 아닙니다.</p>
            <a class="tut-link" href="/fin_portfolio" target="_blank" rel="noopener">포트폴리오 계산기 열기 ↗</a>`)}
        </div>
      </div>

      <div class="tut-block">
        <h3>백테스팅 하는 법</h3>
        ${steps([
          ['시나리오 백테스트 모드 선택', '상단 모드 버튼에서 전환합니다.'],
          ['자산 담기', '이름으로 검색하면 티커로 해석됩니다.'],
          ['비중과 기준통화 정하기', '비중 합을 100%로 맞춥니다.'],
          ['기간 설정 후 실행', '백그라운드에서 돌아가 화면이 멈추지 않습니다.'],
        ])}
        <p class="tut-note">백테스트 결과는 과거 전략 연구용입니다. 현재 보유 재평가 방식의 규제용 VaR 백테스트와는 다릅니다.</p>
      </div>`,

    politics: () => `
      ${head('POLICY &amp; ELECTIONS', '정치 &amp; 정책 — 법안을 따라가고, 권력을 읽는다',
        '정책 메뉴는 미국 법안·행정명령을 단계별로 추적합니다. 정치 메뉴는 각 나라의 권력 구조와 선거, 그리고 선거에 들어간 돈을 봅니다.')}

      ${sub('정책 — 상임위에서 법안으로', '발의된 법안은 먼저 소관 상임위로 갑니다. 그래서 주요 상임위 화면에서 시작하면 지금 어떤 법안이 어느 단계에 걸려 있는지 한 번에 보입니다.')}
      <div class="tut-block tut-two">
        ${card('COMMITTEE → BILL&nbsp;· 하원 세입위원회', `${shot('/policy/us/bill/119-hres-1156', 'policy-bill.webp', '하원 세입위원회를 거친 법안 상세 화면')}
          <h4>상임위를 거친 법안 한 건</h4><p>법안을 열면 지금 단계가 <b>발의 → 위원회 회부·심사 → 상임위 보고 → 본회의 통과</b> 레일로 보이고, 오른쪽에 회부 위원회·분류·법안 원문(PDF)이 붙습니다. 표결이 있었다면 찬반 수까지 나옵니다. 위쪽 경로에서 위원회 이름을 누르면 그 상임위의 소관 법안 목록으로 올라갑니다.</p>`)}
        ${card('SEARCH&nbsp;· "수출통제"', `${shot(`/policy/us/search/${encodeURIComponent('수출통제')}`, 'policy-search.webp', '정책 검색 결과: 수출통제')}
          <h4>제정법안&nbsp;· 발의법안&nbsp;· 행정명령</h4><p>검색 결과는 세 칸으로 갈립니다. 통과된 <b>제정법안</b>, 아직 진행 중인 <b>발의법안</b>, 그리고 <b>행정명령</b>. 발의법안에는 지금 단계(회부&nbsp;· 위원회 심사 등)가 함께 붙습니다.</p>
          ${chips(['발의&nbsp;· 회부', '위원회 심사', '발의원 본회의 통과', '제정'], ['발의&nbsp;· 회부', '위원회 심사', '발의원 본회의 통과', '제정'])}`)}
      </div>
      <div class="tut-block tut-two tut-two-plain">
        <div>
          <h3>검색 키워드는 이렇게</h3>
          ${feats([
            ['법안 이름으로', '"CLARITY"처럼 약칭을 넣으면 그 법안과 이름이 비슷한 법안이 함께 뜹니다.'],
            ['주제어로', '"수출통제", "스테이블코인", "니켈". 임베딩으로 의미를 비교하므로 그 단어가 본문에 그대로 없어도 관련 법안이 걸립니다.'],
            ['행정명령도 같이', '같은 검색창에서 법안과 행정명령이 함께 나옵니다.'],
          ])}
        </div>
        <div>
          <h3>법안 팔로우하는 법</h3>
          ${steps([
            ['법안 카드의 ★', '목록에서든 상세에서든 별 하나로 담깁니다.'],
            ['마이페이지에서 모아 보기', '담은 법안이 한곳에 쌓입니다. 다시 누르면 해제됩니다.'],
            ['단계가 바뀌면 메일', '항목별 음소거와 계정 전체 일시정지가 따로 있습니다.'],
          ])}
        </div>
      </div>

      <div class="tut-rule"></div>

      ${sub('정치 — 권력 구조와 선거 돈', '세계 선거 지도에서 나라를 고르면 행정부·의회·정당 블록이 열립니다. 미국은 주를 누르면 그 주의 선거와 외부 지출까지 내려갑니다.')}
      <div class="tut-block tut-two">
        ${card('EXECUTIVE&nbsp;· 백악관', `${shot('/politics/USA/executive', 'us-executive.webp', '미국 행정부 창')}
          <h4>백악관 — 누가 어디에 앉아 있나</h4><p>대통령·부통령·비서실장, 국가안보회의(NSC)·국가경제위원회(NEC)·무역대표부(USTR) 같은 직속 위원회의 수장, 그리고 분야별 특별보좌관까지 한 창에 모입니다.</p>`)}
        ${card('SUPER PAC&nbsp;· 캘리포니아', `${shot('/politics/USA/CA?view=finance', 'us-ca-superpac.webp', '캘리포니아 외부 독립지출 화면')}
          <h4>외부 독립지출 — 후보 밖에서 쓴 돈</h4><p>슈퍼팩 같은 외부 단체가 특정 후보를 <b>지지</b>하거나 <b>반대</b>하려고 쓴 돈입니다. 후보 캠프의 후원금이 아닙니다. 주 화면에서 '선거' 버튼을 켜면 나옵니다.</p>`)}
      </div>
      <div class="tut-block">
        <div class="tut-card tut-row">
          ${shot('/politics', 'elections.webp', '세계 선거 지도와 일정')}
          <div>
            <div class="tut-label">ELECTION CALENDAR</div>
            <h4>선거 일정&nbsp;· 결과</h4>
            <p>왼쪽 날짜순 일정과 지도가 연동됩니다. 선거 유형별로 색이 다르고, 끝난 선거는 결과로 이어집니다.</p>
          </div>
        </div>
      </div>`,

    shipping: () => `
      ${head('FLEET &amp; CHOKEPOINTS', '해운 — 선대 규모와 길목',
        '해운 메뉴는 "배가 얼마나 있나"와 "길이 막히면 어떻게 되나"를 나눠서 봅니다. 화면 위쪽 탭으로 오갑니다.')}
      <div class="tut-block tut-two">
        ${card('OBSERVED FLEET', `${shot('/shipping_fleet', 'fleet.webp', '글로벌 선대 화면')}
          <h4>글로벌 선대</h4><p>선종별 선복량과 세계 비중입니다. 이 화면의 숫자만 관측값이고, 나머지 화면은 이 선대를 기준으로 한 추정·시나리오입니다.</p>`)}
        ${card('CHOKEPOINT MONITOR', `${shot('/shipping_chokepoints', 'chokepoints.webp', '초크포인트 모니터 화면')}
          <h4>초크포인트 모니터</h4><p>주요 길목의 <b>최근 7일 일평균</b>을 <b>직전 28일 기준선</b>과 비교한 단기 이상 신호입니다. 물리적 봉쇄율이 아닙니다.</p>`)}
      </div>
      <div class="tut-block">
        <h3>나머지 세 화면</h3>
        ${feats([
          ['항로 운항 선복량', '항로별 연간 화물량과 그걸 나르는 데 필요한 선복량. 우회 시 추가분까지 같이 나옵니다.'],
          ['충격 시뮬레이터', '길목이 막혔다고 가정하면 선종별로 얼마가 묶이고 28일 뒤 백로그가 얼마나 쌓이는지 계산합니다.'],
          ['넷제로 경로', '감속·개조·퇴출 가정이 연도별 유효 선복량을 얼마나 잠식하는지. 대표 항로 기준이며 세계 선대 전체 예측은 아닙니다.'],
        ])}
        <p class="tut-note">표의 각 행에는 그 숫자가 관측값인지 모델 추정인지 성격이 함께 붙습니다. 숫자만 떼어 읽지 마세요.</p>
      </div>`,
  };

  const tabFromUrl = () => {
    const t = new URLSearchParams(window.location.search).get('tab');
    return TABS.some((x) => x.id === t) ? t : TABS[0].id;
  };

  const render = (host) => {
    if (!host) return;
    const active = tabFromUrl();
    host.innerHTML = `
      <div class="tut-wrap">
        <header class="tut-masthead">
          <div class="tut-brand">CHOKEPOINT MONITOR</div>
          <h1>화면별 사용설명서</h1>
          <p class="tut-lede">네 영역을 골라서 보세요. 어떤 화면이 있고, 무엇을 클릭하면 무엇이 열리며, 즐겨찾기와 메일 알림까지 어떻게 이어지는지 설명합니다.</p>
          <div class="tut-hint"><span aria-hidden="true">↗</span> 화면 사진을 누르면 실제 화면이 새 탭으로 열립니다.</div>
        </header>
        <div class="tut-tabbar">
          <div class="tut-tabs" role="tablist" aria-label="설명 영역 선택">
            ${TABS.map((t) => `
              <button type="button" class="tut-tab" role="tab" id="tut-tab-${t.id}" data-tut-tab="${t.id}" data-hue="${t.hue}"
                aria-controls="tut-panel-${t.id}" aria-selected="${t.id === active}" tabindex="${t.id === active ? 0 : -1}">
                <span class="tut-tab-label">${t.label}</span>
                <span class="tut-tab-sub">${t.sub}</span>
              </button>`).join('')}
          </div>
        </div>
        ${TABS.map((t) => `
          <section class="tut-panel" id="tut-panel-${t.id}" role="tabpanel" aria-labelledby="tut-tab-${t.id}"
            data-hue="${t.hue}"${t.id === active ? '' : ' hidden'}>${PANELS[t.id]()}</section>`).join('')}
      </div>`;

    const tabs = [...host.querySelectorAll('[data-tut-tab]')];
    const select = (id, focus) => {
      tabs.forEach((b) => {
        const on = b.dataset.tutTab === id;
        b.setAttribute('aria-selected', String(on));
        b.tabIndex = on ? 0 : -1;
        host.querySelector(`#tut-panel-${b.dataset.tutTab}`).hidden = !on;
        if (on && focus) b.focus();
      });
      const url = new URL(window.location.href);
      url.searchParams.set('tab', id);
      window.history.replaceState(window.history.state, '', url.pathname + url.search);
      const bar = host.querySelector('.tut-tabbar');
      if (bar && host.scrollTop > bar.offsetTop) host.scrollTop = bar.offsetTop;
    };
    const smooth = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    host.querySelectorAll('[data-tut-jump]').forEach((b) => b.addEventListener('click', () => {
      host.querySelector(`#tut-step-${b.dataset.tutJump}`)?.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'start' });
    }));
    tabs.forEach((b, i) => {
      b.addEventListener('click', () => select(b.dataset.tutTab, false));
      b.addEventListener('keydown', (e) => {
        const step = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
        if (!step) return;
        e.preventDefault();
        select(tabs[(i + step + tabs.length) % tabs.length].dataset.tutTab, true);
      });
    });
  };

  const unmount = (host) => {
    if (host && host.querySelector('.tut-wrap')) host.innerHTML = '';
  };

  window.Tutorial = { render, unmount };
})();
