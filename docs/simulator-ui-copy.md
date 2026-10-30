# 시뮬레이터 UI 문구·설명 기준

정책 대시보드의 짧은 명사형 제목·항목명에 맞춘다. 제목에 계산 질문이나 입력 지시를 넣지 않고 설명 문장과 분리한다. 국가·반덤핑·기업 탭과 계산 동작은 유지한다.

| 영역 | 대표 제목 | 보조 설명 |
| --- | --- | --- |
| 국가 | 국가별 관세 영향 / 시장·관세 조건 / 공급국별 물량 변화 | 구매액 단위·탄력성·공급국 전환·미국 단일 품목시장 |
| 반덤핑 | 반덤핑 예치 부담·재심 현황 / 조사·재심·소송 진행 / 거래 금액·비교 예치율 | 예치율과 최종 관세, POR와 통관일, 개별조사와 비선정의 구분 |
| 기업 | 기업별 관세·손익 분석 / 판매·원가 조건 / 손익분기·경쟁 조건 | 수출자 흡수율·제품 손익·국가 평균 반응 연결 |

제목은 20~24px, 첫 설명은 12px, 입력칸의 보조 설명은 11px로 둔다. 각 탭 상단에 기본 접힘 상태의 ‘계산 원리·용어’를 배치하고 짧은 계산 흐름·용어 설명·원문 링크를 제공한다. 필수 적용 조건·미확인 상태·가정 표시를 접힘 영역으로 숨기지 않는다. 긴 산식과 적용 한계는 기존 하단 상세 영역에 유지한다.

- 국가: [USITC 모형 소개·Excel 원본](https://www.usitc.gov/ces_tariff_model), [연구 원문 §2.1](https://www.usitc.gov/sites/default/files/data/gravity/structural_equations_for_pe_models_in_group_1.pdf). 구조를 참고한 자체 계산이며 공식 전망·Excel 실행 결과로 표현하지 않는다.
- 반덤핑: [상무부 FAQ](https://www.trade.gov/antidumping-and-countervailing-duty-frequently-asked-questions), [19 CFR §351.212](https://www.ecfr.gov/current/title-19/chapter-III/part-351/subpart-B/section-351.212). 사건·법인·POR별 근거 공고는 단계 카드와 세율 이력에 유지한다. FAQ 설명과 법적 근거 규정을 구분한다.
- 기업: 제품 손익은 자체 산식이다. 하단에 전체 산식을 명시하고 국가 연결에 참고하는 USITC 모형만 외부 원문으로 연결한다. 자체 기업 산식을 USITC 공식 모형으로 소개하지 않는다.

외부 링크는 새 탭으로 열며 `noopener noreferrer`를 지정한다. 360px에서도 용어 설명과 원문 링크가 화면 밖으로 넘치지 않게 줄바꿈한다. 모델·공표 세율·단계 기록·미확인 값의 처리는 이 UI 변경으로 수정하지 않는다.

검증 화면: `docs/previews/{country,antidumping,company}-ui-copy-{desktop,mobile}.png`.
