# 미확인 품목의 공식 자료 확인

확인일: 2026-10-12. PR #528의 제한된 수동 검토 스냅샷이다. 자료 검색 완료, 대표 품목분류, 조건부 관세 경로, 기업별 AD/CVD 적용 확정을 구분한다. 특정 기업의 모든 제품을 확인했다는 뜻이 아니다.

## 연결한 결과

| 품목 | 확인 결과 | 계산 연결 및 남은 조건 |
| --- | --- | --- |
| 제동 시스템 | 대표 HTS 8708.30.50, Column 1 General 2.5% | 한국·일본 승용차/경트럭용 지정 부품 조건부 합산 15%. 전자제어 단품의 분류 별도 |
| 조향 시스템 | 대표 HTS 8708.94.50.00, General 2.5% | 위 조건부 15%. 조향 휠·칼럼·박스 완성품이며 별도 부분품과 구분 |
| 현가 시스템 | 대표 HTS 8708.80.16, General 2.5% | 위 조건부 15%. McPherson strut 이외 현가 시스템 대표 사양. strut·부분품 별도 |
| 전동화 구동·전력변환 | 모터 8501 / 정지형 변환기 8504.40 분류 후보 | 출력·AC/DC·기능·조립 상태 필요. HTS8·자동 관세 미확정 |
| OCTG | A-580-870 및 C-580-913 사건 존재. 2026-19529 최종 마진 표 | 과거 마진만 표시. 현행 예치율·CVD율 자동 계산 미연결 |
| 현가 관련 유압실린더 | A-580-923 조사 개시 및 정정 | 해당 제품과 조사 서술 범위의 대조 필요. HL만도 조사·제품 적용·예치율을 추정하지 않음 |
| 나머지 검토 품목 | 한국 활성 사건 제품명 목록에서 직접 대응 사건 미발견 | AD/CVD 면제·0% 판정이 아님. 다른 원산지에 결과 복사 금지 |

제조사 공식 제품 자료와 HTS 대표 사양을 연결했으나 실제 부품번호·도면과 동일성을 판정하지 않았다. 사용자는 조건 확인 후 대표 시나리오로 계산하거나, 실제 제품의 확인한 총 세율을 직접 입력한다. 한국 기업의 미국 생산을 한국산으로 간주하지 않는다.

## 자동차 부품 관세 근거

