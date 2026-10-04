# 10월 7일 메일링 배포 준비

## 10월 4일 처리

PR #321을 main `29600737`과 통합했습니다. main의 즐겨찾기·마이페이지 UI, 기존 원자재 sender, Congress incremental 설정을 보존했습니다. 옛 PR을 병합하는 것만으로 sender가 교체되거나 실제 메일 발송이 켜지지 않습니다. Auth의 채널별 설정 API는 남기되, 새 채널 스위치 UI는 포함하지 않습니다.

필요한 기본 메일 테이블·함수와 #443의 후속 migration이 같은 트리에 있습니다. 기존 Supabase에는 이미 설치되어 있어 운영 SQL을 재실행하지 않았습니다. 새 메일 설치 테스트는 비어 있는 PostgreSQL 런타임에서 앱 필수 테이블을 먼저 만든 다음 실제 메일 migration을 순서대로 적용합니다. 전체 Supabase/pgvector 프로젝트 설치 검증과는 구분합니다.

- 메일 테스트 46개 + #443 보강 테스트 15개 통과.
- RSS 파서·분류·실패 시 이전 자료 보존 테스트 79개 통과.
- 정책 검색 테스트 18개 통과.
- Worker 타입 생성·정적 검사·dry-run 빌드 통과. Wrangler 4.147.0 및 호환 Workers 타입으로 고정했고 npm audit 결과 0건. GitHub Mailing Reliability Checks, Ownership guard, Feed probe도 통과했습니다(메일 run 37191532988).

맥이 공식 기관 피드를 직접 읽고 private snapshot을 저장한 뒤 DB 보관하도록 연결했습니다. 첫 실행 30개 소스 중 29개 성공, 유효 보고서 69건 저장, 발행일 불명 14개 제외입니다. 운영 DB 전체 보관은 98→103건으로 늘었고 원자재 발송 대기 5건은 10/5 08:00 KST로 예약되어 있습니다. USDA newsroom/NASS/FAS와 EIA 세 소스가 응답했습니다. BCR 시간 초과 1개는 이전 자료 3건을 보존했습니다. 생성된 JSON은 웹사이트에 배포하지 않았습니다. 키워드·시리즈 사전·기관 문맥으로 주제를 분류하며 Gemini는 일부 번역을 보조합니다.

맥 법안 실행기 한 개(PID 13074)를 재개했습니다. 즐겨찾기 법안 4개를 먼저 확인했으며 일반 수집은 실행 중입니다. 마지막 기존 프로세스가 사라진 원인은 로그만으로 확정할 수 없습니다. 전원·로그아웃·재부팅 후 자동 재기동 설정은 이번에 설치하지 않았습니다.

실제 검색은 Node fetch에서 CLARITY Act·암호화폐·3조건 검색 응답 200을 확인했습니다. 암호화폐 결과에 CLARITY가 4번째로 나왔고 한국어·복수 조건 요청에서 semantic_available=true를 확인했습니다. CLARITY 단일 요청 중 하나는 semantic_available=false로 문자 검색이 보완했습니다. 빈 결과와 장애를 구분하며 모든 요청의 공급자 가용성을 보장하지 않습니다.

## 실제 발송 전환

10/4 실제 조회에서 `chokemonitor.com` Resend 도메인은 verified, Supabase/Resend Secret은 존재하고 cron은 10분 주기입니다. 현재 `chokemonitor-mailing`의 MAIL_SEND_ENABLED는 false입니다. 기본 주소는 alerts@chokemonitor.com이며 Resend가 이메일을 발송합니다. Cloudflare의 cron은 10분마다 DB 대기열을 읽는 실행기입니다.

1. 승인된 전환 시 기존 commodity-digest 예약을 비활성화하고 실행 중인 sender가 없음을 확인합니다. Congress의 POLICY_FAVORITES_MAIL_ENABLED도 꺼진 상태를 유지합니다.
2. Worker의 Supabase·Resend Secret과 루트 도메인 인증을 확인합니다. 이미 등록된 키는 다시 채팅에 받을 필요 없습니다.
3. Worker를 MAIL_SEND_ENABLED=true로 배포하고 실제 설정을 읽어 검증합니다. 정책은 감지 다음날 06시부터, 원자재는 월요일 08시부터 처리합니다. 수신함 도착 시각을 보장하지 않습니다.
4. 허용된 테스트 계정으로 전송·공급자 접수·실제 수신함을 각각 확인합니다. 실패하면 OFF로 복귀하고 대기열·발송 기록·idempotency key를 보존합니다.

10월 7일 배포를 목표로 하지만 날짜를 말한 것만으로 운영 병합·UI 배포·자동 발송 활성화를 예약하지 않았습니다. 현재 수정은 draft 검토 대상이며 실제 발송 전환 승인이 필요합니다.

## 남은 검증

- 재개한 맥 일반 법안 배치 완료와 다음 4시간 실행.
- 실제 로그인 화면의 별 클릭 → 마이페이지 표시. DB에 즐겨찾기가 있다는 것만으로 클릭 경로가 검증된 것은 아닙니다.
- 실제 정책 변화 이벤트의 예약 전송과 수신함 확인. 운영 법안 상태를 테스트용으로 조작하지 않습니다.
- EO·regulation 최신 수집 범위, 과거 제정법 누락·벡터 최신성, EO–법률–규칙 연결의 전체 완성도. 이번 Congress/RSS 복구로 완료됐다고 주장하지 않습니다.
