// Curated official notices; rates are not inferred by an LLM. See docs/antidumping-simulator.md.
export const AD_CATALOG = {
  "schema_version": 1,
  "checked_on": "2026-10-11",
  "coverage": "selected_official_notices_only",
  "coverage_note": "선별한 공식 공고의 기업별 마진·예치 조건을 확인한 자료입니다. 사건 전체 정정·법원 명령·CBP 지침을 전수 확인한 현재 적용 세율 서비스는 아닙니다. 기업·제품 범위·수출자/생산자 조합을 확인해야 하며 누락 구간은 미확인입니다.",
  "documents": {
    "2012-21613": {
      "document_id": "2012-21613",
      "published": "2012-08-31",
      "kind": "order",
      "title": "대형 전력용 변압기 반덤핑 명령",
      "url": "https://www.govinfo.gov/content/pkg/FR-2012-08-31/pdf/2012-21613.pdf",
      "notes": "대상 범위의 서술이 HTS 코드보다 우선합니다.",
      "verified_on": "2026-10-11"
    },
    "2025-05960": {
      "document_id": "2025-05960",
      "published": "2025-04-08",
      "kind": "review_final",
      "title": "변압기 2022–2023 최종결과",
      "url": "https://www.govinfo.gov/content/pkg/FR-2025-04-08/pdf/2025-05960.pdf",
      "notes": "현대 0%, 일진 16.87%, LS 16.87%. 효성의 이 기간 결과는 이 공고에 없습니다.",
      "verified_on": "2026-10-11"
    },
    "2026-02646": {
      "document_id": "2026-02646",
      "published": "2026-02-10",
      "kind": "review_preliminary",
      "title": "변압기 2023–2024 예비결과",
      "url": "https://www.govinfo.gov/content/pkg/FR-2026-02-10/pdf/2026-02646.pdf",
      "notes": "예비 마진이며 새 현금예치율 발효 공고가 아닙니다.",
      "verified_on": "2026-10-11"
    },
    "2026-16663": {
      "document_id": "2026-16663",
      "published": "2026-08-14",
      "kind": "review_final",
      "title": "변압기 2023–2024 최종결과",
      "url": "https://www.govinfo.gov/content/pkg/FR-2026-08-14/pdf/2026-16663.pdf",
      "notes": "두 조사기업 0%, 비선정 LS·효성 4.32%. 최종 공고는 다른 합리적 방법을 사용했다고 설명합니다. 상세 결정문은 별도 ACCESS 확인이 필요합니다.",
      "verified_on": "2026-10-11"
    },
    "2026-20160": {
      "document_id": "2026-20160",
      "published": "2026-10-01",
      "kind": "review_initiation",
      "title": "복수 사건 행정재심 개시",
      "url": "https://www.govinfo.gov/content/pkg/FR-2026-10-01/html/2026-20160.htm",
      "notes": "변압기 A-580-867 부분만 연결. 개시는 조사기업 선정이나 새 세율 확정이 아닙니다.",
      "verified_on": "2026-10-11"
    },
    "2026-14027": {
      "document_id": "2026-14027",
      "published": "2026-07-13",
      "kind": "review_final",
      "title": "한국 승용차·경트럭 타이어 2023–2024 최종결과",
      "url": "https://www.govinfo.gov/content/pkg/FR-2026-07-13/pdf/2026-14027.pdf",
      "notes": "한국타이어 13.03%, 넥센 8.02%, 금호 10.53%. 금호의 실제 가중치는 이 공고만으로 재구성하지 않습니다.",
      "verified_on": "2026-10-11"
    }
  },
  "cases": [
    {
      "case_id": "A-580-867",
      "product": "대형 전력용 변압기",
      "country": "KR",
      "order_date": "2012-08-31",
      "companies": [
        {
          "id": "hyundai",
          "name": "HD현대일렉트릭",
          "official_name": "HD Hyundai Electric Co., Ltd.",
          "aliases": []
        },
        {
          "id": "iljin",
          "name": "일진전기",
          "official_name": "Iljin Electric Co., Ltd.",
          "aliases": [
            "ILJIN"
          ]
        },
        {
          "id": "ls",
          "name": "LS일렉트릭",
          "official_name": "LS Electric Co., Ltd.",
          "aliases": []
        },
        {
          "id": "hyosung",
          "name": "효성중공업",
          "official_name": "Hyosung Heavy Industries Corporation",
          "aliases": []
        }
      ],
      "scope": {
        "description": "한국산 액체 유전체 전력용 변압기, 최대 용량 60MVA 이상. 미조립·미완성도 포함될 수 있습니다. 부품·수리품은 서술 범위와 개별 판단을 확인해야 합니다.",
        "document_id": "2012-21613",
        "hts": [
          "8504.23.0040",
          "8504.23.0080",
          "8504.90.9540"
        ],
        "automatic_determination": false
      },
      "all_others_reference": {
        "rate_pct": "22.00",
        "source": "2026-16663",
        "note": "이전 조사·재심 적용 여부와 수출자/생산자 조합을 확인해야 합니다. 미등록 기업에 자동 적용하지 않습니다."
      },
      "segments": [
        {
          "document_id": "2025-05960",
          "por_start": "2022-08-01",
          "por_end": "2023-07-31",
          "stage": "final",
          "cash_deposit_effective": "2025-04-08",
          "rates": [
            {
              "company_id": "hyundai",
              "margin_pct": "0",
              "examined": true,
              "entirely_facts_available": false
            },
            {
              "company_id": "iljin",
              "margin_pct": "16.87",
              "examined": true,
              "entirely_facts_available": false
            },
            {
              "company_id": "ls",
              "margin_pct": "16.87",
              "examined": false,
              "entirely_facts_available": false
            }
          ],
          "reason": "유효한 개별 마진이 일진 한 곳이어서 비선정 LS에 같은 마진을 부여.",
          "rule_basis": "해당 공고: §735(c)(5)를 행정재심 지침으로 참조"
        },
        {
          "document_id": "2026-02646",
          "por_start": "2023-08-01",
          "por_end": "2024-07-31",
          "stage": "preliminary",
          "cash_deposit_effective": null,
          "rates": [
            {
              "company_id": "hyundai",
              "margin_pct": "0",
              "examined": true,
              "entirely_facts_available": false
            },
            {
              "company_id": "iljin",
              "margin_pct": "0",
              "examined": true,
              "entirely_facts_available": false
            },
            {
              "company_id": "ls",
              "margin_pct": "16.87",
              "examined": false,
              "entirely_facts_available": false
            },
            {
              "company_id": "hyosung",
              "margin_pct": "4.32",
              "examined": false,
              "entirely_facts_available": false
            }
          ],
          "reason": "모든 조사기업 마진이 0%이므로 비선정 기업의 기존 세율을 유지하는 예비 접근.",
          "rule_basis": "해당 공고: §735(c)(5)를 행정재심 지침으로 참조"
        },
        {
          "document_id": "2026-16663",
          "por_start": "2023-08-01",
          "por_end": "2024-07-31",
          "stage": "final",
          "cash_deposit_effective": "2026-08-14",
          "rates": [
            {
              "company_id": "hyundai",
              "margin_pct": "0",
              "examined": true,
              "entirely_facts_available": false
            },
            {
              "company_id": "iljin",
              "margin_pct": "0",
              "examined": true,
              "entirely_facts_available": false
            },
            {
              "company_id": "ls",
              "margin_pct": "4.32",
              "examined": false,
              "entirely_facts_available": false
            },
            {
              "company_id": "hyosung",
              "margin_pct": "4.32",
              "examined": false,
              "entirely_facts_available": false
            }
          ],
          "reason": "조사기업 둘 다 0%이나 다른 합리적 방법으로 비선정 기업 4.32%. 세부 산정 근거는 ACCESS 결정문 확인 필요.",
          "rule_basis": "해당 공고: §735(c)(5)를 행정재심 지침으로 참조"
        }
      ],
      "reviews": [
        {
          "document_id": "2026-20160",
          "por_start": "2025-08-01",
          "por_end": "2026-07-31",
          "status": "initiated",
          "companies": [
            "hyundai",
            "iljin",
            "ls",
            "hyosung"
          ],
          "respondent_selection": null,
          "target_final_date": null,
          "target_is_guaranteed": false
        }
      ],
      "litigation": []
    },
    {
      "case_id": "A-580-908",
      "product": "승용차·경트럭 타이어",
      "country": "KR",
      "order_date": "2021-07-19",
      "companies": [
        {
          "id": "hankook",
          "name": "한국타이어",
          "official_name": "Hankook Tire & Technology Co., Ltd.",
          "aliases": [
            "Hankook Tire Mfg Co. Ltd.",
            "Hankook Tire Co., Ltd."
          ]
        },
        {
          "id": "nexen",
          "name": "넥센타이어",
          "official_name": "Nexen Tire Corporation",
          "aliases": []
        },
        {
          "id": "kumho",
          "name": "금호타이어",
          "official_name": "Kumho Tire Co., Inc.",
          "aliases": []
        }
      ],
      "scope": {
        "description": "한국산 승용차·경트럭 타이어. 정확한 포함·제외 조건은 원 명령과 ACCESS 결정문을 별도로 확인해야 합니다. HS 4011이라는 이유만으로 대상이라고 판단하지 않습니다.",
        "document_id": "2026-14027",
        "hts": [],
        "automatic_determination": false
      },
      "all_others_reference": {
        "rate_pct": "21.74",
        "source": "2026-14027",
        "note": "모든 미등록 기업의 기본값이 아닙니다. 공고의 수출자·생산자 적용 조건 확인 필요."
      },
      "segments": [
        {
          "document_id": "2026-14027",
          "por_start": "2023-07-01",
          "por_end": "2024-06-30",
          "stage": "final",
          "cash_deposit_effective": "2026-07-13",
          "rates": [
            {
              "company_id": "hankook",
              "margin_pct": "13.03",
              "examined": true,
              "entirely_facts_available": false
            },
            {
              "company_id": "nexen",
              "margin_pct": "8.02",
              "examined": true,
              "entirely_facts_available": false
            },
            {
              "company_id": "kumho",
              "margin_pct": "10.53",
              "examined": false,
              "entirely_facts_available": false
            }
          ],
          "reason": "공표된 금호 10.53%를 사용. 한국타이어·넥센의 단순 평균 10.525%에서 실제 산정 가중치를 역추정하지 않습니다. 공고는 19 CFR 351.109(f)·(g)를 인용합니다.",
          "rule_basis": "2026-14027: 19 CFR 351.109(f)・(g), §735(c)(5)"
        }
      ],
      "reviews": [],
      "litigation": []
    }
  ],
  "legal_sources": [
    {
      "label": "상무부 AD/CVD 법령",
      "url": "https://www.trade.gov/legal-framework-antidumping-and-countervailing-duty-remedies"
    },
    {
      "label": "2026-14027 · 19 CFR 351.109(f)·(g) 적용 설명",
      "url": "https://www.govinfo.gov/content/pkg/FR-2026-07-13/pdf/2026-14027.pdf"
    },
    {
      "label": "19 CFR §351.109 비선정 기업",
      "url": "https://www.ecfr.gov/current/title-19/chapter-III/part-351/subpart-A/section-351.109"
    }
  ]
};
