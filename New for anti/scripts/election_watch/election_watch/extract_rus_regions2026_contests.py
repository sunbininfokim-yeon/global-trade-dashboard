"""Build elections_contest_v1 for rus-2026-single-voting-day-regions.

Heads: Atlas Vyborov Table 1 (8 direct, 39 registered) + EN/RU Wikipedia.
Legislatures: 39-subject inventory (TASS / RU Wikipedia). Named lists not fully
extracted — districts stay scheduled, status of the event is partial.
Current heads: incumbent/acting holder of each of the 11 offices.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT.parents[1] / "public" / "data"
CONTESTS_DIR = PUBLIC / "elections_contests"

AS_OF = date.today().isoformat()
EVENT_ID = "rus-2026-single-voting-day-regions"

ATLAS = (
    "https://atlas.vyborov.org/en/articles/89/"
    "osobennosti-regionalnoj-konkurencii-2026-itogi-vydvizheniya-i-registracii-"
    "kandidatov-i-partijnyh-spiskov-na-regionalnyh-vyborah-20-sentyabrya-2026"
)
WIKI_EN = "https://en.wikipedia.org/wiki/2026_Russian_regional_elections"
WIKI_RU = (
    "https://ru.wikipedia.org/wiki/"
    "%D0%95%D0%B4%D0%B8%D0%BD%D1%8B%D0%B9_%D0%B4%D0%B5%D0%BD%D1%8C_%D0%B3%D0%BE%D0%BB%D0%BE%D1%81%D0%BE%D0%B2%D0%B0%D0%BD%D0%B8%D1%8F_20_%D1%81%D0%B5%D0%BD%D1%82%D1%8F%D0%B1%D1%80%D1%8F_2026_%D0%B3%D0%BE%D0%B4%D0%B0"
)
TASS_FACT = "https://tass.com/politics/2189299"
TASS_JUNE = "https://tass.com/politics/2146991"
VEDOMOSTI = "https://www.vedomosti.ru/politics/articles/2026/09/18/1229785-kogo-budut-vibirat-v-2026"
CIKRF = "http://www.cikrf.ru/"

PARTY_META: Dict[str, Dict[str, str]] = {
    "UR": {
        "name_ru": "Единая Россия",
        "name_ko": "통합러시아",
        "name_en": "United Russia",
        "leader_ko": "드미트리 메드베데프",
        "note_ko": "여당. 직선 주지사 8곳 중 7곳에서 현직·권한대행을 냄. 울리야놉스크는 현직이 공산당이라 후보를 내지 않았다.",
    },
    "CPRF": {
        "name_ru": "КПРФ",
        "name_ko": "러시아연방공산당",
        "name_en": "Communist Party of the Russian Federation",
        "leader_ko": "겐나디 주가노프",
        "note_ko": "직선 8곳 전원 후보지. 울리야놉스크 현직 루스키흐.",
    },
    "LDPR": {
        "name_ru": "ЛДПР",
        "name_ko": "자유민주당",
        "name_en": "Liberal Democratic Party of Russia",
        "leader_ko": "레오니드 슬루츠키",
        "note_ko": "직선 8곳 중 체첸을 뺀 7곳 후보지(체첸 수장은 3명만 등록).",
    },
    "SR": {
        "name_ru": "Справедливая Россия",
        "name_ko": "정의러시아",
        "name_en": "A Just Russia",
        "leader_ko": "세르게이 미로노프",
        "note_ko": "직선 8곳 전원 후보지.",
    },
    "NL": {
        "name_ru": "Новые люди",
        "name_ko": "새로운 사람들",
        "name_en": "New People",
        "leader_ko": "알렉세이 네차예프",
        "note_ko": "직선은 모르도바·투바·브랸스크·울리야놉스크. 주의회 명부는 체첸·축치에는 없음(Atlas).",
    },
    "Greens": {
        "name_ru": "Российская экологическая партия «Зелёные»",
        "name_ko": "녹색당",
        "name_en": "The Greens",
        "leader_ko": "콘스탄틴 아타얀",
        "note_ko": "직선은 모르도바 마세로프.",
    },
    "RPPSS": {
        "name_ru": "Российская партия пенсионеров за социальную справедливость",
        "name_ko": "연금생활자당",
        "name_en": "Russian Party of Pensioners for Social Justice",
        "leader_ko": "에릭 프라즈드니코프",
        "note_ko": "직선은 벨고로드·펜자·트베리.",
    },
    "CR": {
        "name_ru": "Коммунисты России",
        "name_ko": "러시아공산주의자들",
        "name_en": "Communists of Russia",
        "leader_ko": "세르게이 말린코비치",
        "note_ko": "직선은 트베리 말린코비치.",
    },
    "Rodina": {
        "name_ru": "Родина",
        "name_ko": "조국당",
        "name_en": "Rodina",
        "leader_ko": "알렉세이 주라블료프",
        "note_ko": "벨고로드 예스코프는 공천 다음날 사퇴, 투표용지에 없음. 주의회 명부는 일부 주만.",
    },
    "Yabloko": {
        "name_ru": "Яблоко",
        "name_ko": "야블로코",
        "name_en": "Yabloko",
        "leader_ko": "니콜라이 리바코프",
        "note_ko": "카렐리야·상트페테르부르크·레닌그라드주 주의회 명부는 등록 취소(Atlas).",
    },
    "PPD": {
        "name_ru": "Партия прямой демократии",
        "name_ko": "직접민주당",
        "name_en": "Party of Direct Democracy",
        "leader_ko": "타티야나 콜나우스",
        "note_ko": "주의회 명부는 유대인자치주만(Atlas).",
    },
}

# Atlas Table 1 registered candidates (39). Yeskov/Rodina withdrew, not listed.
GOV_DIRECT: List[Dict[str, Any]] = [
    {
        "id": "mordovia",
        "name_ko": "모르도바 수장",
        "name_ru": "Глава Республики Мордовия",
        "group_ko": "직선",
        "incumbent_party": "UR",
        "note_ko": "현직 즈두노프 재출마. Atlas 등록 6명. 영문 위키 표는 툴라예프(NL)가 빠져 있어 Atlas를 쓴다.",
        "candidates": [
            ("UR", "Zdunov, Artyom", True),
            ("CPRF", "Aleksandrov, Alexander", False),
            ("SR", "Geraskin, Timur", False),
            ("Greens", "Masserov, Dmitry", False),
            ("NL", "Tulayev, Vladislav", False),
            ("LDPR", "Tyurin, Yevgeny", False),
        ],
    },
    {
        "id": "tuva",
        "name_ko": "투바 수장",
        "name_ru": "Глава Республики Тыва",
        "group_ko": "직선",
        "incumbent_party": "UR",
        "note_ko": "현직 호발릭 재출마. Atlas·영문 위키 등록 5명.",
        "candidates": [
            ("UR", "Khovalyg, Vladislav", True),
            ("CPRF", "Kuular, Lodoy-Damba", False),
            ("SR", "Chanzan, Aziat", False),
            ("LDPR", "Chistyakov, Yegor", False),
            ("NL", "Irgit, Artysh", False),
        ],
    },
    {
        "id": "chechnya",
        "name_ko": "체첸 수장",
        "name_ru": "Глава Чеченской Республики",
        "group_ko": "직선",
        "incumbent_party": "UR",
        "note_ko": "현직 카디로프 재출마. Atlas 등록 3명(직선 중 최소).",
        "candidates": [
            ("UR", "Kadyrov, Ramzan", True),
            ("CPRF", "Nakayev, Khalid", False),
            ("SR", "Denilkhanov, Ismail", False),
        ],
    },
    {
        "id": "belgorod",
        "name_ko": "벨고로드 주지사",
        "name_ru": "Губернатор Белгородской области",
        "group_ko": "직선",
        "incumbent_party": "UR",
        "note_ko": "글라드코프 사퇴 후 권한대행 슈바예프 출마. 로디나 예스코프는 공천 다음날 사퇴라 투표용지에 없음.",
        "candidates": [
            ("UR", "Shuvaev, Alexander", True),
            ("CPRF", "Shevlyakov, Valery", False),
            ("SR", "Abelmazov, Vladimir", False),
            ("LDPR", "Dremov, Yevgeny", False),
            ("RPPSS", "Zotov, Artyom", False),
        ],
    },
    {
        "id": "bryansk",
        "name_ko": "브랸스크 주지사",
        "name_ru": "Губернатор Брянской области",
        "group_ko": "직선",
        "incumbent_party": "UR",
        "note_ko": "보고마즈 사퇴 후 권한대행 코발추크 출마. 조기선거.",
        "candidates": [
            ("UR", "Kovalchuk, Yegor", True),
            ("CPRF", "Arkhitsky, Andrey", False),
            ("NL", "Kazachkova, Alexandra", False),
            ("SR", "Timoshkov, Aleksey", False),
            ("LDPR", "Titov, Ruslan", False),
        ],
    },
    {
        "id": "penza",
        "name_ko": "펜자 주지사",
        "name_ru": "Губернатор Пензенской области",
        "group_ko": "직선",
        "incumbent_party": "UR",
        "note_ko": "현직 멜니첸코 재출마. Atlas 등록 5명.",
        "candidates": [
            ("UR", "Melnichenko, Oleg", True),
            ("CPRF", "Shalyapin, Oleg", False),
            ("LDPR", "Kulikov, Pavel", False),
            ("RPPSS", "Yeroshenko, Viktor", False),
            ("SR", "Lisin, Mikhail", False),
        ],
    },
    {
        "id": "tver",
        "name_ko": "트베리 주지사",
        "name_ru": "Губернатор Тверской области",
        "group_ko": "직선",
        "incumbent_party": "UR",
        "note_ko": "루데냐 사퇴 후 권한대행 코롤료프 출마. Atlas 등록 6명.",
        "candidates": [
            ("UR", "Korolyov, Vitaly", True),
            ("CPRF", "Vorobyova, Lyudmila", False),
            ("LDPR", "Levina, Olga", False),
            ("CR", "Malinkovich, Sergey", False),
            ("SR", "Petrova, Tatyana", False),
            ("RPPSS", "Yakovenko, Igor", False),
        ],
    },
    {
        "id": "ulyanovsk",
        "name_ko": "울리야놉스크 주지사",
        "name_ru": "Губернатор Ульяновской области",
        "group_ko": "직선",
        "incumbent_party": "CPRF",
        "note_ko": "현직 루스키흐(공산당) 재출마. 통합러시아는 후보를 내지 않았다(Vedomosti·Atlas).",
        "candidates": [
            ("CPRF", "Russkikh, Aleksey", True),
            ("SR", "Kim, Marina", False),
            ("LDPR", "Marinin, Sergey", False),
            ("NL", "Yasaitis, Yulia", False),
        ],
    },
]

GOV_INDIRECT: List[Dict[str, Any]] = [
    {
        "id": "dagestan",
        "name_ko": "다게스탄 수장(간선)",
        "name_ru": "Глава Республики Дагестан",
        "group_ko": "간선",
        "incumbent_party": "UR",
        "note_ko": "멜리코프 사퇴 후 권한대행 슈추킨(통합러시아). 대통령이 3인을 주의회에 제출. 8기 인민회의 첫 회기에서 뽑는다. 숏리스트는 출처에 없어 후보를 비운다.",
    },
    {
        "id": "karachay-cherkessia",
        "name_ko": "카라차예보체르케스 수장(간선)",
        "name_ru": "Глава Карачаево-Черкесской Республики",
        "group_ko": "간선",
        "incumbent_party": "UR",
        "note_ko": "현직 템레조프 재출마 보도. 대통령 숏리스트 3인은 출처에 없어 후보를 비운다. 투표일 2026-09-20.",
    },
    {
        "id": "north-ossetia",
        "name_ko": "북오세티야 수장(간선)",
        "name_ru": "Глава Республики Северная Осетия",
        "group_ko": "간선",
        "incumbent_party": "UR",
        "note_ko": "현직 멘야일로 재출마 보도. 대통령 숏리스트 3인은 출처에 없어 후보를 비운다. 투표일 2026-09-20.",
    },
]

# RU Wikipedia 2026 EDG table for seats this cycle; EN wiki 2021 UR majority.
# seats = this election. ur_2021 / total_2021 = last full election majority fraction.
LEG: List[Dict[str, Any]] = [
    {"id": "adygea", "name_ko": "아디게야 국가회의", "name_ru": "Государственный совет-Хасэ Республики Адыгея", "group_ko": "공화국", "seats": 50, "ur_2021": 40, "total_2021": 50, "system_ko": "병립 25+25"},
    {"id": "dagestan", "name_ko": "다게스탄 인민회의", "name_ru": "Народное собрание Республики Дагестан", "group_ko": "공화국", "seats": 90, "ur_2021": 69, "total_2021": 90, "system_ko": "명부 비례"},
    {"id": "ingushetia", "name_ko": "인구셰티야 인민회의", "name_ru": "Народное Собрание Республики Ингушетия", "group_ko": "공화국", "seats": 32, "ur_2021": 27, "total_2021": 32, "system_ko": "명부 비례"},
    {"id": "karelia", "name_ko": "카렐리야 입법회의", "name_ru": "Законодательное собрание Республики Карелия", "group_ko": "공화국", "seats": 36, "ur_2021": 22, "total_2021": 36, "system_ko": "병립 18+18. 야블로코 명부 등록 취소"},
    {"id": "mordovia", "name_ko": "모르도바 국가회의", "name_ru": "Государственное Собрание Республики Мордовия", "group_ko": "공화국", "seats": 48, "ur_2021": 42, "total_2021": 48, "system_ko": "병립 24+24"},
    {"id": "chechnya", "name_ko": "체첸 의회", "name_ru": "Парламент Чеченской Республики", "group_ko": "공화국", "seats": 41, "ur_2021": 37, "total_2021": 41, "system_ko": "명부 비례. NL 명부 없음"},
    {"id": "chuvashia", "name_ko": "추바시야 국가회의", "name_ru": "Государственный Совет Чувашской Республики", "group_ko": "공화국", "seats": 44, "ur_2021": 30, "total_2021": 44, "system_ko": "병립 22+22"},
    {"id": "altai-krai", "name_ko": "알타이 변경 입법회의", "name_ru": "Алтайское краевое законодательное собрание", "group_ko": "변경", "seats": 68, "ur_2021": 31, "total_2021": 68, "system_ko": "병립 34+34. 2021만 통합러시아 과반 아님"},
    {"id": "kamchatka", "name_ko": "캄차카 변경 입법회의", "name_ru": "Законодательное собрание Камчатского края", "group_ko": "변경", "seats": 28, "ur_2021": 18, "total_2021": 28, "system_ko": "병립 14+14"},
    {"id": "krasnoyarsk", "name_ko": "크라스노야르스크 변경 입법회의", "name_ru": "Законодательное собрание Красноярского края", "group_ko": "변경", "seats": 52, "ur_2021": 34, "total_2021": 52, "system_ko": "병립. 러 위키 26+26(22×1+2×2)"},
    {"id": "perm", "name_ko": "페름 변경 입법회의", "name_ru": "Законодательное Собрание Пермского края", "group_ko": "변경", "seats": 60, "ur_2021": 40, "total_2021": 60, "system_ko": "병립 30+30"},
    {"id": "primorsky", "name_ko": "연해주 입법회의", "name_ru": "Законодательное Собрание Приморского края", "group_ko": "변경", "seats": 40, "ur_2021": 23, "total_2021": 40, "system_ko": "병립 20+20"},
    {"id": "stavropol", "name_ko": "스타브로폴 변경 두마", "name_ru": "Дума Ставропольского края", "group_ko": "변경", "seats": 50, "ur_2021": 43, "total_2021": 50, "system_ko": "병립 25+25"},
    {"id": "amur", "name_ko": "아무르주 입법회의", "name_ru": "Законодательное собрание Амурской области", "group_ko": "주", "seats": 27, "ur_2021": 18, "total_2021": 27, "system_ko": "병립 9+18"},
    {"id": "astrakhan", "name_ko": "아스트라한주 두마", "name_ru": "Дума Астраханской области", "group_ko": "주", "seats": 44, "ur_2021": 27, "total_2021": 44, "system_ko": "병립 22+22"},
    {"id": "vologda", "name_ko": "볼로그다주 입법회의", "name_ru": "Законодательное Собрание Вологодской области", "group_ko": "주", "seats": 34, "ur_2021": 24, "total_2021": 34, "system_ko": "병립 17+17"},
    {"id": "kaliningrad", "name_ko": "칼리닌그라드주 입법회의", "name_ru": "Законодательное собрание Калининградской области", "group_ko": "주", "seats": 40, "ur_2021": 29, "total_2021": 40, "system_ko": "병립 20+20"},
    {"id": "kirov", "name_ko": "키로프주 입법회의", "name_ru": "Законодательное собрание Кировской области", "group_ko": "주", "seats": 40, "ur_2021": 24, "total_2021": 40, "system_ko": "러 위키 이번 40(13+27). 영문 위키는 45(기존 40, 15+30). 병기.", "seats_conflict": True},
    {"id": "kursk", "name_ko": "쿠르스크주 두마", "name_ru": "Курская областная дума", "group_ko": "주", "seats": 45, "ur_2021": 31, "total_2021": 45, "system_ko": "병립. 러 위키 22+23, 영문 위키 21+24"},
    {"id": "leningrad", "name_ko": "레닌그라드주 입법회의", "name_ru": "Законодательное собрание Ленинградской области", "group_ko": "주", "seats": 50, "ur_2021": 35, "total_2021": 50, "system_ko": "병립 25+25. 야블로코 명부 등록 취소"},
    {"id": "lipetsk", "name_ko": "리페츠크주 의회", "name_ru": "Липецкий областной совет депутатов", "group_ko": "주", "seats": 36, "ur_2021": 23, "total_2021": 42, "system_ko": "병립 9+27. 정수 42→36"},
    {"id": "moscow-oblast", "name_ko": "모스크바주 두마", "name_ru": "Московская областная дума", "group_ko": "주", "seats": 50, "ur_2021": 36, "total_2021": 50, "system_ko": "병립 25+25"},
    {"id": "murmansk", "name_ko": "무르만스크주 두마", "name_ru": "Мурманская областная дума", "group_ko": "주", "seats": 28, "ur_2021": 25, "total_2021": 32, "system_ko": "병립 10+18. 정수 32→28"},
    {"id": "nizhny-novgorod", "name_ko": "니즈니노브고로드주 입법회의", "name_ru": "Законодательное собрание Нижегородской области", "group_ko": "주", "seats": 50, "ur_2021": 40, "total_2021": 50, "system_ko": "병립 25+25"},
    {"id": "novgorod", "name_ko": "노브고로드주 두마", "name_ru": "Новгородская областная дума", "group_ko": "주", "seats": 32, "ur_2021": 23, "total_2021": 32, "system_ko": "정수 32. 러 위키 16+16, 영문 위키 12+20"},
    {"id": "omsk", "name_ko": "옴스크주 입법회의", "name_ru": "Законодательное собрание Омской области", "group_ko": "주", "seats": 44, "ur_2021": 26, "total_2021": 44, "system_ko": "병립 22+22"},
    {"id": "orenburg", "name_ko": "오렌부르크주 입법회의", "name_ru": "Законодательное собрание Оренбургской области", "group_ko": "주", "seats": 47, "ur_2021": 29, "total_2021": 47, "system_ko": "병립 24+23"},
    {"id": "oryol", "name_ko": "오룔주 인민대의원회의", "name_ru": "Орловский областной Совет народных депутатов", "group_ko": "주", "seats": 50, "ur_2021": 27, "total_2021": 50, "system_ko": "병립 25+25"},
    {"id": "pskov", "name_ko": "프스코프주 입법회의", "name_ru": "Законодательное собрание Псковской области", "group_ko": "주", "seats": 26, "ur_2021": 19, "total_2021": 26, "system_ko": "병립 13+13"},
    {"id": "samara", "name_ko": "사마라주 두마", "name_ru": "Самарская Губернская дума", "group_ko": "주", "seats": 50, "ur_2021": 36, "total_2021": 50, "system_ko": "병립 25+25"},
    {"id": "sverdlovsk", "name_ko": "스베르들롭스크주 입법회의", "name_ru": "Законодательное собрание Свердловской области", "group_ko": "주", "seats": 50, "ur_2021": 33, "total_2021": 50, "system_ko": "병립 25+25"},
    {"id": "tambov", "name_ko": "탐보프주 두마", "name_ru": "Тамбовская областная дума", "group_ko": "주", "seats": 50, "ur_2021": 42, "total_2021": 50, "system_ko": "병립 25+25"},
    {"id": "tver-leg", "name_ko": "트베리주 입법회의", "name_ru": "Законодательное собрание Тверской области", "group_ko": "주", "seats": 40, "ur_2021": 29, "total_2021": 40, "system_ko": "병립 20+20"},
    {"id": "tomsk", "name_ko": "톰스크주 입법두마", "name_ru": "Законодательная дума Томской области", "group_ko": "주", "seats": 42, "ur_2021": 27, "total_2021": 42, "system_ko": "병립 21+21"},
    {"id": "tyumen", "name_ko": "튜멘주 두마", "name_ru": "Тюменская областная дума", "group_ko": "주", "seats": 48, "ur_2021": 38, "total_2021": 48, "system_ko": "병립 24+24"},
    {"id": "spb", "name_ko": "상트페테르부르크 입법회의", "name_ru": "Законодательное собрание Санкт-Петербурга", "group_ko": "연방시", "seats": 50, "ur_2021": 29, "total_2021": 50, "system_ko": "병립 25+25. 야블로코 명부 등록 취소"},
    {"id": "eao", "name_ko": "유대인자치주 입법회의", "name_ru": "Законодательное собрание Еврейской АО", "group_ko": "자치주", "seats": 19, "ur_2021": 14, "total_2021": 19, "system_ko": "병립 10+9. PPD 명부 1곳(Atlas)"},
    {"id": "khmao", "name_ko": "한티만시 두마", "name_ru": "Дума Ханты-Мансийского АО — Югры", "group_ko": "자치구", "seats": 38, "ur_2021": 29, "total_2021": 38, "system_ko": "러 위키 이번 38(19+19). 영문 위키는 40(기존 38). 병기.", "seats_conflict": True},
    {"id": "chukotka", "name_ko": "축치 두마", "name_ru": "Дума Чукотского АО", "group_ko": "자치구", "seats": 15, "ur_2021": 11, "total_2021": 15, "system_ko": "병립. NL 명부 없음"},
]


def compact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: compact(v) for k, v in obj.items() if v is not None and v != ""}
    if isinstance(obj, list):
        return [compact(x) for x in obj]
    return obj


def cand(party: str, name: str, incumbent: bool, source: str) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "party_abbr": party,
        "name": name,
        "status": "nominated",
        "source": source,
    }
    if incumbent:
        row["incumbent"] = True
    return row


def gov_districts() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in GOV_DIRECT:
        out.append(
            {
                "id": row["id"],
                "name_ko": row["name_ko"],
                "name_ru": row["name_ru"],
                "group_ko": row["group_ko"],
                "seats": 1,
                "status": "nominated",
                "note_ko": row["note_ko"],
                "candidates": [
                    cand(p, n, inc, ATLAS) for p, n, inc in row["candidates"]
                ],
            }
        )
    for row in GOV_INDIRECT:
        out.append(
            {
                "id": row["id"],
                "name_ko": row["name_ko"],
                "name_ru": row["name_ru"],
                "group_ko": row["group_ko"],
                "seats": 1,
                "status": "scheduled",
                "note_ko": row["note_ko"],
                "candidates": [],
            }
        )
    n = sum(len(d["candidates"]) for d in out if d["status"] == "nominated")
    if n != 39:
        raise SystemExit(f"expected 39 registered direct-head candidates, got {n}")
    if len(out) != 11:
        raise SystemExit(f"expected 11 head races, got {len(out)}")
    return out


def leg_districts() -> List[Dict[str, Any]]:
    if len(LEG) != 39:
        raise SystemExit(f"expected 39 legislatures, got {len(LEG)}")
    out = []
    for row in LEG:
        note = (
            f"이번 정수 {row['seats']}. 2021 통합러시아 {row['ur_2021']}/{row['total_2021']}. "
            f"{row['system_ko']}. 등록 명부·소선거구 후보는 전수 미수록."
        )
        out.append(
            {
                "id": row["id"],
                "name_ko": row["name_ko"],
                "name_ru": row["name_ru"],
                "group_ko": row["group_ko"],
                "seats": row["seats"],
                "status": "scheduled",
                "note_ko": note,
                "candidates": [],
            }
        )
    return out


def parties_block(used: set) -> List[Dict[str, Any]]:
    out = []
    for abbr, meta in PARTY_META.items():
        if abbr not in used:
            continue
        row = {"abbr": abbr}
        for k in ("name_ru", "name_ko", "name_en", "leader_ko", "note_ko"):
            if meta.get(k):
                row[k] = meta[k]
        out.append(row)
    missing = used - {p["abbr"] for p in out}
    if missing:
        raise SystemExit(f"PARTY_META missing {missing}")
    return out


def build() -> Dict[str, Any]:
    heads = gov_districts()
    legs = leg_districts()
    used = {"UR", "CPRF"}
    for d in heads:
        for c in d["candidates"]:
            used.add(c["party_abbr"])
    used.update(PARTY_META)  # keep small parties mentioned in notes
    current_heads = {
        "by_party": {"UR": 10, "CPRF": 1},
        "total": 11,
        "as_of": AS_OF,
        "note_ko": (
            "이번 회차 11개 지방 수장 자리의 현직·권한대행. "
            "통합러시아 10(카디로프·즈두노프·호발릭·슈바예프·코발추크·멜니첸코·코롤료프·슈추킨·템레조프·멘야일로), "
            "공산당 1(루스키흐). 10+1=11. "
            "간선 3곳의 숏리스트는 아직 출처에 없다."
        ),
        "vacancies": 0,
    }
    ur_2021 = sum(r["ur_2021"] for r in LEG)
    tot_2021 = sum(r["total_2021"] for r in LEG)
    current_legs = {
        "by_party": {"UR": ur_2021},
        "total": tot_2021,
        "as_of": "2021-09-19",
        "note_ko": (
            f"39개 주의회를 한 원으로 더한 숫자가 아니다. total {tot_2021}은 2021 선출 당시 정수 합"
            f"(리페츠크 42, 무르만스크 32). UR {ur_2021}은 영문 위키 2021 통합러시아 의석 합. "
            f"나머지 정당 분해·2026 공시전 이적은 출처에 없어 넣지 않았다. "
            f"{ur_2021}≠{tot_2021}. 이번 회차 정수가 바뀐 주는 각 행 note_ko."
        ),
    }
    doc = {
        "schema": "elections_contest_v1",
        "event_id": EVENT_ID,
        "iso3": "RUS",
        "date": "2026-09-20",
        "as_of": AS_OF,
        "sources": [ATLAS, WIKI_EN, WIKI_RU, TASS_FACT, TASS_JUNE, VEDOMOSTI, CIKRF],
        "parties": parties_block(used),
        "columns": [
            {
                "key": "heads",
                "label_ko": "지방 수장",
                "current": current_heads,
                "contested_ko": "8곳 직선 + 3곳 주의회 간선. 투표 2026-09-18–20, 집계 전.",
                "seat_note_ko": "Atlas Table 1: 직선 8곳 공천 40·등록 39(벨고로드 로디나 사퇴). 간선 3곳은 대통령 숏리스트 미공개.",
                "districts": heads,
            },
            {
                "key": "legislatures",
                "label_ko": "주의회",
                "current": current_legs,
                "contested_ko": "39개 주의회 전원. 명부·소선거구 후보는 전수 미수록(partial).",
                "seat_note_ko": (
                    "TASS·러 위키: 39개 주. Atlas: 등록 명부 254. "
                    "UR·CPRF·LDPR·SR는 39곳 전원, NL은 체첸·축치 제외. "
                    "시·구 의회와 다른 주 보궐은 이 이벤트에 넣지 않았다."
                ),
                "districts": legs,
            },
        ],
    }
    return compact(doc)


def upsert_index() -> None:
    path = PUBLIC / "elections_contests_index_v1.json"
    if path.exists():
        idx = json.loads(path.read_text(encoding="utf-8"))
    else:
        idx = {
            "schema": "elections_contests_index_v1",
            "null_policy": {"없음": "해당 없음", "불명": "미확정"},
            "events": [],
        }
    idx["as_of"] = AS_OF
    idx.setdefault("null_policy", {"없음": "해당 없음", "불명": "미확정"})
    row = {
        "event_id": EVENT_ID,
        "iso3": "RUS",
        "date": "2026-09-20",
        "path": f"elections_contests/{EVENT_ID}.json",
        "status": "partial",
        "as_of": AS_OF,
    }
    events = [e for e in idx.get("events", []) if e.get("event_id") != EVENT_ID]
    events.append(row)
    events.sort(key=lambda e: (e.get("date") or "", e.get("event_id") or ""))
    idx["events"] = events
    path.write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    doc = build()
    CONTESTS_DIR.mkdir(parents=True, exist_ok=True)
    out = CONTESTS_DIR / f"{EVENT_ID}.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    upsert_index()
    heads = doc["columns"][0]["districts"]
    legs = doc["columns"][1]["districts"]
    print(
        f"wrote {out} ({out.stat().st_size} bytes); "
        f"heads {len(heads)} / {sum(len(d['candidates']) for d in heads)}; "
        f"legs {len(legs)} scheduled"
    )


if __name__ == "__main__":
    main()
