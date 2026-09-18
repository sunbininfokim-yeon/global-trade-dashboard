#!/usr/bin/env python3
"""One-shot patch: china_leadership_extracted.json from the 2026-09-12 briefing."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PATH = ROOT / "config" / "china_leadership_extracted.json"


def person(**kwargs):
    return {k: v for k, v in kwargs.items() if v is not None}


def minister_row(
    *,
    dept_id: str,
    title_ko: str,
    title_zh: str,
    name_en: str,
    name_zh: str,
    name_ko: str,
    since: str,
    cabinet_23: bool,
    note_ko: str = "",
    party_group_secretary=None,
    predecessor=None,
):
    row = {
        "id": dept_id,
        "title_ko": title_ko,
        "title_zh": title_zh,
        "cabinet_23": cabinet_23,
        "minister": person(
            name_en=name_en,
            name_zh=name_zh,
            name_ko=name_ko,
            since=since,
            status="incumbent",
            confidence="high",
            title_ko=title_ko,
        ),
    }
    if note_ko:
        row["minister"]["note_ko"] = note_ko
    if party_group_secretary:
        row["party_group_secretary"] = party_group_secretary
    if predecessor:
        row["predecessor"] = predecessor
    return row


def main() -> None:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    data["version"] = 6
    data["as_of"] = "2026-09-12"
    data["extracted_at"] = "2026-09-12"
    data["next_full_review"] = "2026-10-01"
    data["merge_note"] = (
        "2026-09-12 Cursor patch: CCP General Office / Policy Research / "
        "CFEAC office / MCF office + 26 State Council constituent departments "
        "from NPC decrees and Xinhua bios. Wikipedia not used."
    )

    psc = data["party_state"]["politburo_standing_committee"]["rank_order"]
    for row in psc:
        if row.get("name_en") == "Cai Qi":
            row["role_ko"] = "중앙서기처 제1서기·중앙판공청 주임"
            row["title_ko"] = "중앙판공청 주임"
            row["also"] = [
                "정치국 상무위원 5위",
                "중앙·국가기관 공위 서기",
                "중앙당교 교장",
                "국가행정학원 원장",
            ]

    for row in data["party_state"]["politburo"]["active"]:
        if row.get("name_en") == "Cai Qi":
            row["role_ko"] = "중앙서기처 제1서기·중앙판공청 주임"
            row["title_ko"] = "중앙판공청 주임"
        if row.get("name_en") == "He Lifeng":
            row["role_ko"] = "부총리·중앙재경위 판공실 주임"
            row["title_ko"] = "중앙재경위 판공실 주임"

    existing = data["party_state"]["central_departments"]
    data["party_state"]["central_departments"] = {
        "note_ko": "공산당 핵심 부서 + 판공 4곳 + 정법. 판공 명목 주임이 비면 status=unknown.",
        "as_of": "2026-09-12",
        "general_office": {
            "id": "ccp_general_office",
            "title_ko": "중앙판공청",
            "title_zh": "中共中央办公厅",
            "function_ko": "최고지도자 일정·문건·회의·경호·정보 유통. 시진핑 참모장.",
            "director": person(
                name_en="Cai Qi",
                name_zh="蔡奇",
                name_ko="차이치",
                since="2023-03",
                status="incumbent",
                confidence="high",
                rank_ko="정치국 상무위원 5위, 서기처 1순위",
                also=[
                    "중앙·국가기관 공위 서기",
                    "2026-05/06 중앙당교 교장·국가행정학원 원장",
                ],
                predecessor_ko="딩쉐샹 丁薛祥",
                title_ko="중앙판공청 주임",
            ),
            "deputies": [
                person(
                    name_en="Meng Xiangfeng",
                    name_zh="孟祥锋",
                    name_ko="멍샹펑",
                    status="incumbent",
                    confidence="medium",
                    note_ko="확인된 부주임. 전수 아님.",
                    title_ko="중앙판공청 부주임",
                )
            ],
            "sources": [
                "xinhua_leaders_bio",
                "scmp_2023_general_office",
                "reuters_2026-06_party_school",
            ],
        },
        "organization_department": existing["organization_department"],
        "propaganda_department": existing["propaganda_department"],
        "united_front_work_department": existing["united_front_work_department"],
        "political_and_legal_affairs": existing["political_and_legal_affairs"],
        "policy_research_office": {
            "id": "ccp_policy_research_office",
            "title_ko": "중앙정책연구실",
            "title_zh": "中央政策研究室",
            "function_ko": "당대회 보고·전회 결정·이념 문건 기초.",
            "director": person(
                name_en="Tang Fangyu",
                name_zh="唐方裕",
                name_ko="탕팡위",
                since="2025-12",
                status="incumbent",
                confidence="high",
                note_ko="국가매체 직함 공표 2026-01-14. 전임 장진취안 2020-10~2025-12.",
                title_ko="중앙정책연구실 주임",
            ),
            "deputies": [
                person(name_en="Hu Jinqi", name_zh="胡金旗", name_ko="후진치", status="incumbent", confidence="medium"),
                person(name_en="Deng Maosheng", name_zh="邓茂生", name_ko="덩마오성", status="incumbent", confidence="medium"),
                person(
                    name_en="Zhou Xinqun",
                    name_zh="周新群",
                    name_ko="저우신췬",
                    since="2026-06",
                    status="incumbent",
                    confidence="medium",
                ),
            ],
            "sources": [
                "caixin_2026-01-15",
                "trivium_2026-01-15",
            ],
        },
        "cfeac_office": {
            "id": "cfeac_office",
            "title_ko": "중앙재경위원회 판공실",
            "title_zh": "中央财经委员会办公室",
            "commission_chair": person(name_en="Xi Jinping", name_zh="习近平", name_ko="시진핑"),
            "commission_vice": person(name_en="Li Qiang", name_zh="李强", name_ko="리창"),
            "function_ko": "거시·금융 의제 설정. 발개위·재정부보다 앞선다.",
            "director": person(
                name_en="He Lifeng",
                name_zh="何立峰",
                name_ko="허리펑",
                since="2023-03",
                status="incumbent",
                confidence="high",
                rank_ko="정치국위원·부총리",
                also=["중앙금융위 판공실 주임", "중앙금융공위 서기"],
                title_ko="중앙재경위 판공실 주임",
            ),
            "executive_deputy": person(
                name_en="Han Wenxiu",
                name_zh="韩文秀",
                name_ko="한원슈",
                since="2018-12",
                status="incumbent",
                confidence="high",
                rank_ko="정부급, 일상 주재",
                also=["중앙농촌공작영도소조 판공실 주임"],
                note_ko="중국발전고위포럼 2026-03-22 직함.",
                title_ko="중앙재경위 판공실 일상 부주임",
            ),
            "sources": [
                "xinhua_he_lifeng_bio_2023-10-30",
                "cdf_2026-03_han_wenxiu",
            ],
        },
        "mcf_office": {
            "id": "mcf_office",
            "title_ko": "중앙군민융합발전위원회 판공실",
            "title_zh": "中央军民融合发展委员会办公室",
            "commission_chair": person(name_en="Xi Jinping", name_zh="习近平", name_ko="시진핑"),
            "function_ko": "민군 융합 상설 판공. DoD CMPR은 전략만 서술하고 이 사무실 성명은 없음.",
            "director": {
                "name_en": None,
                "name_zh": None,
                "name_ko": None,
                "status": "unknown",
                "confidence": "low",
                "note_ko": "장가오리(2017–18) → 한정(2018–?) 이후 공식 후임 없음. TODO.",
                "title_ko": "군민융합 판공실 주임",
            },
            "executive_deputy": person(
                name_en="Shao Xinyu",
                name_zh="邵新宇",
                name_ko="사오신이",
                since="2025-04-09",
                status="incumbent",
                confidence="medium-high",
                rank_ko="정부급",
                note_ko="공정원 원사. 전 과기부 부부장·후베이 상무부성장.",
                title_ko="군민융합 판공실 상무부주임",
            ),
            "deputies": [
                person(
                    name_en="Pei Jinjia",
                    name_zh="裴金佳",
                    name_ko="페이진자",
                    status="incumbent",
                    confidence="high",
                    note_ko="퇴역군인부장 겸",
                    title_ko="군민융합 판공실 부주임",
                ),
                person(
                    name_en="Wu Xihua",
                    name_zh="吴喜铧",
                    name_ko="우시화",
                    status="incumbent",
                    confidence="medium",
                    note_ko="로켓군 소장",
                    title_ko="군민융합 판공실 부주임",
                ),
                person(
                    name_en="Yin Weijun",
                    name_zh="尹卫军",
                    name_ko="인웨이쥔",
                    status="incumbent",
                    confidence="medium",
                    title_ko="군민융합 판공실 부주임",
                ),
            ],
            "sources": ["cctv_protocol_2025-04", "most_appointment_history"],
        },
    }

    data["party_state"]["state_council"] = {
        "as_of": "2026-09-12",
        "note_ko": "공식 구성부문 26곳. cabinet_23=false는 국방·인행·감사.",
        "premier": {
            "name_en": "Li Qiang",
            "name_zh": "李强",
            "name_ko": "리창",
            "status": "incumbent",
            "confidence": "high",
            "title_ko": "국무원 총리",
            "_internal": {"xi_tie": "close_aide_25y"},
        },
        "vice_premiers": [
            person(name_en="Ding Xuexiang", name_zh="丁薛祥", name_ko="딩쉐샹", title_ko="상무부총리", status="incumbent", confidence="high"),
            person(name_en="He Lifeng", name_zh="何立峰", name_ko="허리펑", title_ko="부총리", status="incumbent", confidence="high", note_ko="중앙재경위·중앙금융위 판공실 주임 겸"),
            person(name_en="Zhang Guoqing", name_zh="张国清", name_ko="장궈칭", title_ko="부총리", status="incumbent", confidence="high"),
            person(name_en="Liu Guozhong", name_zh="刘国中", name_ko="류궈중", title_ko="부총리", status="incumbent", confidence="high"),
        ],
        "state_councilors": [
            person(name_en="Wang Xiaohong", name_zh="王小洪", name_ko="왕샤오훙", title_ko="국무위원·공안부장", status="incumbent", confidence="high"),
            person(name_en="Wu Zhenglong", name_zh="吴政隆", name_ko="우정룽", title_ko="국무위원·국무원 비서장", status="incumbent", confidence="high"),
            person(name_en="Shen Yiqin", name_zh="谌贻琴", name_ko="선이친", title_ko="국무위원", status="incumbent", confidence="high", note_ko="여성, 바이족"),
        ],
        "constituent_departments": [
            minister_row(dept_id="mfa", title_ko="외교부", title_zh="外交部", name_en="Wang Yi", name_zh="王毅", name_ko="왕이", since="2023-07-25", cabinet_23=True, note_ko="당위 서기는 제위 齐玉. 부장≠당서기", party_group_secretary=person(name_en="Qi Yu", name_zh="齐玉", name_ko="제위", title_ko="외교부 당위 서기", confidence="high")),
            minister_row(dept_id="mod", title_ko="국방부", title_zh="国防部", name_en="Dong Jun", name_zh="董军", name_ko="둥쥔", since="2023-12-29", cabinet_23=False, note_ko="PLA 별선"),
            minister_row(dept_id="ndrc", title_ko="국가발전개혁위원회", title_zh="国家发展和改革委员会", name_en="Zheng Shanjie", name_zh="郑栅洁", name_ko="정산제", since="2023-03-12", cabinet_23=True, note_ko="재경위 아래 실무"),
            minister_row(dept_id="moe", title_ko="교육부", title_zh="教育部", name_en="Huai Jinpeng", name_zh="怀进鹏", name_ko="화이진펑", since="2021-08-20", cabinet_23=True),
            minister_row(dept_id="most", title_ko="과학기술부", title_zh="科学技术部", name_en="Yin Hejun", name_zh="阴和俊", name_ko="인허쥔", since="2023-10-24", cabinet_23=True),
            minister_row(dept_id="miit", title_ko="공업정보화부", title_zh="工业和信息化部", name_en="Li Lecheng", name_zh="李乐成", name_ko="리러청", since="2025-04-30", cabinet_23=True, note_ko="진좡룽 면. 주석령 48호.", predecessor=person(name_en="Jin Zhuanglong", name_zh="金壮龙", name_ko="진좡룽", status="removed", next_post="unknown", confidence="high")),
            minister_row(dept_id="seac", title_ko="국가민족사무위원회", title_zh="国家民族事务委员会", name_en="Chen Ruifeng", name_zh="陈瑞峰", name_ko="천루이펑", since="2025-09-12", cabinet_23=True),
            minister_row(dept_id="mps", title_ko="공안부", title_zh="公安部", name_en="Wang Xiaohong", name_zh="王小洪", name_ko="왕샤오훙", since="2022-06-24", cabinet_23=True, note_ko="국무위원 겸"),
            minister_row(dept_id="mss", title_ko="국가안전부", title_zh="国家安全部", name_en="Chen Yixin", name_zh="陈一新", name_ko="천이신", since="2022-10-30", cabinet_23=True),
            minister_row(dept_id="mca", title_ko="민정부", title_zh="民政部", name_en="Li Changguan", name_zh="李常官", name_ko="리창관", since="2026-08-28", cabinet_23=True, note_ko="루즈위안 면. 주석령 85호.", predecessor=person(name_en="Lu Zhiyuan", name_zh="陆治原", name_ko="루즈위안", status="removed", confidence="high")),
            minister_row(dept_id="moj", title_ko="사법부", title_zh="司法部", name_en="He Rong", name_zh="贺荣", name_ko="허룽", since="2023-02-24", cabinet_23=True, note_ko="여성"),
            minister_row(dept_id="mof", title_ko="재정부", title_zh="财政部", name_en="Lan Fo'an", name_zh="蓝佛安", name_ko="란포안", since="2023-10-24", cabinet_23=True),
            minister_row(dept_id="mohrss", title_ko="인력자원사회보장부", title_zh="人力资源和社会保障部", name_en="Wang Xiaoping", name_zh="王晓萍", name_ko="왕샤오핑", since="2022-12-30", cabinet_23=True, note_ko="여성"),
            minister_row(dept_id="mnr", title_ko="자연자원부", title_zh="自然资源部", name_en="Guan Zhi'ou", name_zh="关志鸥", name_ko="관즈어우", since="2024-12-25", cabinet_23=True),
            minister_row(dept_id="mee", title_ko="생태환경부", title_zh="生态环境部", name_en="Huang Runqiu", name_zh="黄润秋", name_ko="황룬추", since="2020-04-29", cabinet_23=True, note_ko="구삼학사. 당조 서기는 쑨진룽.", party_group_secretary=person(name_en="Sun Jinlong", name_zh="孙金龙", name_ko="쑨진룽", title_ko="생태환경부 당조 서기", confidence="high")),
            minister_row(dept_id="mohurd", title_ko="주택도시농촌건설부", title_zh="住房和城乡建设部", name_en="Ni Hong", name_zh="倪虹", name_ko="니훙", since="2022-06-24", cabinet_23=True),
            minister_row(dept_id="mot", title_ko="교통운수부", title_zh="交通运输部", name_en="Liu Wei", name_zh="刘伟", name_ko="류웨이", since="2024-11-08", cabinet_23=True),
            minister_row(dept_id="mwr", title_ko="수리부", title_zh="水利部", name_en="Li Guoying", name_zh="李国英", name_ko="리궈잉", since="2021-02-28", cabinet_23=True),
            minister_row(dept_id="mara", title_ko="농업농촌부", title_zh="农业农村部", name_en="Zhang Zhu", name_zh="张柱", name_ko="장주", since="2026-04-30", cabinet_23=True, note_ko="한쥔 면. 거취 unknown. 주석령 76호.", predecessor=person(name_en="Han Jun", name_zh="韩俊", name_ko="한쥔", status="removed", next_post="unknown", confidence="high")),
            minister_row(dept_id="mofcom", title_ko="상무부", title_zh="商务部", name_en="Wang Wentao", name_zh="王文涛", name_ko="왕원타오", since="2020-12-26", cabinet_23=True),
            minister_row(dept_id="mct", title_ko="문화여유부", title_zh="文化和旅游部", name_en="Sun Yeli", name_zh="孙业礼", name_ko="쑨예리", since="2023-12-29", cabinet_23=True),
            minister_row(dept_id="nhc", title_ko="국가위생건강위원회", title_zh="国家卫生健康委员会", name_en="Lei Haichao", name_zh="雷海潮", name_ko="레이하이차오", since="2024-06-28", cabinet_23=True),
            minister_row(dept_id="mva", title_ko="퇴역군인사무부", title_zh="退役军人事务部", name_en="Pei Jinjia", name_zh="裴金佳", name_ko="페이진자", since="2022-06-24", cabinet_23=True, note_ko="군민융합 판공실 부주임 겸"),
            minister_row(dept_id="mem", title_ko="응급관리부", title_zh="应急管理部", name_en="Zhang Chengzhong", name_zh="张成中", name_ko="장청중", since="2026-04-30", cabinet_23=True, note_ko="왕샹시 2026-02 면. 주석령 76호.", predecessor=person(name_en="Wang Xiangxi", name_zh="王祥喜", name_ko="왕샹시", status="removed", confidence="high")),
            minister_row(dept_id="pbc", title_ko="중국인민은행", title_zh="中国人民银行", name_en="Pan Gongsheng", name_zh="潘功胜", name_ko="판궁성", since="2023-07-25", cabinet_23=False, note_ko="중앙금융위 아래"),
            minister_row(dept_id="nao", title_ko="감사서", title_zh="审计署", name_en="Hou Kai", name_zh="侯凯", name_ko="허우카이", since="2020-06-30", cabinet_23=False),
        ],
        "sources": [
            "https://www.gov.cn/gwyzzjg/",
            "https://www.gov.cn/yaowen/liebiao/202604/content_7067518.htm",
            "https://www.gov.cn/yaowen/liebiao/202608/content_7079463.htm",
        ],
    }

    n = len(data["party_state"]["state_council"]["constituent_departments"])
    if n != 26:
        raise SystemExit(f"expected 26 departments, got {n}")

    todos = list(data.get("todo_next") or [])
    extra = [
        "군민융합 판공실 명목 주임 (한정 이후) unknown 유지",
        "한쥔·진좡룽 거취 unknown",
        "멍샹펑 외 중난 부주임 전수",
    ]
    for item in extra:
        if item not in todos:
            todos.append(item)
    data["todo_next"] = todos

    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"patched {PATH} version={data['version']} departments={n}")


if __name__ == "__main__":
    main()
