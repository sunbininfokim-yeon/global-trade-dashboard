# 일정 세션 → 선거 구조 세션 (2026-10-20)

일정 세션이 넘긴다. 날짜를 다시 만들지 말 것. 제도(임기·정수·투표방법·결선·봉쇄)만 elections_system_v1.json 에 채운다. 당권은 국가 제도 행으로 만들지 말 것. 대진·후보는 하지 말 것. 10월 12일 이후 새 공고로 늘어난 선거는 없다.

## 추가 조사 (행이 없음)
- CAN 브리티시컬럼비아 주의회. can-2026-bc, 2026-10-24. 캘린더는 can-local을 가리키지만 그 행은 퀘벡 전용. BC 행을 새로 조사하고, can-local을 BC 행으로 고치지 말 것.
- BRA 주지사 결선. bra-2026-general-r2, 2026-10-25. system_id는 bra-president만. 주지사 행이 없음. bra-president의 2라운드 규칙은 보강 대상이 아님.
- JPN 후쿠시마현의회 보궐. jpn-2026-fukushima-assembly-by, 2026-10-25. system_id 비어 있음. 같은 날 지사 jpn-prefecture-governor로 대체하지 말 것.
- ISR 크네세트. isr-2026-knesset, 2026-10-27. ISR 제도 행 없음.
- RUS 지방 단일투표일. rus-2026-single-voting-day-regions, 2026-09-20. system_id 비어 있음. rus-duma에 붙이지 말 것.
- RUS 대선. rus-2026-presidential, 2030-03 (월만). 대선 행 없음. 일 단위로 만들지 말 것.
- IRN 전국선거. irn-2026-national, 2028-07 (월만). 행 없음. 일 단위로 만들지 말 것. 지도부 검토는 선거 제도 행이 아님.
- IND 주의회 묶음. ind-2026-state-pack, 날짜 불명. system_id 비어 있음. 날짜를 만들지 말 것.

## 보강 (행은 있으나 얇음)
- can-local: 퀘벡 127석만. BC 정수를 이 행에 덮지 말 것.
- pol-local: threshold_ko 불명. seats_total 2477은 그미나 수, 시장 1인 정수 아님. 결선 문장은 이미 있음. pol-2026-krakow-mayor 2026-09-27, pol-2026-krakow-mayor-r2 2026-10-11. 시 단위 id를 만들지 말 것.
- ind-rajya-sabha: 간선·6년·245석 이미 있음. ind-2026-rajya-sabha-oct 2026-10-16는 이 id 재사용. 회차마다 행을 복제하지 말 것. 보강 대상 아님.
- mex-deputies: method_ko가 하원 500석(3년)뿐. mex-2027-deputies 2027-06-06.
- mex-senate: 상원 128석(6년)뿐. mex-2030-senate 2030-06.
- mex-local: runoff_rule_ko 불명. mex-2027-state 2027-06-06. 대상 주 전수를 합산하지 말 것.
- ita-chamber: 하원 400·선출 상원 200뿐. 투표방법 문장 없음. 상원 별도 id 없음. ita-2027-general 2027-12. 이 id 재사용.
- aus-local: 주마다 다름, 정수는 사우스오스트레일리아 47석. aus-2026-sa 2026-03-21.
- phl-local: 직위 이름뿐. 정수는 방사모로 2026 회차 78. phl-2026-barmm 2026-09-14.
- tur-assembly: threshold_ko 불명. tur-2028-parliamentary 2028-05.
- nga-president: threshold_ko 불명, 주 분산 요건 불명. nga-2027-presidential 2027-02.
- zaf-local: method_ko가 지방 의회·와드. seats_total 1은 의석 합계가 아님. zaf-2026-local-government 2026-11-04.

## 하지 말 것
- 프랑스 코뮌 fra-2026-municipal-r1/r2는 전국 정수 없음. system_id 불명 유지.
- 국민투표와 CHN·SAU·ARE 경쟁선거 없음에는 제도 행을 만들지 말 것.
- 대통령 직선이 없는 JPN GBR CAN AUS ITA MYS THA VNM에는 대선 행을 만들지 말 것.
- null/0 금지. 없음=제도상 없음, 불명=못 찾음.

## 구조 세션이 채운 것 (2026-10-20)

날짜와 캘린더 `system_id` 는 건드리지 않았다. 제도 73행.

새로 만든 행: `can-bc` (93석, 최다득표), `bra-governor` (주·연방구 27, 유효표 과반 아니면 10월 마지막 일요일 결선). `bra-president` 결선 문장은 그대로다.

보강한 행: `can-local` 은 퀘벡 127석으로 이름을 고정했다. `pol-local` 단체장 과반·14일 재투표. `mex-deputies` 300+200과 비례 3%. `mex-senate` 64+32+32. 상원 비례 봉쇄 숫자는 불명. `ita-chamber` 1표 혼합, 명부 3%·연합 10%. `aus-local` 은 사우스오스트레일리아 하원 47석 완전 선호투표. `phl-local` 은 방사모로 80석(40+32+8), 정당대표 4%. `tur-assembly` 전국 유효표 7%. `nga-president` 는 헌법 134조의 최다득표와 3분의 2 분산.

이미 있어 다시 만들지 않은 것: `isr-knesset`, `jpn-fukushima-assembly`. `zaf-local` 은 의석 10,526으로 이미 채워져 있어 1로 되돌리지 않았다.

행을 만들지 않은 것: 러시아 단일투표일 지방은 전국 정수가 없어 `rus-duma` 에도 붙이지 않았다. 러시아 대선·이란 전국선거는 조문 원문을 이 회차에 열지 않아 월만 있는 일정에 정수를 만들지 않았다. 이란 일정은 대선과 마줄리스가 한 행이라 하나를 합치면 거짓 정수가 된다. 인도 주의회 묶음은 날짜가 없고 주 의석을 합치지 않는다. 멕시코 주 선거 결선은 연방 공통 규정을 찾지 못해 불명이다.
