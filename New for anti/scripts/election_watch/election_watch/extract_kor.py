"""Extract KOR National Assembly composition, head/PM floor lines, governance poll refresh.

Primary composition source: Wikipedia list of 22nd NA members (seat table as-of label).
NEC open data supersedes when a stable machine parser is wired.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import urllib.request
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw" / "kor"
OUT = ROOT / "config" / "extracted"
OUT.mkdir(parents=True, exist_ok=True)
UA = "election-watch/1.0 (+global-trade-dashboard research)"

WIKI_LIST = (
    "https://en.wikipedia.org/wiki/"
    "List_of_members_of_the_National_Assembly_(South_Korea),_2024%E2%80%932028"
)
WIKI_22 = "https://en.wikipedia.org/wiki/22nd_National_Assembly_of_South_Korea"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch(url: str, dest: Path, timeout: float = 40.0) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    curl = shutil.which("curl")
    if curl:
        r = subprocess.run(
            [curl, "-sL", "--max-time", str(int(timeout)), "-A", UA, "-o", str(dest), url],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0 and dest.exists() and dest.stat().st_size > 200:
            return True
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            dest.write_bytes(resp.read())
        return dest.exists() and dest.stat().st_size > 200
    except Exception:
        return False


def curated_assembly() -> Dict[str, Any]:
    """Seat matrix as of 2026-07-16 (Wikipedia composition table)."""
    parties = [
        {"abbr": "DPK", "name_en": "Democratic Party", "name_ko": "더불어민주당", "seats": 161, "floor_leader": "Han Byung-do"},
        {"abbr": "PPP", "name_en": "People Power", "name_ko": "국민의힘", "seats": 109, "floor_leader": "Jeong Jeom-sig"},
        {"abbr": "RKP", "name_en": "Rebuilding Korea", "name_ko": "조국혁신당", "seats": 12, "floor_leader": "Kim Joon-hyung"},
        {"abbr": "JP", "name_en": "Progressive Party", "name_ko": "진보당", "seats": 4, "floor_leader": "Yoon Jong-oh"},
        {"abbr": "NRP", "name_en": "New Reform", "name_ko": "개혁신당", "seats": 3, "floor_leader": "Cheon Ha-ram"},
        {"abbr": "BIP", "name_en": "Basic Income", "name_ko": "기본소득당", "seats": 1, "floor_leader": "Yong Hye-in"},
        {"abbr": "SDP", "name_en": "Social Democratic", "name_ko": "사회민주당", "seats": 1, "floor_leader": "Han Chang-min"},
        {"abbr": "IND", "name_en": "Independent", "name_ko": "무소속", "seats": 8, "floor_leader": "없음"},
        {"abbr": "VAC", "name_en": "Vacant", "name_ko": "결원", "seats": 1, "floor_leader": "없음"},
    ]
    by_abbr = {p["abbr"]: p["seats"] for p in parties}
    seats_sum = sum(by_abbr.values())
    return {
        "as_of": now_iso(),
        "composition_date": "2026-07-16",
        "source": {
            "id": "wiki_22nd_na_members_2024_2028",
            "url": WIKI_LIST,
            "grade": "aggregator_wikipedia",
            "note": "Current seats table as of 16 July 2026. Gangneung (Kweon Seong-dong) vacated 16 July; replacement TBD counted as Vacant in this pass.",
            "official_portal": "https://www.assembly.go.kr/",
            "nec": "https://www.nec.go.kr/",
            "also": WIKI_22,
        },
        "summary": {
            "chamber": "national_assembly",
            "assembly_number": 22,
            "term": "2024-05-30 .. 2028-05-29",
            "seats_total_nominal": 300,
            "seats_sum_parsed": seats_sum,
            "by_party_abbr": by_abbr,
            "ruling_bloc_note": "DPK majority 161; pan-progressive allies RKP+JP+SDP+BIP separate negotiation groups under 20 seats",
            "parse_ok": seats_sum == 300,
        },
        "parties": parties,
        "floor_leadership": [
            {
                "office": "president",
                "name": "Lee Jae Myung",
                "name_ko": "이재명",
                "party_abbr": "DPK",
                "since": "2025-06-04",
                "source": "https://en.wikipedia.org/wiki/Lee_Jae-myung",
            },
            {
                "office": "prime_minister",
                "name": "Han Seong-sook",
                "name_ko": "한성숙",
                "party_abbr": "IND",
                "since": "2026-07-01",
                "confidence": "high",
                "note": "제50대 국무총리; former Naver CEO / MSME minister under Lee government.",
                "source": "https://www.opm.go.kr/opm/prime/profile.do",
            },
            {
                "office": "speaker",
                "name": "Cho Jeong-sik",
                "name_ko": "조정식",
                "party_abbr": "IND",
                "since": "2026-06-05",
                "note": "Speaker sits independent by statute; formerly DPK.",
                "source": "https://www.koreatimes.co.kr/southkorea/politics/20260605/six-term-lawmaker-cho-jeong-sik-elected-new-natl-assembly-speaker",
            },
            {
                "office": "deputy_speaker",
                "name": "Nam In-soon",
                "name_ko": "남인순",
                "party_abbr": "DPK",
                "since": "2026-06-05",
            },
            {
                "office": "deputy_speaker",
                "name": "Park Deok-heum",
                "name_ko": "박덕흠",
                "party_abbr": "PPP",
                "since": "2026-06-05",
            },
            {
                "office": "floor_leader_ruling",
                "name": "Han Byung-do",
                "name_ko": "한병도",
                "party_abbr": "DPK",
                "composition_date": "2026-07-16",
            },
            {
                "office": "floor_leader_opposition",
                "name": "Jeong Jeom-sig",
                "name_ko": "정점식",
                "party_abbr": "PPP",
                "composition_date": "2026-07-16",
            },
        ],
        "null_policy": {"없음": "해당 없음", "불명": "출처 미확정"},
    }


def try_parse_wiki_seats(html: str) -> Optional[Dict[str, int]]:
    """Best-effort parse of composition table; return None if incomplete."""
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    text = re.sub(r"\s+", " ", text)
    # Prefer explicit "as of" current totals if pattern appears
    found: Dict[str, int] = {}
    patterns = [
        (r"Democratic\s+\d+\s+—?\s*N/?a\s+\d+\s+[-–]\s+(\d+)", "DPK"),
        (r"People Power\s+\d+\s+—?\s*N/?a\s+\d+\s+\d+\s+(\d+)", "PPP"),
        (r"Rebuilding Korea\s+—?\s*N/?a\s+\d+\s+\d+\s+—?\s+(\d+)", "RKP"),
    ]
    for pat, abbr in patterns:
        m = re.search(pat, text, re.I)
        if m:
            found[abbr] = int(m.group(1))
    if found.get("DPK") and found.get("PPP"):
        return found
    return None


def extract_kor_assembly(*, refresh: bool = True) -> Dict[str, Any]:
    doc = curated_assembly()
    raw_path = RAW / "wiki_list_members.html"
    if refresh:
        ok = fetch(WIKI_LIST, raw_path)
        if ok:
            try:
                html = raw_path.read_text(encoding="utf-8", errors="replace")
                parsed = try_parse_wiki_seats(html)
                if parsed:
                    doc["source"]["parse_attempt"] = "partial_regex"
                    doc["source"]["parsed_partial"] = parsed
            except Exception as e:
                doc["source"]["parse_error"] = str(e)[:200]
        else:
            doc["source"]["fetch"] = "failed_using_curated_offline"
    else:
        doc["source"]["fetch"] = "skipped"
    return doc


def local_election_snapshot() -> Dict[str, Any]:
    """9th nationwide local elections 2026-06-03 — metro/provincial heads only (light)."""
    return {
        "as_of": now_iso(),
        "source": {
            "id": "nec_local_2026_via_yonhap",
            "urls": [
                "https://en.yna.co.kr/view/AEN20260602008360315",
                "https://www.koreaherald.com/article/10763117",
            ],
            "grade": "media_cross_check",
            "note": "Official NEC open data supersedes city-by-city when wired.",
        },
        "summary": {
            "election_id": "kor-2026-local",
            "date": "2026-06-03",
            "label_ko": "제9회 전국동시지방선거",
            "metro_provincial_heads_total": 16,
            "by_party_abbr": {"DPK": 12, "PPP": 4},
            "note": "DPK 12 including Busan/Incheon/Gyeonggi; PPP retained Seoul + Yeongnam core (Daegu, N/S Gyeongsang).",
        },
        "highlights": [
            {
                "office": "seoul_mayor",
                "name_en": "Oh Se-hoon",
                "name_ko": "오세훈",
                "party_abbr": "PPP",
                "result": "incumbent 5th term; ~48.94% vs Chong Won-o (DPK) ~48.34%",
            },
            {
                "office": "gyeonggi_governor",
                "name_en": "Choo Mi-ae",
                "name_ko": "추미애",
                "party_abbr": "DPK",
                "result": "55.04% vs Yang Hyang-ja (PPP) 39.37%; first woman elected provincial governor",
            },
            {
                "office": "busan_mayor",
                "name_en": "Jeon Jae-soo",
                "name_ko": "전재수",
                "party_abbr": "DPK",
                "result": "won traditional conservative stronghold",
            },
        ],
    }


def merge_governance_polls() -> Dict[str, Any]:
    path = OUT / "governance_polls.json"
    existing: Dict[str, Any] = {}
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
    series = [s for s in (existing.get("series") or []) if s.get("iso3") != "KOR"]
    series.extend(
        [
            {
                "iso3": "KOR",
                "kind": "presidential_job_approval",
                "subject": "Lee Jae Myung",
                "pollster": "Gallup Korea",
                "approve_pct": 51,
                "disapprove_pct": 38,
                "field_date": "2026-07-21..23",
                "field_note": (
                    "Gallup 4th week of July 2026: +51 / −38 (n≈1003). "
                    "Realmeter early Aug ~45.9% positive / 50.5% negative (different house) — track both; "
                    "primary series = Gallup Korea."
                ),
                "sources": [
                    {
                        "url": "https://www.mk.co.kr/en/politics/12106417",
                        "label": "MK: Gallup Korea 51% (21–23 Jul 2026)",
                    },
                    {
                        "url": "https://www.koreatimes.co.kr/southkorea/politics/20260803/lees-approval-rating-hits-new-low-as-housing-stock-market-turmoil-overshadow-diplomatic-trip",
                        "label": "Korea Times: Realmeter 45.9% (early Aug, secondary house)",
                    },
                ],
                "confidence": "high",
                "refresh": "weekly_gallup_korea",
            },
            {
                "iso3": "KOR",
                "kind": "presidential_job_approval_secondary",
                "subject": "Lee Jae Myung",
                "pollster": "Realmeter",
                "approve_pct": 45.9,
                "disapprove_pct": 50.5,
                "field_date": "2026-08-early",
                "field_note": "ARSS weekly series; first sub-50 sustained streak of term (housing/markets).",
                "sources": [
                    {
                        "url": "https://www.koreatimes.co.kr/southkorea/politics/20260803/lees-approval-rating-hits-new-low-as-housing-stock-market-turmoil-overshadow-diplomatic-trip",
                        "label": "Korea Times / Realmeter",
                    }
                ],
                "confidence": "medium",
                "refresh": "weekly_realmeter",
            },
        ]
    )
    return {
        "as_of": now_iso(),
        "policy": existing.get("policy")
        or {
            "admit": [
                "presidential_job_approval",
                "cabinet_approval",
                "pm_approval",
                "pm_preferred",
            ],
            "reject": ["national_horserace_headline"],
        },
        "series": series,
    }


def party_leadership_snapshot() -> Dict[str, Any]:
    """Major-party conventions (presidential system: ruling + main opposition).

    Product rule: party_leadership is always-include for KOR (not USA).
    Horserace *poll averages* still rejected; official race metadata + interim tour counts OK.
    """
    return {
        "as_of": now_iso(),
        "as_of_date": "2026-08-08",
        "policy": {
            "track_parties": ["dpk", "ppp"],
            "note_ko": "대통령제: 여당+제1야당 전당대회·당대표. 경마형 여론 평균은 배제, 선관위/당 발표 일정·후보·규칙·중간 순회 집계는 수집.",
        },
        "source": {
            "id": "dpk_ppp_convention_official_and_media_cross",
            "grade": "official_party_plus_media_cross",
            "urls": [
                "https://www.yna.co.kr/view/AKR20260723181951001",
                "https://www.inews24.com/view/1993155",
                "https://www.peoplepowerparty.kr/news/comment_view/BBSDD0001/108751?page=1",
                "https://www.peoplepowerparty.kr/news/comment_view_all/108719?gubun_list=all&page=364",
            ],
        },
        "parties": [
            {
                "party_id": "dpk",
                "party_abbr": "DPK",
                "name_ko": "더불어민주당",
                "role": "ruling",
                "convention": {
                    "id": "kor-2026-dpk-convention",
                    "label_ko": "더불어민주당 전당대회 (당대표·최고위원)",
                    "final_date": "2026-08-17",
                    "venue": "대전컨벤션센터 (DCC)",
                    "status": "ongoing",
                    "prelim_cut": {
                        "date": "2026-07-23",
                        "advanced": [
                            {"name_ko": "김민석", "name_en": "Kim Min-seok"},
                            {"name_ko": "정청래", "name_en": "Chung Chung-rae"},
                            {"name_ko": "송영길", "name_en": "Song Young-gil"},
                        ],
                        "dropped_note": "고민정·김보미 등 예비경선 탈락 (득표수 비공개)",
                    },
                    "rules": {
                        "member_vote_weight_pct": 70,
                        "public_poll_weight_pct": 30,
                        "one_member_one_vote": True,
                        "preference_vote": True,
                        "regional_weight_note": "대구·경북·경남 대의원·권리당원 5% 가중 (당 규정)",
                        "final_combines": "대의원+권리당원 + 국민여론조사; 순회 구간은 권리당원 1순위 공개 위주",
                    },
                    "tour_schedule": [
                        {"region": "충청(충남·충북·대전·세종)", "result_date": "2026-08-01", "status": "completed"},
                        {"region": "부울경(부산·울산·경남)", "result_date": "2026-08-02", "status": "completed"},
                        {"region": "제주·인천", "result_date": "2026-08-08", "status": "completed"},
                        {"region": "강원·대구·경북", "result_date": "2026-08-09", "status": "scheduled"},
                        {"region": "전북·전남광주", "result_date": "2026-08-15", "status": "scheduled"},
                        {"region": "경기·서울", "result_date": "2026-08-16", "status": "scheduled"},
                        {"region": "최종 전당대회", "result_date": "2026-08-17", "status": "scheduled"},
                    ],
                    "candidates_chair": [
                        {
                            "name_ko": "김민석",
                            "name_en": "Kim Min-seok",
                            "faction_note": "친명 계열로 보도",
                            "status": "in_final",
                        },
                        {
                            "name_ko": "정청래",
                            "name_en": "Chung Chung-rae",
                            "faction_note": "직전 대표; 친청 프레임 보도",
                            "status": "in_final",
                        },
                        {
                            "name_ko": "송영길",
                            "name_en": "Song Young-gil",
                            "faction_note": "친명 계열로 보도",
                            "status": "in_final",
                        },
                    ],
                    "interim_running_total": {
                        "as_of": "2026-08-08",
                        "scope": "권리당원 순회 누적 (경남 가중 미반영 보도 수치) — 최종 아님",
                        "share_first_preference_pct": {
                            "김민석": 45.42,
                            "정청래": 44.56,
                            "송영길": 10.02,
                        },
                        "votes_note": "보도에 따라 송 후보 세 자리는 ~10%대; 합 100 반올림.",
                        "source": "https://www.inews24.com/view/1993155",
                        "confidence": "medium",
                    },
                    "supreme_council": {
                        "note": "최고위원 본선 8인 (예비 통과). 최종 5명 8/17 확정.",
                        "finalists_sample": [
                            "박선원",
                            "이성윤",
                            "김용",
                            "한민수",
                            "서미화",
                            "최민희",
                            "김영호",
                            "임미애",
                        ],
                        "status": "ongoing",
                    },
                    "winner": "불명",
                    "winner_note": "2026-08-17 전당대회 발표 전",
                },
            },
            {
                "party_id": "ppp",
                "party_abbr": "PPP",
                "name_ko": "국민의힘",
                "role": "main_opposition",
                "convention": {
                    "id": "kor-2025-ppp-convention",
                    "label_ko": "국민의힘 제6차 전당대회 (현 지도부 출처)",
                    "first_round_date": "2025-08-22",
                    "final_date": "2025-08-26",
                    "runoff_date": "2025-08-26",
                    "status": "completed",
                    "year_on_2026_board": "prior_year_result_for_incumbent_leader",
                    "rules": {
                        "member_vote_weight_pct": 80,
                        "public_poll_weight_pct": 20,
                    },
                    "candidates_chair_final": [
                        {"name_ko": "장동혁", "name_en": "Jang Dong-hyuk", "status": "won"},
                        {"name_ko": "김문수", "name_en": "Kim Moon-soo", "status": "lost_runoff"},
                    ],
                    "winner": {
                        "name_ko": "장동혁",
                        "name_en": "Jang Dong-hyuk",
                        "since": "2025-08",
                        "term_years": 2,
                    },
                    "supreme_council": {
                        "elected": ["신동욱", "김민수", "양향자", "김재원"],
                        "youth": "우재준",
                    },
                    "note_2026": "2026년 별도 정기 전당대회 일정 없음(현 대표 임기 중). 차기(제7차) 보도 기준 2027 — confirm when party announces.",
                },
            },
        ],
        "null_policy": {"없음": "해당 없음", "불명": "미확정"},
    }


def main() -> int:
    na = extract_kor_assembly(refresh=True)
    local = local_election_snapshot()
    party_lead = party_leadership_snapshot()
    polls = merge_governance_polls()

    (OUT / "kor_assembly.json").write_text(
        json.dumps(na, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "kor_local_2026.json").write_text(
        json.dumps(local, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "kor_party_leadership.json").write_text(
        json.dumps(party_lead, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "governance_polls.json").write_text(
        json.dumps(polls, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    summary_path = OUT / "summary.json"
    summary: Dict[str, Any] = {}
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["generated_at"] = now_iso()
    summary["kor"] = {
        "assembly_by_party_abbr": (na.get("summary") or {}).get("by_party_abbr"),
        "seats_sum": (na.get("summary") or {}).get("seats_sum_parsed"),
        "floor_leadership": na.get("floor_leadership"),
        "local_metro_by_party": (local.get("summary") or {}).get("by_party_abbr"),
        "party_leadership": {
            "dpk_status": "ongoing_final_2026-08-17",
            "ppp_leader": "장동혁",
            "as_of": party_lead.get("as_of_date"),
        },
    }
    summary["polls"] = {
        "series": [
            {
                "iso3": s["iso3"],
                "kind": s["kind"],
                "approve_pct": s.get("approve_pct"),
                "status": s.get("status"),
            }
            for s in polls["series"]
        ]
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "assembly_sum": na["summary"]["seats_sum_parsed"],
                "dpk": na["summary"]["by_party_abbr"].get("DPK"),
                "ppp": na["summary"]["by_party_abbr"].get("PPP"),
                "local_dpk_metro": local["summary"]["by_party_abbr"].get("DPK"),
                "dpk_convention": "2026-08-17 ongoing",
                "ppp_leader": "Jang Dong-hyuk",
                "poll_gallup": 51,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
