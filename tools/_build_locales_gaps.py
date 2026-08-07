#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Add remaining UI + main-branch export/SST/metals strings into locales. Run from repo root."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KO_PATH = ROOT / "locales" / "ko.json"
EN_PATH = ROOT / "locales" / "en.json"

PAIRS: list[tuple[str, str, str]] = [
    # --- metals menu (origin/main) ---
    ("nav.metals", "금속·광물", "Metals & minerals"),
    ("nav.dd.precious", "귀금속", "Precious metals"),
    ("nav.dd.industrial", "산업금속", "Industrial metals"),
    ("nav.dd.battery", "배터리·전략광물", "Battery & strategic minerals"),
    ("nav.dd.steel_feed", "철강 원료", "Steel feedstock"),
    ("nav.platinum", "백금족 (Pt·Pd)", "PGMs (Pt · Pd)"),
    ("nav.tin", "주석", "Tin"),
    ("nav.lead", "납", "Lead"),
    ("nav.nickel", "니켈", "Nickel"),
    ("nav.cobalt", "코발트", "Cobalt"),
    ("nav.lithium", "리튬", "Lithium"),
    ("nav.graphite", "흑연", "Graphite"),
    ("nav.rare_earths", "희토류", "Rare earths"),
    ("nav.iron_ore", "철광석", "Iron ore"),
    ("nav.manganese", "망간", "Manganese"),
    ("nav.chromium", "크롬", "Chromium"),
    # --- export controls (display strings; data file still has *_ko) ---
    ("export.note_seed", "수집 자동화 전 수기 정리본입니다. 각 항목에 근거 URL과 확인 시점을 답니다. 정책은 자주 바뀌므로 화면은 이 파일의 as_of 를 함께 표시하고, 최신 여부는 원문으로 확인해야 합니다.", "Hand-curated seed before collection is automated. Each row carries a source URL and checked-as-of date. Policies change often — show this file’s as_of on screen and verify currency against the original."),
    ("export.level.prohibited", "수출 금지", "Export ban"),
    ("export.level.restricted", "수출 제한 (쿼터·인허가·관세)", "Export restriction (quota · permit · tariff)"),
    ("export.level.watch", "통제 논의·검토", "Control under discussion · review"),
    ("export.measure.idn_nickel", "니켈 원광 수출 금지 — 국내 제련 유도", "Nickel ore export ban — push domestic refining"),
    ("export.measure.idn_bauxite", "보크사이트 원광 수출 금지", "Bauxite ore export ban"),
    ("export.measure.chn_gallium_ge", "갈륨·게르마늄 수출 허가제", "Gallium · germanium export licensing"),
    ("export.measure.chn_graphite", "흑연 수출 허가제", "Graphite export licensing"),
    ("export.measure.chn_rare_earths_tech", "희토류 추출·분리 기술 수출 금지 (기술 통제)", "Rare-earth extraction/separation tech export ban (tech control)"),
    ("export.measure.rus_wheat_duty", "밀 수출세(floating duty) 및 쿼터 운용", "Wheat export tax (floating duty) and quota"),
    ("export.measure.ind_rice", "비바스마티 백미 수출 제한·관세", "Non-basmati white-rice export limits · tariffs"),
    ("export.measure.arg_retenciones", "수출세(retenciones) 및 등록제(DJVE)", "Export taxes (retenciones) and DJVE registration"),
    ("export.measure.cod_cobalt", "코발트 수출 쿼터·일시 중단 조치", "Cobalt export quota · temporary suspension"),
    ("export.measure.tur_wheat_ban", "밀 수출 금지 (예외 승인 기반)", "Wheat export ban (exception approvals)"),
    ("export.measure.chl_lithium_strategy", "국가 리튬 전략 — 신규 개발 국영 참여 의무 (수출 금지 아님)", "National lithium strategy — state participation in new projects required (not an export ban)"),
    # --- SST regions ---
    ("sst.note_box_mean", "해역 평균 월별 편차입니다. 격자가 아니라 박스 평균이므로 해역 내부의 세부 구조는 표현하지 않습니다.", "Basin-mean monthly anomalies. Box averages, not the full grid — fine structure inside a basin is not shown."),
    ("sst.region.subpolar_atlantic", "북대서양 아북극 (블루 블롭)", "Subpolar North Atlantic (cold blob)"),
    ("sst.region.gulf_stream", "멕시코만류 (걸프스트림)", "Gulf Stream"),
    ("sst.region.nino34", "적도 동태평양 (Niño 3.4)", "Eastern equatorial Pacific (Niño 3.4)"),
    ("sst.region.west_pacific", "서태평양 웜풀", "Western Pacific warm pool"),
    ("sst.region.north_pacific", "북태평양", "North Pacific"),
    ("sst.region.iod_west", "인도양 서 (IOD 서극)", "Western Indian Ocean (IOD west pole)"),
    ("sst.region.iod_east", "인도양 동 (IOD 동극)", "Eastern Indian Ocean (IOD east pole)"),
    ("sst.region.bay_of_bengal", "벵골만", "Bay of Bengal"),
    ("sst.region.south_atlantic", "남대서양", "South Atlantic"),
    ("sst.region.mediterranean", "지중해", "Mediterranean"),
    ("sst.why.subpolar_atlantic", "그린란드 남쪽 한랭역. 대서양 자오선 역전 순환(AMOC) 약화의 지표로 읽힙니다. 약해지면 유럽 강수와 겨울 한파 패턴이 바뀌어 EU 밀·유채에 영향합니다.", "Cold pool south of Greenland. Read as a marker of AMOC weakening; if it softens, European rainfall and winter cold patterns shift — affecting EU wheat and oilseed rape."),
    ("sst.why.gulf_stream", "AMOC 의 표층 구간. 열을 북쪽으로 실어 나르는 쪽이라, 아북극 한랭역과 함께 봐야 순환 전체의 상태가 읽힙니다.", "Surface limb of the AMOC. Carries heat northward — read with the subpolar cold pool to see the circulation as a whole."),
    ("sst.why.nino34", "ENSO 를 정의하는 해역. 엘니뇨는 인도네시아·호주 가뭄과 아르헨티나 다우로, 라니냐는 그 반대로 나타납니다.", "The basin that defines ENSO. El Niño tends toward Indonesia/Australia drought and Argentina wetness; La Niña the reverse."),
    ("sst.why.west_pacific", "지구에서 가장 따뜻한 해역. 아시아 몬순의 에너지원이며 Niño 3.4 와 반대 위상으로 움직이는 경향이 있습니다.", "Earth’s warmest ocean region. Energy source for the Asian monsoon; often moves in opposite phase to Niño 3.4."),
    ("sst.why.north_pacific", "북미 서해안 기압계와 미 중서부 겨울 기후에 영향합니다.", "Influences the North American west-coast pressure pattern and US Midwest winter climate."),
    ("sst.why.iod_west", "IOD 양의 위상에서 따뜻해지는 쪽. 동아프리카 다우와 호주 가뭄이 동반됩니다.", "Warms in a positive IOD. Often pairs with East Africa wetness and Australia drought."),
    ("sst.why.iod_east", "IOD 의 반대쪽 극. 서극과의 온도차가 곧 IOD 지수입니다.", "Opposite IOD pole. The temperature difference vs the west pole is the IOD index."),
    ("sst.why.bay_of_bengal", "인도 몬순의 수분 공급원. 수온이 높으면 몬순 강수가 늘지만 사이클론 강도도 함께 올라갑니다.", "Moisture source for the Indian monsoon. Warmer water boosts monsoon rain but also cyclone intensity."),
    ("sst.why.south_atlantic", "브라질 남부·아르헨티나 강수에 관여합니다.", "Linked to rainfall over southern Brazil and Argentina."),
    ("sst.why.mediterranean", "남유럽·북아프리카 강수의 수분 공급원. 수온이 높으면 겨울 폭우와 여름 가뭄이 함께 강해집니다. MENA 밀 산지에 직결됩니다.", "Moisture source for southern Europe and North Africa rainfall. Warm anomalies strengthen winter downpours and summer drought together — directly relevant to MENA wheat producing regions."),
    ("sst.affect.eu_wheat", "EU 밀", "EU wheat"),
    ("sst.affect.eu_rapeseed", "유럽 유채", "European oilseed rape"),
    ("sst.affect.n_atl_fishery", "북대서양 어장", "North Atlantic fisheries"),
    ("sst.affect.atl_hurricane", "대서양 허리케인", "Atlantic hurricanes"),
    ("sst.affect.us_east_climate", "미 동부 기후", "US East Coast climate"),
    ("sst.affect.se_asia_rice", "동남아 쌀", "Southeast Asia rice"),
    ("sst.affect.idn_palm", "인니 팜유", "Indonesia palm oil"),
    ("sst.affect.idn_palm_rubber", "인니 팜유·고무", "Indonesia palm oil · rubber"),
    ("sst.affect.au_wheat", "호주 밀", "Australia wheat"),
    ("sst.affect.us_winter_wheat", "미국 겨울밀", "US winter wheat"),
    ("sst.affect.ca_canola", "캐나다 캐놀라", "Canada canola"),
    ("sst.affect.e_africa_coffee", "동아프리카 커피", "East Africa coffee"),
    ("sst.affect.in_rice_wheat", "인도 쌀·밀", "India rice · wheat"),
    ("sst.affect.bd_rice", "방글라데시 쌀", "Bangladesh rice"),
    ("sst.affect.br_soy_coffee", "브라질 대두·커피", "Brazil soy · coffee"),
    ("sst.affect.br_coffee", "브라질 커피", "Brazil coffee"),
    ("sst.affect.ar_soy_corn", "아르헨 대두·옥수수", "Argentina soy · corn"),
    ("sst.affect.ar_pampas", "아르헨 팜파스", "Argentina Pampas"),
    ("sst.affect.s_eu_olive_durum", "남유럽 올리브·듀럼밀", "Southern Europe olive · durum"),
    ("sst.affect.mena_wheat", "모로코·알제리 밀", "Morocco · Algeria wheat"),
    # --- remaining app / panel chrome ---
    ("panel.ref_not_forecast", "정부·기관 전망 + 조사 메모 (예측 아님)", "Government/agency outlooks + research notes (not a forecast)"),
    ("panel.no_yield_forecast_limit", "데이터 한계로 단수 예측을 제공하지 않습니다.", "No yield (per-area) forecast due to data limits."),
    ("panel.no_forecast_short", "예측없음", "No forecast"),
    ("panel.no_wx_summary", "기상효과 요약 없음", "No weather-effect summary"),
    ("panel.no_summary", "요약 없음", "No summary"),
    ("panel.source_nasa_power", "출처: NASA POWER", "Source: NASA POWER"),
    ("panel.skill_drop_vs_trend", "추세 대비 오차 {0}% 감소", "Error vs trend reduced {0}%"),
    ("panel.low_conf_reason", "신뢰도 낮음 (검증 미통과·표본 부족 가능)", "Low confidence (may fail validation · thin sample)"),
    ("panel.no_skill_meta", "스킬 메타 없음", "No skill metadata"),
    ("panel.method_docs_hint", "논문·방법론은 해당국 yield_model 문서 / DATA_LAYOUT 참고", "See that country’s yield_model docs / DATA_LAYOUT for papers and methods"),
    ("panel.yield_per_area", "단수", "Yield (per-area)"),
    ("panel.region_wx_summary", "지역 기상효과 요약", "Regional weather-effect summary"),
    ("panel.producing_wx_effect", "산지 기상효과", "Producing-region weather effect"),
    ("panel.heat_drought_stress", "고온·건조 스트레스", "Heat · drought stress"),
    ("panel.caution", "주의", "Caution"),
    ("panel.crop_wx_effect", "작황 기상효과", "Crop-conditions weather effect"),
    ("panel.crops_regions_count", "{0}개 · {1}개", "{0} · {1}"),
    ("panel.target_crops_regions", "대상 작물 / 산지", "Crops / producing regions"),
    ("panel.forecast_or_wx", "예측/기상효과", "Forecast / weather effect"),
    ("panel.wx_vs_trend_avg", "기상효과(추세 대비) 평균 · 실적 평균 {0} {1}", "Weather effect (vs trend) avg · actual avg {0} {1}"),
    ("panel.news", "뉴스", "News"),
    ("wx.drought", "가뭄", "Drought"),
    ("wx.flood", "홍수", "Flood"),
    ("placeholder.commodities_coal", "원자재 > 석탄", "Commodities › Coal"),
    # --- data.js commodity / sample labels ---
    ("data.crop.soy_bean", "대두(콩)", "Soybeans"),
    ("data.crop.milled_rice", "백미", "Milled rice"),
    ("data.commodity.coal", "석탄", "Coal"),
    ("data.crop.corn_en", "옥수수 (corn)", "Corn"),
    ("data.crop.raw_sugar", "원당", "Raw sugar"),
    ("data.crop.green_coffee", "원두", "Green coffee"),
    ("data.fx.krw_usd_close", "원/달러 환율(종가)", "KRW/USD (close)"),
    ("data.bok_policy_rate", "한국은행 기준금리", "Bank of Korea policy rate"),
    ("geo.indonesia", "인도네시아", "Indonesia"),
    ("geo.australia", "호주", "Australia"),
    ("geo.saudi", "사우디아라비아", "Saudi Arabia"),
    ("geo.us_qatar", "미국 / 카타르", "United States / Qatar"),
    ("geo.switzerland", "스위스", "Switzerland"),
    ("geo.mx_pe", "멕시코 / 페루", "Mexico / Peru"),
    ("geo.chile", "칠레", "Chile"),
    ("geo.china_processed", "중국 (가공품)", "China (processed)"),
    ("geo.russia", "러시아", "Russia"),
    ("geo.usa", "미국", "United States"),
    ("geo.brazil", "브라질", "Brazil"),
    ("geo.br_et", "브라질 / 에티오피아", "Brazil / Ethiopia"),
    ("news.oil_iran_risk", "[리스크 경보] 이란 타격 여파로 사우디 주요 원유 생산 시설 가동 중단 우려 확산", "[Risk alert] Iran-strike fallout raises concern over Saudi crude production outages"),
    ("news.brent_85", "중동 지정학적 리스크 고조... 브렌트유(Brent) 배럴당 85달러 돌파", "Middle East geopolitical risk rises… Brent breaks $85/bbl"),
    ("common.hours_ago_2", "2시간 전", "2 hours ago"),
    ("climate.nina_watch_rain", "라니냐 주의: 강우 지연 및 불규칙", "La Niña watch: delayed and irregular rainfall"),
    ("climate.nina_hit_drought", "라니냐 직격타: 극심한 가뭄", "La Niña direct hit: severe drought"),
    ("climate.nina_dryish", "라니냐 영향: 예년 대비 다소 건조", "La Niña influence: somewhat drier than normal"),
    ("climate.nina_soil_deplete", "라니냐 기조: 토양 수분 고갈 (가뭄)", "La Niña setup: soil-moisture depletion (drought)"),
    ("climate.nina_wet_good", "라니냐 호조: 강수량 풍부 (수확량 긍정적)", "Favorable La Niña: abundant rain (yield-positive)"),
    ("data.crop.soy_en", "대두 (Soybeans)", "Soybeans"),
    ("data.crop.corn_safrinha_en", "옥수수 (Corn - Safrinha)", "Corn (safrinha)"),
    ("data.crop.cotton_en", "목화 (Cotton)", "Cotton"),
    ("data.crop.corn_en2", "옥수수 (Corn)", "Corn"),
    ("data.crop.palm_oil_en", "팜유 (Palm Oil)", "Palm oil"),
    ("data.crop.coffee_en", "커피 (Coffee)", "Coffee"),
    ("data.crop.rubber_en", "천연고무 (Rubber)", "Natural rubber"),
]


