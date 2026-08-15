<div align="center">

# 🐉 용아맥 알림 봇

**CGV 용산아이파크몰 IMAX 예매가 열리는 순간, 그리고 명당 취소표가 나오는 순간, 60초 안에 폰으로.**

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
![Discord](https://img.shields.io/badge/Discord-Webhook%20%2B%20Bot-5865F2?logo=discord&logoColor=white)
![Hosting](https://img.shields.io/badge/Hosting-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white)

</div>

용아맥은 매니저 재량으로 예매가 불규칙하게 열려 오픈 타이밍을 예측할 수 없고, 한번 열리면 좋은 자리는 순식간에 매진됩니다. 이 봇은 CGV 스케줄을 상시 감시하다가 **새 날짜의 IMAX 예매가 열리는 순간**과 **명당(H\~L열 16\~29번) 취소표가 나오는 순간**을 Discord로 알립니다.

## 기능

### 신규 날짜 오픈 알림
- ⚡ 새 날짜 오픈을 **60초 내 감지** (GitHub Actions 장시간 잡 체이닝, 서버비 0원)
- 🎬 **영화별 채널 알림** — 보고 싶은 영화 채널만 알림을 켜면 구독 끝
- 🖼 알림에 **영화 포스터** 첨부 (무인증 CGV CDN)
- 📱 알림 탭 한 번에 **영화·날짜가 선택된 CGV 앱 예매 화면**으로 이동
- 📖 오픈 감지 이벤트를 `state/openings.jsonl`에 축적 (요일·시각 패턴 분석용)

### 명당 취소표 알림
- 💺 **좌석 단위 감지** — 어느 자리가 풀렸는지 `J23`처럼 정확히 알려줌
- 🔗 **연석 표기** — 나란한 좌석이 함께 풀리면 `J23~J24 (2연석)`으로 한 번에 묶어서 알림
- ⏱ 아직 **예매 가능한 회차**(판매종료 `salEndTm` 이전)만 대상
- 🪶 **게이트 방식**이라 요청이 거의 안 늘어남 (아래 [동작 원리](#명당-취소표-감지-원리))

### 공통
- 🎭 서버 입장 시 읽기 전용 `관객` 역할 자동 부여
- 🚨 봇 내부 장애·Actions 잡 실패 모두 `#장애_알림`으로 경고

## 구조

```
src/
├── main.py                        # 엔트리포인트 (의존성 조립)
├── domain/
│   ├── models.py                  # Screening (회차) — 예매 마감 시각·심야 회차 시각 계산 포함
│   ├── seat.py                    # Seat, SeatZone/RowRangeZone (명당 정의), 연석 묶기
│   ├── cancellation.py            # 취소표 감지 이벤트
│   └── config.py                  # 환경변수 파싱
├── sources/
│   ├── schedule_source.py         # 스케줄 소스 ABC
│   ├── cgv_http_source.py         # 회차 목록 API 클라이언트
│   ├── seat_source.py             # 좌석맵 소스 ABC
│   ├── cgv_seat_source.py         # 좌석맵 API 클라이언트
│   └── imax_filter.py             # IMAX 회차 판별
├── monitor/
│   ├── app.py                     # MonitorApp(극장 1개) + MonitorCoordinator
│   ├── detector.py                # 영화×날짜 diff로 신규 오픈 감지
│   ├── snapshot_store.py          # 오픈 스냅샷 영속화
│   ├── cancel_watcher.py          # 명당 취소표 감시 (게이트 + 롤링 스윕)
│   ├── cancel_detector.py         # 좌석 diff로 신규 가용 좌석 감지
│   ├── seat_snapshot_store.py     # 회차별 좌석 관측 상태 영속화
│   └── backoff.py                 # 실패 시 지수 백오프
├── notify/
│   ├── notifier.py                # 오픈 알림 ABC
│   ├── routing_notifier.py        # 영화별 채널 라우팅
│   ├── discord_notifier.py        # 오픈 알림 embed
│   ├── cancel_notifier.py         # 취소 알림 ABC
│   ├── routing_cancel_notifier.py # 영화별 취소 채널 라우팅
│   ├── discord_cancel_notifier.py # 취소 알림 embed
│   ├── discord_webhook.py         # 웹훅 POST 저수준 헬퍼
│   ├── booking_link.py            # CGV 앱 직행 딥링크 생성
│   ├── routes.py                  # 극장·영화 → 채널 웹훅 라우팅 설정
│   └── pattern_logger.py          # 오픈 패턴 기록
└── bot/
    └── member_bot.py              # 관객 역할 자동 부여 봇
```

## 명당 취소표 감지 원리

취소표 알림이 붙기 전, 이 봇은 스케줄 조회만으로 **분당 4\~5건**을 요청했습니다. 그런데 좌석맵은 회차당 약 36KB(gzip)라, 열려 있는 58개 회차를 매분 전수 조회하면 **분당 58건** — 열 배가 넘습니다. CGV 서버가 못 버텨서가 아니라 **WAF에 찍혀 러너 IP가 차단되면 봇 전체가 죽기 때문에** 그렇게 하지 않습니다. 대신:

1. **게이트** — 스케줄 API 1요청이 그 날짜 전 회차의 잔여석(`frSeatCnt`)을 통째로 줍니다. 오픈 감지가 이미 받아오는 데이터라 추가 요청이 0건입니다. 잔여석이 직전 사이클과 **달라진 회차만** 좌석맵을 조회합니다.
2. **롤링 스윕** — 게이트만으로는 "같은 사이클 안에 취소 +1과 구매 −1이 상쇄"된 경우를 놓치므로, 매 사이클 6회차씩 순번대로 좌석맵을 갈아봅니다(약 10분이면 전 회차 순회).
3. **기준선** — 처음 보는 회차는 기록만 하고 알리지 않습니다. 예매가 갓 열린 날짜는 명당이 통째로 비어 있어서, 알렸다간 66석이 한꺼번에 취소표로 둔갑합니다.

결과적으로 요청은 **분당 약 20건**입니다. 전수 조회(58건)의 3분의 1이면서, 감지 성능은 사실상 같습니다. Actions 러너에서 실측한 사이클 소요는 60초 중 **35초**입니다.

### 좌석 상태 코드 (2026-08-16 실측)

| `seatStusCd` | `seatSaleYn` | 의미 |
|---|---|---|
| `01` 판매 | N | 이미 팔린 좌석 |
| `00` 미정 | **Y** | **예매 가능** ← 잔여석 |
| `00` 미정 | N | 상시 차단석 (용아맥 K16\~K19) |
| `04` 진행 | N | 결제 진행 중 임시 점유 |

예매 가능 판별은 `seatSaleYn == "Y"` 하나뿐입니다. 이 개수가 스케줄 API의 `frSeatCnt`와 58/58 회차에서 일치함을 확인했습니다.

명당 H\~L열 16\~29번은 70석이지만 K16\~K19 4석이 상시 차단석이라 실제 감시 대상은 **66석**입니다.

## 실행

```bash
python3 -m src.main --once           # 1회 조회: 현재 열린 IMAX 회차 확인
python3 -m src.main --once --seats    # 위 + 회차별 명당 좌석 현황 (회차당 1요청)
cp routes.json.example routes.json && python3 -m src.main   # 상시 감시
```

Python 3.9+, 폴러는 표준 라이브러리만 사용. 운영은 GitHub Actions (`ROUTES_JSON`·`DISCORD_BOT_TOKEN`·`ALERT_WEBHOOK_URL` Secret 필요).

새 영화를 추가하려면 `routes.json`의 `routes`에 항목을 넣고 `gh secret set ROUTES_JSON < routes.json`을 실행합니다. `webhook_url`은 신규 오픈 채널, `cancel_webhook_url`은 취소표 채널이며 후자를 비우면 그 영화는 취소표를 감시하지 않습니다.

명당 구역은 `routes.json`의 극장별 `honey_zone`(`rows`·`min_seat_no`·`max_seat_no`)으로 바꿀 수 있고, 생략하면 용아맥 기본값을 씁니다.

## 진단

```bash
gh workflow run probe   # 러너 IP에서 스케줄·좌석맵 API가 통하는지, 1분 사이클이 60초 안에 끝나는지 실측
```

## 주의

- HTTP 클라이언트는 반드시 `urllib` — Cloudflare가 curl 등 비브라우저 TLS 핑거프린트를 차단 (2026-08 실측)
- 클라우드 VM(Oracle 등) 직접 폴링 불가 — CGV가 데이터센터 IP를 하드 차단. GitHub Actions 러너 IP는 통과
- 좌석맵 조회는 `Accept-Encoding: gzip` 필수 — 원본이 회차당 약 540KB이고 gzip으로 36KB가 됩니다
- 취소표는 몇 초 만에 선점될 수 있습니다. 이 봇은 "알림을 가장 먼저 받는 것"까지만 보장합니다
