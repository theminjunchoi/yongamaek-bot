<div align="center">

# 🐉 용아맥 알림 봇

**CGV 용산아이파크몰 IMAX 예매가 열리는 순간, 60초 안에 폰으로.**

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
![Discord](https://img.shields.io/badge/Discord-Webhook%20%2B%20Bot-5865F2?logo=discord&logoColor=white)
![Hosting](https://img.shields.io/badge/Hosting-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white)

</div>

용아맥은 매니저 재량으로 예매가 불규칙하게 열려 오픈 타이밍을 예측할 수 없습니다. 이 봇은 CGV 스케줄을 상시 감시하다가 **새 날짜의 IMAX 예매가 열리는 순간** Discord 채널로 푸시 알림을 보냅니다.

## 기능

- ⚡ 새 날짜 오픈을 **60초 내 감지** (GitHub Actions 장시간 잡 체이닝, 서버비 0원)
- 🎬 **영화별 채널 알림** — 보고 싶은 영화 채널만 알림을 켜면 구독 끝
- 📱 알림 탭 한 번에 **영화·날짜가 선택된 CGV 앱 예매 화면**으로 이동
- 🎭 서버 입장 시 읽기 전용 `관객` 역할 자동 부여
- 📖 오픈 감지 이벤트를 `state/openings.jsonl`에 축적 (오픈 요일·시각 패턴 분석용)
- 🚨 봇 내부 장애·Actions 잡 실패 모두 `#장애_알림`으로 경고

## 구조

```
src/
├── main.py               # 엔트리포인트 (의존성 조립)
├── app.py                # 폴링 루프 오케스트레이션
├── cgv_http_source.py    # CGV API 클라이언트 (ScheduleSource 구현)
├── imax_filter.py        # IMAX 회차 판별
├── detector.py           # 영화×날짜 스냅샷 diff로 신규 오픈 감지
├── routing_notifier.py   # 영화별 채널 라우팅 (Notifier 구현)
├── booking_link.py       # CGV 앱 직행 딥링크 생성
├── pattern_logger.py     # 오픈 패턴 기록
└── member_bot.py         # 관객 역할 자동 부여 봇
```

## 실행

```bash
python3 -m src.main --once   # 1회 조회: 현재 열린 IMAX 회차 확인
cp routes.json.example routes.json && python3 -m src.main   # 상시 감시
```

Python 3.9+, 폴러는 표준 라이브러리만 사용. 운영은 GitHub Actions (`ROUTES_JSON`·`DISCORD_BOT_TOKEN`·`ALERT_WEBHOOK_URL` Secret 필요). 새 영화 채널은 `ROUTES_JSON`에 웹훅 항목만 추가하면 됩니다.

## 주의

- HTTP 클라이언트는 반드시 `urllib` — Cloudflare가 curl 등 비브라우저 TLS 핑거프린트를 차단 (2026-08 실측)
- 클라우드 VM(Oracle 등) 직접 폴링 불가 — CGV가 데이터센터 IP를 하드 차단. GitHub Actions 러너 IP는 통과