def main() -> None:
    ko = json.loads(KO_PATH.read_text(encoding="utf-8"))
    en = json.loads(EN_PATH.read_text(encoding="utf-8"))
    ko_meta = {k: ko.pop(k) for k in list(ko) if str(k).startswith("__")}
    en_meta = {k: en.pop(k) for k in list(en) if str(k).startswith("__")}

    keys = [k for k, _, _ in PAIRS]
    assert len(keys) == len(set(keys)), "duplicate keys"
    added = 0
    skipped = []
    for k, ko_v, en_v in PAIRS:
        if k in ko:
            skipped.append(k)
            continue
        ko[k] = ko_v
        en[k] = en_v
        added += 1

    # Map export measures that may still be missing from incomplete list — load full file
    ec_path = Path("/tmp/export_controls_v1.json")
    if ec_path.is_file():
        ec = json.loads(ec_path.read_text(encoding="utf-8"))
        # ensure every measure_ko has a key; create slug from country+first commodity
        for c in ec.get("controls", []):
            measure = c.get("measure_ko")
            if not measure:
                continue
            # if already present as a value, skip
            if measure in ko.values():
                continue
            slug = f"{c.get('iso','xx').lower()}_{(c.get('commodities') or ['x'])[0]}"
            key = f"export.measure.{slug}"
            if key in ko:
                key = f"export.measure.{slug}_{c.get('since','').replace('-', '')}"
            # leave EN as TODO-quality only if we somehow missed — shouldn't happen for known list
            print("WARN unmapped measure", measure)

    ko_meta["__phase__"] = "1+2+gaps"
    en_meta["__phase__"] = "1+2+gaps"
    en_meta["__notes__"] = (
        "UI locale pack for Claude t()+lang toggle. Keys must not be renamed after wiring. "
        "export.* / sst.* mirror display strings from data JSON *_ko fields — data files still need schema _en later (Phase 3). "
        "Sign rule: weather-effect placeholders have no +/-; the app formats the signed number into {0}."
    )

    def dump(path: Path, data: dict, meta: dict) -> None:
        ordered = dict(sorted(data.items()))
        ordered.update(meta)
        path.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    dump(KO_PATH, ko, ko_meta)
    dump(EN_PATH, en, en_meta)
    print(f"added {added}, skipped existing {len(skipped)}")
    print(f"total {sum(1 for k in ko if not str(k).startswith('__'))}")


if __name__ == "__main__":
    main()
