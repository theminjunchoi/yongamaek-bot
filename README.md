# 용아맥 알림 봇

CGV 용산아이파크몰 IMAX관(용아맥) 예매가 열리는 순간 Discord로 알림을 보내는 봇.

CGV 스케줄 API를 짧은 주기로 폴링해서 **새 날짜(또는 새 영화)의 IMAX 예매 오픈**을
감지하면, 그 영화의 전용 채널 웹훅으로 날짜·상영시간·잔여석·예매 링크를 발송한다.
이미 열린 날짜에 같은 영화의 회차가 추가되는 것은 알리지 않는다.

## 영화별 채널 구독

영화마다 Discord 채널을 만들고(`#오디세이-알림`, `#스파이더맨-알림`, …) 각 채널의
웹훅을 `routes.json`에 등록한다. 사용자는 보고 싶은 영화 채널의 알림만 켜면 된다.
라우트에 없는 새 영화가 열리면 `fallback_webhook_url` 채널로 알림이 가므로,
거기서 보고 새 채널을 만들어 라우트에 추가하면 된다.

```bash
cp routes.json.example routes.json  # 채널별 웹훅 URL 채우기
```

`routes.json`이 없으면 `.env`의 `DISCORD_WEBHOOK_URL` 단일 채널 모드로 동작한다.

## 실행

```bash
# 1회 조회: 현재 열려있는 IMAX 회차 확인 (웹훅 불필요)
python3 -m src.main --once

# 상시 감시
python3 -m src.main
```

Python 3.9+ / 외부 의존성 없음.

## 설정 (.env)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `ROUTES_PATH` | `routes.json` | 영화별 채널 라우팅 설정 경로 |
| `DISCORD_WEBHOOK_URL` | — | 단일 채널 모드용 웹훅 (routes.json 없을 때만 사용) |
| `CGV_SITE_NO` | `0013` | 극장 코드 (용산아이파크몰) |
| `POLL_INTERVAL_SEC` | `60` | 폴링 간격(초) |
| `NIGHT_POLL_INTERVAL_SEC` | `300` | 심야(KST 01~07시) 폴링 간격 |
| `DAYS_AHEAD` | `14` | 오늘부터 조회할 일수 |
| `SNAPSHOT_PATH` | `state/snapshot.json` | 알림 완료 회차 저장 경로 |

## 구조

`ScheduleSource`(데이터 소스)와 `Notifier`(알림 채널)가 추상 인터페이스라,
CGV가 API를 막으면 Playwright 구현을, 새 알림 방식이 필요하면 Notifier 구현을
추가하는 것으로 기존 코드 수정 없이 확장한다.

```
src/
├── main.py               # 엔트리포인트: 설정 로드 → 의존성 조립
├── app.py                # MonitorApp — 폴링 루프 오케스트레이션
├── config.py             # Config — 환경변수 파싱
├── models.py             # Screening — 회차 도메인 모델
├── schedule_source.py    # ScheduleSource(ABC) ← 확장점
├── cgv_http_source.py    # urllib 기반 CGV BFF API 구현
├── imax_filter.py        # IMAX 회차 판별
├── snapshot_store.py     # 알림 완료 키 집합 영속화
├── detector.py           # 스냅샷 diff로 신규 오픈 감지
├── notifier.py           # Notifier(ABC) ← 확장점
├── discord_notifier.py   # Discord 웹훅 embed 발송
├── routes.py             # 영화 → 채널 웹훅 라우팅 테이블
├── routing_notifier.py   # 영화별 채널로 알림 분배
└── backoff.py            # 연속 실패 시 지수 백오프
```

## 운영 (GitHub Actions)

`.github/workflows/poller.yml`이 24시간 감시를 담당한다: 30분 cron이 잡을 큐잉하되
concurrency 그룹으로 동시 실행을 막아, 5시간 20분짜리 폴링 잡이 끝나면 대기 잡이
즉시 이어받는다 (평상시 알림 지연 = 폴링 간격 60초, 잡 교체 시에만 ~1분 공백).

- 웹훅 URL은 레포 Secret `ROUTES_JSON`(routes.json 전체 내용)으로 주입
- `state/snapshot.json`은 잡 종료 시 커밋되어 잡 간 연속성을 유지
- Oracle 등 클라우드 VM 직접 폴링은 불가 — CGV가 데이터센터 IP 대역을 WAF에서
  하드 차단한다 (2026-08 실측, GitHub Actions 러너 IP는 통과)

## 동작 규칙

- 알림 단위는 **영화×날짜**: 새 날짜가 열리거나, 열린 날짜에 새 영화가 편성되면 알린다.
  이미 열린 영화×날짜에 회차만 추가되는 것은 무시한다
- 첫 실행(스냅샷 없음)은 알림 없이 스냅샷만 구축한다
- 알림 발송에 성공한 오픈만 스냅샷에 기록한다 (실패 시 다음 사이클에 재시도)
- 조회 실패가 연속되면 지수 백오프(최대 30분), 5회 연속 실패 시 장애 경고를 1회 발송한다
- 상영일이 지난 키는 자동 정리한다

## 주의

- HTTP 클라이언트는 반드시 `urllib` 사용 — Cloudflare가 curl 등 비브라우저 TLS 핑거프린트를 차단한다 (2026-08 실측)
- `User-Agent`와 `Referer: https://cgv.co.kr/cnm/movieBook/cinema` 헤더가 없으면 403
- macOS에서는 **Homebrew Python**으로 실행할 것 — Xcode 내장 Python(`/usr/bin/python3`)은 TLS 스택 차이로 CGV API에서 전부 403이 난다 (2026-08 실측)