- USITC **2026 HTS Revision 21**, 현행 [Chapter 87](https://hts.usitc.gov/reststop/file?release=currentRelease&filename=Chapter%2087)의 위 분류 및 [Chapter 99](https://hts.usitc.gov/reststop/file?release=currentRelease&filename=Chapter%2099) Note 33(g)의 승용차·경트럭 부품 목록을 대조. Chapter 87 PDF 23페이지의 현가 구분, Chapter 99 PDF 521페이지의 Note 33(g)를 렌더링 확인했다.
- 한국: [2025-21940 Part A](https://www.govinfo.gov/content/pkg/FR-2025-12-04/pdf/2025-21940.pdf), 현행 [9903.94.63](https://hts.usitc.gov/search?query=9903.94.63), Note 33(t).
- 일본: [2025-17908](https://www.govinfo.gov/content/pkg/FR-2025-09-16/pdf/2025-17908.pdf), 현행 [9903.94.43](https://hts.usitc.gov/search?query=9903.94.43), Note 33(l). **9903.94.53은 EU 항목**으로 일본에 사용하지 않는다.
- General 기본관세 2.5%를 위 합산 15%에 다시 더하지 않는다. KORUS 특혜·원산지·실제 용도·입항 시점 등은 개별 거래 확인 대상이다. AD/CVD·다른 추가세·수입조정 상계는 이 15%로 확정되지 않는다. [CBP CSMS 69087399](https://content.govdelivery.com/accounts/USDHSCBP/bulletins/41e30a7)의 상계 절차를 개별 기업에 자동 적용하지 않았다.
- 모터와 인버터를 하나의 자동차 부품 HTS로 정하지 않는다. Note 33(g)에는 특정 8501 분류가 있지만 8504.40을 같은 목록에 자동 포함하지 않는다. 다른 인증·용도 경로 적용도 구체 사양 확인 전 보류한다.

## AD/CVD 검색 범위

[Commerce ACCESS 활성 사건 검색](https://access.trade.gov/adcvd)에서 `Korea` 검색, 6페이지 **51개 고유 사건**의 제품명을 전부 읽었다. [상무부 설명](https://www.trade.gov/data-visualization/adcvd-proceedings)에 따르면 활성 조사·명령·중지협정 검색 자료다. 원 명령의 서술 범위·개별 scope ruling·우회수출·타국산 및 모든 기업의 과거 사건을 전수 확인한 것은 아니다.

17개 제품에 검토 결과를 연결: 직접 대응 미발견 15개(완성차4, 제동/조향/전동화3, 차단기1, 케이블3, 타이어코드/탄소섬유/아라미드3, 트럭버스 타이어1), 관련 조사 범위 검토 1개(현가), 사건·마진 확인/예치 미확정 1개(OCTG). 기존 5개 계산 사건·33개 법인은 그대로다.

제품명 미발견은 법적인 비대상 판정이 아니다. 원산지 공란·한국 외 원산지에는 `origin_not_reviewed`를 사용한다. 모든 신규 AD 검토 결과의 `rate_pct`는 null이며 기존 사건의 예치율을 복사하지 않는다.

### OCTG

[2026-19529](https://www.govinfo.gov/content/pkg/FR-2026-09-24/pdf/2026-19529.pdf), 2026-09-24 공표, POR 2023-09-01~2024-08-31. 표의 SeAH Steel Corporation 최종 마진 9.80%, NEXTEEL Co., Ltd. 29.94%를 기록했다. 과거 재심 마진이며 현재 예치율로 표시하지 않는다.

Cash Deposit Requirements의 `simple-average` 문구와 기업별 표의 대응은 CBP 지침/ACCESS/정정 확인이 필요하다. 9.80% 또는 두 마진의 평균을 임의로 현재 예치율에 사용하지 않는다. 대구경 용접강관의 0.80%도 상속하지 않는다. C-580-913은 사건 존재만 확인했으며 CVD율은 미검토다.

### 관련 유압실린더

[2026-18706 조사 개시](https://www.govinfo.gov/content/pkg/FR-2026-09-14/pdf/2026-18706.pdf) 및 [2026-19374 정정](https://www.govinfo.gov/content/pkg/FR-2026-09-22/pdf/2026-19374.pdf). 자동차 현가장치 전체 또는 HL만도를 대상 기업으로 확정하지 않는다. 실제 치수·설계·기능과 원문 범위 대조가 필요하다. 제소 주장 마진은 현금예치율이 아니다.

### 확인한 ACCESS 사건 목록

아래는 2026-10-12 화면에 표시된 순서의 제품명·사건번호 수기 기록이다. 후속 사건·삭제·범위 변경은 자동 반영되지 않는다.

| 페이지 | 사건 | 화면 제품명 |
| --- | --- | --- |
| 1 | A-580-852 | Prestressed Concrete Steel Wire Strand |
| 1 | A-580-876 | Welded Line Pipe |
| 1 | A-580-886 | Ferrovanadium |
| 1 | A-580-893 | Fine Denier Polyester Staple Fiber |
| 1 | A-580-914 | Superabsorbent Polymers |
| 1 | A-580-921 | Monomers and Oligomers |
| 1 | C-580-920 | Epoxy Resins |
| 1 | A-580-872 | Non-Oriented Electrical Steel |
| 1 | A-580-881 | Cold-Rolled Steel Flat Products |
| 1 | A-580-890 | Emulsion Styrene-Butadiene Rubber |
| 2 | A-580-908 | Passenger Vehicle and Light Truck Tires |
| 2 | C-580-910 | Seamless Carbon and Alloy Steel Standard, Line, and Pressure Pipe |
| 2 | C-580-882 | Cold-Rolled Steel Flat Products |
| 2 | C-580-888 | Carbon and Alloy Steel Cut-To-Length Plate |
| 2 | A-580-834 | Stainless Steel Sheet And Strip In Coils |
| 2 | A-580-859 | Light-Walled Rectangular Pipe And Tube |
| 2 | A-580-897 | Large Diameter Welded Carbon and Alloy Steel Line and Structural Pipe |
| 2 | C-580-917 | Brass Rod |
| 2 | A-580-810 | Welded Astm A-312 Stainless Steel Pipe |
| 2 | A-580-867 | Large Power Transformers |
| 3 | A-580-885 | Phosphor Copper |
| 3 | A-580-902 | Utility Scale Wind Towers |
| 3 | C-580-879 | Corrosion-Resistant Steel Products |
| 3 | A-580-919 | Epoxy Resins |
| 3 | A-580-892 | Cold-Drawn Mechanical Tubing |
| 3 | A-580-916 | Brass Rod |
| 3 | A-580-878 | Corrosion-Resistant Steel Products |
| 3 | A-580-899 | Acetone |
| 3 | A-580-904 | Forged Steel Fittings |
| 3 | C-580-837 | Certain Cut-To-Length Carbon-Quality Steel Plate |
| 4 | C-580-898 | Large Diameter Welded Carbon and Alloy Steel Line and Structural Pipe |
| 4 | C-580-913 | Oil Country Tubular Goods |
| 4 | A-580-887 | Carbon and Alloy Steel Cut-To-Length Plate |
| 4 | A-580-922 | Polytetramethylene Ether Glycol |
| 4 | A-580-874 | Steel Nails |
| 4 | A-580-895 | Low Melt Polyester Staple Fiber |
| 4 | A-580-891 | Carbon and Alloy Steel Wire Rod |
| 4 | A-580-836 | Certain Cut-To-Length Carbon-Quality Steel Plate |
| 4 | A-580-870 | Oil Country Tubular Goods |
| 4 | C-580-835 | Stainless Steel Sheet And Strip In Coils |
| 5 | A-580-889 | Dioctyl Terephthalate (Dotp) |
| 5 | A-580-809 | Circular Welded Non-Alloy Steel Pipe |
| 5 | A-580-880 | Heavy Walled Rectangular Welded Carbon Steel Pipes and Tubes |
| 5 | A-580-903 | Polyethylene Terephthalate Sheet |
| 5 | A-580-829 | Stainless Steel Wire Rod |
| 5 | A-580-911 | Thermal Paper |
| 5 | A-580-839 | Polyester Staple Fiber |
| 5 | A-580-883 | Hot-Rolled Steel Flat Products |
| 5 | A-580-909 | Seamless Carbon and Alloy Steel Standard, Line, and Pressure Pipe |
| 5 | C-580-884 | Hot-Rolled Steel Flat Products |
| 6 | A-580-923 | Linear Hydraulic Cylinders and Parts Thereof |

## UI·JSON·검증

국가·기업·반덤핑 품목 선택에 접힌 `공식 자료 확인 결과`를 추가했다. 대표 분류/조건부 관세/AD 검토/남은 조건/공식 원문/확인일을 작은 설명으로 제공한다. 국가·기업 JSON에 `product_verification`을 보존한다. 공급국 통계가 없는 신규 품목은 출처와 연도를 null로 기록한다.

관련 Node 89개, 소유권 회귀 7개, 브라우저 4종 통과. 대표 부품 한국 15→30 계산, 조건 확인, 잘못된 원산지 격리, 수록되지 않은 공급국 통계 null, OCTG 마진/예치 구분, 전동화 분류 보류, 기존 40프로필/22품목/5사건/33법인, 360px·원문 링크·외부 호출 없음을 확인했다.

남은 자료는 실제 제품 사양·원산지, 기업별 적용 공고와 CBP 예치 지침, 제품별 공급국 통계·탄력성·비공개 거래/원가다. 로컬 미리보기와 PR 검토 범위이며 main 병합·운영 배포·DB·상시 수집·메일·유료 AI 호출은 하지 않았다.
