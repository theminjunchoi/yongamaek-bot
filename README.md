# 용아맥 알림 봇

CGV 용산아이파크몰 IMAX관(용아맥) 예매가 열리는 순간 Discord로 알림을 보내는 봇.

CGV 스케줄 API를 짧은 주기로 폴링해서, 스냅샷에 없던 IMAX 회차가 나타나면
Discord 웹훅으로 영화명·날짜·상영시간·잔여석·예매 링크를 발송한다.

## 실행

```bash
# 1회 조회: 현재 열려있는 IMAX 회차 확인 (웹훅 불필요)
python3 -m src.main --once

# 상시 감시 (.env에 DISCORD_WEBHOOK_URL 필요)
cp .env.example .env  # 웹훅 URL 채우기
python3 -m src.main
```

Python 3.9+ / 외부 의존성 없음.

## 설정 (.env)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | (필수) | Discord 채널 웹훅 URL |
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
└── backoff.py            # 연속 실패 시 지수 백오프
```

## 동작 규칙

- 첫 실행(스냅샷 없음)은 알림 없이 스냅샷만 구축한다
- 알림 발송에 성공한 회차만 스냅샷에 기록한다 (실패 시 다음 사이클에 재시도)
- 조회 실패가 연속되면 지수 백오프(최대 30분), 5회 연속 실패 시 장애 경고를 1회 발송한다
- 상영일이 지난 키는 자동 정리한다

## 주의

- HTTP 클라이언트는 반드시 `urllib` 사용 — Cloudflare가 curl 등 비브라우저 TLS 핑거프린트를 차단한다 (2026-08 실측)
- `User-Agent`와 `Referer: https://cgv.co.kr/cnm/movieBook/cinema` 헤더가 없으면 403
