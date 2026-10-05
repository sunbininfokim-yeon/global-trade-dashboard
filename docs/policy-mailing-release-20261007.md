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

## 10월 5일 요청 1~5 보강

기존 원자재 메일이 실제로 운영 중이라는 점을 확인했습니다. GitHub run `37252775985`는 10/5 10:46:55 KST에 시작해 다이제스트 1건을 보냈으며, 현재 Resend 키에서 해당 메일 `delivered`를 확인했습니다. DB에는 같은 날 보고서별 발송 기록 12개가 있습니다. 새 `mailing_deliveries`가 비어 있다는 이유로 전체 메일이 꺼져 있다고 판단하면 안 됩니다. 새 Worker는 여전히 OFF이며 대기열 5개가 있습니다. 지금 확인된 키/기록에서는 매일 동일 메일을 반복했다는 증거가 없습니다.

1. **맥 운영에 적용:** LaunchAgent `com.chokemonitor.policy-mac`를 설치했습니다. 30초 heartbeat, active task, Congress/RSS 마지막 성공 시각, 원자재 실패 이유를 기록합니다. 재로그인 시 시작하고 비정상 종료는 60초 간격으로 재시도합니다. STOP는 재시작을 막습니다. 죽은 PID의 잠금만 복구하며, 실제 작업 프로세스에도 잠금을 두어 supervisor가 죽어도 살아 있는 작업과 겹치지 않습니다. 정상 대기 중 프로세스를 한 번 강제 종료하는 시험에서 새 PID로 복구하고 다음 예약 `2026-10-05T04:59:39.989Z`를 보존했습니다. 최초 LaunchAgent의 Documents 작업 경로 초기화 오류는 홈에서 시작하고 수집기 자체가 비공개 로그를 여는 방식으로 해결했습니다. 맥이 꺼지거나 덮개를 닫아 시스템이 잠들면 수집은 지연됩니다.
2. **발송 코드 보강, 운영 전환은 별도:** 기존 sender는 사용자마다 공급자 접수 ID를 확인한 직후 발송 기록을 저장하며, 수신자/보고서 집합의 해시를 Resend idempotency key로 전달합니다. 뒤 사용자의 실패가 앞 사용자의 발송 기록을 잃게 하는 문제를 막았습니다. 공급자 키 보존 기간은 24시간이며 영구 중복 방지는 DB 보고서별 기록에 의존합니다. 실제 전환은 위의 기존 sender 종료 → 새 sender 활성화 절차를 따릅니다. 이번 작업에서 새 메일을 보내거나 sender 설정을 바꾸지 않았습니다.
3. **10/7 검토용 UI 수정:** 고정 `매일 11:17` 보장 문구를 없애고 `수신 설정 켜짐`으로 표시합니다. 주간 08:00은 예약 시각이며 지연 가능성을 밝힙니다. 클릭→저장→재로그인/새로고침→마이페이지 실제 화면 검증은 사이트가 로그아웃 상태여서 사용자 로그인 대기입니다. Auth/마이페이지 관련 회귀 검증은 통과했습니다. Supabase 관리자 로그인과 사이트 로그인이 다릅니다.
4. **RSS 품질:** 수집 실패, 이전 자료 보존, 발행일 미확인, 주제 미분류를 구분합니다. 시간 초과/종료 신호/런타임 미설치를 구별해 로그에 남깁니다. 맥 비공개 `rss-quality.json`과 DB `data_sync_state.sync_resource='mailing:reports:mac'`에 보관 품질을 기록합니다. DB 건강 기록은 다음 RSS 실행부터 생성되며 이번에 과거 성공을 새 성공으로 기록하지 않았습니다. 새 `/api/us/reports/quality`는 화이트리스트 집계/시각만 반환합니다. UI는 맥 DB 보관 상태와 웹에 게시된 RSS 파일 상태를 구분하고 12시간 넘은 게시 자료는 지연으로 표시합니다. 실패·미확인은 기관 미발행을 의미하지 않습니다. 새 수집기에서도 발행일/주제가 불명확한 문서를 임의로 주간 메일에 포함하지 않습니다.
5. **표결/임베딩:** 절차 표결의 부결 안내에 공식 Senate/Congress/House 근거 링크를 추가했습니다. 기존 일반 규칙을 유지하며 CLARITY만 별도로 하드코딩하지 않습니다. Congress 수집기는 실제 임베딩 입력(같은 6,000자 제한)의 SHA-256·모델·차원을 기록하고 갱신 대기를 다음 동기화에서도 보존합니다. API는 `current/stale/unknown/not_embedded`만 공개하며 벡터/원본/입력 해시는 전달하지 않습니다. 기존 벡터에 입력 이력이 없으면 최신성을 미확인으로 표시합니다. 이 변경은 전체 과거 법안의 재임베딩을 자동으로 돌리지 않습니다.

운영 맥 코드 커밋: `c2b901cc`, `e4dfaa67`. 기존 체크포인트/수정 전 파일 백업은 `/Users/yeoninair/Documents/policy-downloads/mac-20260930/backups/mailing-20261005`, 복구 시험 기록은 그 아래 `recovery-proof.json`입니다. 비밀 환경 파일과 키는 백업·커밋에 포함하지 않았습니다. launchd 초기 진단은 `/tmp/chokemonitor-policy-launch.log`, 정상 수집 기록은 기존 `runner.log`입니다.

검증: 서비스 메일 46, 후속 DB 7·보관 5, 정책/UI/품질/잠금/재개/검색 계약 59 테스트, RSS 배포 준비 트리 79·운영 맥 트리 66 테스트 통과. Worker esbuild 번들 통과. 새 잠금 경쟁 시험은 실제 두 프로세스 중 하나만 실행되는지와 supervisor 없이 살아 있는 작업 잠금을 검증합니다. 사이트 배포/실제 클릭/새 sender 수신함 검증은 이 테스트 숫자와 구분합니다.

## 맥 수집 제어

서비스는 아래 체크아웃을 실행합니다. 기존 foreground 실행기를 별도로 다시 켜지 않습니다.

```sh
cd /Users/yeoninair/Documents/policy-mac-handoff-20260930
# 상태 조회
cat /Users/yeoninair/Documents/policy-downloads/mac-20260930/status.json
# 상태가 대기 중인지 확인한 후 서비스 설정을 재등록할 때만
/opt/miniconda3/bin/python3 scripts/install-policy-mac-service.py
```

중지 요청 시 기존 STOP 경로를 사용하면 실행기가 정상 종료하며 launchd는 성공 종료를 반복 재시작하지 않습니다. 재개 요청이 명시적으로 있을 때만 STOP를 제거하고 `launchctl kickstart gui/$(id -u)/com.chokemonitor.policy-mac`로 같은 서비스를 시작합니다. 재부팅 후 자동 실행은 사용자 로그인 이후입니다. 판단할 수 없는 잠금 소유자나 recovery mutex는 임의 삭제하지 말고 실제 프로세스를 확인합니다.

자료: [Resend idempotency keys](https://resend.com/docs/dashboard/emails/idempotency-keys).
