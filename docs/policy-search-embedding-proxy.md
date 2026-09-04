# 정책 검색용 Gemini 임베딩 프록시

## 왜 필요한가

정책 검색 API는 질의어를 `gemini-embedding-001`의 1,536차원
`RETRIEVAL_QUERY` 벡터로 바꾼 뒤 Supabase의 `search_policy_corpus` RPC를 호출한다.
Cloudflare Worker에서 Gemini를 직접 호출하면 Worker의 실행 리전이 Gemini API
지원 지역으로 판정되지 않아 400 오류가 날 수 있다. 이 서비스는 미국 리전의
Cloud Run에서 그 **질의 임베딩 한 번만** 수행한다. 법안·EO·규제 데이터와
Supabase 검색 RPC는 이 서비스가 수정하지 않는다.

## 보안 원칙

- `GEMINI_API_KEY`와 `WORKER_EMBEDDING_PROXY_TOKEN`은 Git·소스·로그에 넣지 않는다.
- 두 값 모두 Google Secret Manager에서 Cloud Run 환경으로 주입한다.
- Cloud Run은 Cloudflare가 호출할 수 있도록 네트워크상 공개될 수 있으나,
  `/embed`는 별도의 긴 Bearer 토큰 없이는 실행되지 않는다.
- 질의어와 임베딩 벡터는 로그에 기록하지 않는다.

## 최초 배포 전 준비

아래 명령은 Google Cloud CLI가 로그인되어 있고, 결제 가능한 Google Cloud 프로젝트가
선택되어 있을 때만 실행한다. 실제 배포는 과금이 생길 수 있으므로 운영자 승인 후에만
수행한다.

```bash
gcloud config set project YOUR_GOOGLE_CLOUD_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com
```

Secret Manager에 다음 두 비밀값을 만든다.

```bash
gcloud secrets create policy-embedding-gemini-key --replication-policy=automatic
gcloud secrets create policy-embedding-proxy-token --replication-policy=automatic
```

그 다음 각 명령을 **한 줄씩** 실행하여 터미널 프롬프트에 실제 값을 안전하게 입력한다.

```bash
gcloud secrets versions add policy-embedding-gemini-key --data-file=-
gcloud secrets versions add policy-embedding-proxy-token --data-file=-
```

Cloud Run의 기본 Compute Engine 서비스 계정에 두 Secret의 `Secret Manager Secret
Accessor` 역할을 준다. Google Cloud 콘솔에서 Secret Manager → 각 Secret → 권한 메뉴로
들어가 실행 서비스 계정을 추가하는 방식이 가장 안전하다.

## Cloud Run 배포

리포지토리 루트에서 실행한다. `us-central1`은 미국 리전 예시이며, Gemini API가
지원하는 리전인지 배포 전 다시 확인한다.

```bash
gcloud run deploy policy-embedding-proxy \
  --source services/policy-embedding-proxy \
  --region us-central1 \
  --allow-unauthenticated \
  --set-secrets GEMINI_API_KEY=policy-embedding-gemini-key:latest,WORKER_EMBEDDING_PROXY_TOKEN=policy-embedding-proxy-token:latest
```

배포가 끝나면 출력되는 Cloud Run URL을 복사한다. `/healthz` 끝점은 204를 반환해야 한다.

## Cloudflare Worker 연결

Cloudflare Dashboard의 Workers & Pages → `global-trade-dashboard` → Settings → Variables
and Secrets에서 아래 두 **Secret**을 추가하고 배포한다.

| 이름 | 값 |
| --- | --- |
| `POLICY_EMBEDDING_PROXY_URL` | Cloud Run URL. 끝의 `/`는 제외 |
| `POLICY_EMBEDDING_PROXY_TOKEN` | Cloud Run에 넣은 것과 완전히 같은 Bearer 토큰 |

기존 `AI_STUDIO_API_KEY`는 로컬 개발 호환성을 위해 남겨도 된다. 운영 검색은 위 프록시
두 값이 모두 있으면 자동으로 프록시를 우선 사용한다.

## 확인 순서

1. Cloud Run URL 뒤에 `/healthz`를 붙여 열고 204 응답을 확인한다.
2. Cloudflare Worker를 재배포한다.
3. 정책 화면에서 `니켈` 또는 `수출통제`를 검색한다.
4. Cloudflare Worker 로그에는 `Gemini ... User location is not supported`가 더 이상
   없어야 한다. 오류가 나더라도 방문자 화면에는 상류 서비스 오류 전문이 노출되지 않는다.
