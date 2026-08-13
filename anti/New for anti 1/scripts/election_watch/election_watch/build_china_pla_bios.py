"""Build china_pla_bios.json from CMPR text — no LLM API. Unknown → 불명, N/A → 없음 where applicable."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw" / "china"
OUT = ROOT / "config" / "extracted"
CFG = ROOT / "config"
OUT.mkdir(parents=True, exist_ok=True)

불명 = "불명"
없음 = "없음"


def parse_theater_blocks(text: str) -> List[Dict[str, Any]]:
    """Parse 'X Theater Command Leadership' blocks from CMPR."""
    out = []
    # Split by theater leadership headers
    parts = re.split(
        r"(Eastern|Southern|Western|Central|Northern)\s+Theater Command Leadership",
        text,
    )
    # parts: [pre, name1, body1, name2, body2, ...]
    theater_ko = {
        "Eastern": "동부",
        "Southern": "남부",
        "Western": "서부",
        "Central": "중부",
        "Northern": "북부",
    }
    role_map = {
        "Commander": "사령원",
        "Political Commissar": "정치위원",
        "Chief of Staff": "참모장",
    }
    for i in range(1, len(parts), 2):
        theater_en = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        # stop at next major section if present
        body = re.split(r"\n[A-Z][a-z]+ Theater Command\n", body)[0]
        # entries: Role– Rank Name [hanzi]
        for m in re.finditer(
            r"(Commander|Political Commissar|Chief of Staff)[–\-]\s*"
            r"(General|Admiral|Lt\.?\s*General|Lt Gen|Vice Admiral|Major General)?\s*"
            r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})\s*"
            r"(?:\[([^\]]+)\])?",
            body,
        ):
            role_en, rank, name_en, name_zh = m.groups()
            # slice from this match to next role
            start = m.end()
            nxt = re.search(
                r"(Commander|Political Commissar|Chief of Staff)[–\-]",
                body[start:],
            )
            chunk = body[start : start + nxt.start()] if nxt else body[start : start + 800]
            birth = re.search(r"Birthplace:\s*([^\n]+)", chunk)
            dob = re.search(r"DOB:\s*([^\n]+)", chunk)
            prev = re.search(r"Previous [Pp]osition[;:]?\s*([^\n]+)", chunk)
            bio = re.search(r"Bio:\s*(.+?)(?=\nPolitical|\nChief|\n[A-Z][a-z]+ Theater|\Z)", chunk, re.S)
            birthplace = birth.group(1).strip() if birth else 불명
            shandong = "예" if birthplace and "Shandong" in birthplace else ("아니오" if birthplace != 불명 else 불명)
            xi = 불명
            if bio:
                b = bio.group(1)
                if re.search(r"ties to President Xi|Xi Jinping", b, re.I):
                    xi = "CMPR: possible ties to President Xi Jinping 언급"
                elif "Air Force" in b and theater_en == "Central":
                    xi = 불명
            rank = (rank or "").strip() or 불명
            out.append(
                {
                    "이름": name_zh or 불명,
                    "이름_영문": name_en,
                    "직책": f"{theater_ko.get(theater_en, theater_en)}전구 {role_map.get(role_en, role_en)}",
                    "직책_영문": f"{theater_en} Theater Command {role_en}",
                    "계급": rank,
                    "상태": "활성 (Active)",
                    "고향": birthplace,
                    "산둥성_출신": shandong,
                    "생년": dob.group(1).strip() if dob else 불명,
                    "이전직": prev.group(1).strip() if prev else 불명,
                    "실전경험": 불명,
                    "파벌_시진핑": xi,
                    "파벌_펑리위안": 불명,
                    "파벌_장유샤": 불명,
                    "숙청_조사": 없음,
                    "출처": ["DoD CMPR 2025", "as_of 2024-12-31"],
                }
            )
    return out


def cmc_entries() -> List[Dict[str, Any]]:
    """CMC / defense minister cards from curated CMPR notes (not full theater parse)."""
    return [
        {
            "이름": "习近平",
            "이름_영문": "Xi Jinping",
            "직책": "중앙군사위원회 주석",
            "직책_영문": "CMC Chair",
            "계급": 없음,
            "상태": "활성 (Active)",
            "고향": 불명,
            "산둥성_출신": 불명,
            "생년": 불명,
            "이전직": 없음,
            "실전경험": 불명,
            "파벌_시진핑": "본인",
            "파벌_펑리위안": "배우자 관계",
            "파벌_장유샤": 불명,
            "숙청_조사": 없음,
            "출처": ["DoD CMPR 2025"],
        },
        {
            "이름": "张又侠",
            "이름_영문": "Zhang Youxia",
            "직책": "중앙군사위원회 부주석",
            "직책_영문": "CMC Vice Chairman",
            "계급": "General",
            "상태": "활성 (Active)",
            "고향": 불명,
            "산둥성_출신": 불명,
            "생년": 불명,
            "이전직": 불명,
            "실전경험": 불명,
            "파벌_시진핑": 불명,
            "파벌_펑리위안": 불명,
            "파벌_장유샤": "본인",
            "숙청_조사": 없음,
            "출처": ["DoD CMPR 2025 — He Weidong 이슈 후 oversight 강화 서술"],
        },
        {
            "이름": "何卫东",
            "이름_영문": "He Weidong",
            "직책": "중앙군사위원회 부주석",
            "직책_영문": "CMC Vice Chairman",
            "계급": "General",
            "상태": "조사·구금 보도 (Under investigation / reportedly detained)",
            "고향": 불명,
            "산둥성_출신": 불명,
            "생년": 불명,
            "이전직": 불명,
            "실전경험": 불명,
            "파벌_시진핑": 불명,
            "파벌_펑리위안": 불명,
            "파벌_장유샤": 불명,
            "숙청_조사": "2025 초 부재 → 2025-03 구금 보도 (CMPR)",
            "출처": ["DoD CMPR 2025"],
        },
        {
            "이름": "苗华",
            "이름_영문": "Miao Hua",
            "직책": "중앙군사위원회 정치공작부 주임",
            "직책_영문": "CMC Political Work Department Director",
            "계급": "Admiral",
            "상태": "조사·직무정지 (Under investigation / suspended)",
            "고향": 불명,
            "산둥성_출신": 불명,
            "생년": 불명,
            "이전직": 불명,
            "실전경험": 불명,
            "파벌_시진핑": 불명,
            "파벌_펑리위안": 불명,
            "파벌_장유샤": 불명,
            "숙청_조사": "2024-11 부패 조사·직무정지 (CMPR)",
            "출처": ["DoD CMPR 2025"],
        },
        {
            "이름": "董军",
            "이름_영문": "Dong Jun",
            "직책": "국방부장 (CMC 미소속)",
            "직책_영문": "Minister of National Defense (not seated on CMC)",
            "계급": "Admiral",
            "상태": "활성 (Active) — CMC 미소속",
            "고향": 불명,
            "산둥성_출신": 불명,
            "생년": 불명,
            "이전직": 불명,
            "실전경험": 불명,
            "파벌_시진핑": 불명,
            "파벌_펑리위안": 불명,
            "파벌_장유샤": 불명,
            "숙청_조사": 없음,
            "출처": ["DoD CMPR 2025 — 2023-12 임명, CMC 미입"],
        },
        {
            "이름": "李尚福",
            "이름_영문": "Li Shangfu",
            "직책": "전 국방부장·전 CMC",
            "직책_영문": "Former Minister of National Defense / CMC",
            "계급": "General",
            "상태": "해임·숙청 (Removed)",
            "고향": 불명,
            "산둥성_출신": 불명,
            "생년": 불명,
            "이전직": "CMC Equipment Development Dept",
            "실전경험": 불명,
            "파벌_시진핑": 불명,
            "파벌_펑리위안": 불명,
            "파벌_장유샤": 불명,
            "숙청_조사": "2023-10 해임 (조달 부패 추정, CMPR)",
            "출처": ["DoD CMPR 2025"],
        },
    ]


def main() -> int:
    text_path = RAW / "CMPR_2025.txt"
    text = text_path.read_text(encoding="utf-8", errors="ignore") if text_path.exists() else ""
    theaters = parse_theater_blocks(text) if text else []
    # Enrich Lin Xiangyang Xi note if bio parse missed
    for row in theaters:
        if row["이름_영문"] == "Lin Xiangyang" and row["파벌_시진핑"] == 불명:
            if "possible ties to President Xi" in text or "ties to President Xi Jinping" in text:
                row["파벌_시진핑"] = "CMPR: possible ties to President Xi Jinping 언급"

    bios = cmc_entries() + theaters
    doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "rule_based_cmpr_parse_no_llm",
        "null_policy": {"없음": "해당 없음", "불명": "출처에 없음/미확정"},
        "source_primary": {
            "id": "dod_cmpr_2025",
            "press_index": "https://news.usni.org/2025/12/24/pentagon-annual-report-on-chinese-military-and-security-developments-2",
            "local_txt": "raw/china/CMPR_2025.txt",
            "as_of_theater_leadership": "2024-12-31",
        },
        "implementation_plan_note": (
            "Anti LLM/API 파이프는 문헌 범위 밖. Cursor v1은 CMPR 규칙추출. "
            "싱크탱크 보강 JSON은 Anti 문헌 산출물을 Cursor가 병합."
        ),
        "count": len(bios),
        "산둥성_출신_확인": [b for b in bios if b.get("산둥성_출신") == "예"],
        "figures": bios,
    }
    # dual write: extracted + literature-friendly copy under config
    out1 = OUT / "china_pla_bios.json"
    out2 = CFG / "china_pla_bios.json"
    payload = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    out1.write_text(payload, encoding="utf-8")
    out2.write_text(payload, encoding="utf-8")
    print(
        json.dumps(
            {
                "wrote": [str(out1), str(out2)],
                "count": len(bios),
                "theater_rows": len(theaters),
                "shandong": [b["이름_영문"] for b in doc["산둥성_출신_확인"]],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
