"""게이트 방식 1분 사이클이 러너에서 60초 안에 끝나는지 실측한다.

한 사이클 = 스케줄 14일 조회(전 회차 frSeatCnt 확보) + 변동 회차 좌석맵 조회.
현행 봇과 동일하게 요청 사이 랜덤 딜레이를 넣고 벽시계 시간을 잰다.
"""

import datetime
import gzip
import json
import random
import time
import urllib.parse
import urllib.request

BASE = "https://cgv.co.kr/api/v1/booking/"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)
SITE_NO = "0013"
SCNS_NO = "018"
DAYS_AHEAD = 14
HONEY_ROWS = set("HIJKL")


def get(endpoint: str, params: dict, referer: str):
    url = BASE + endpoint + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Referer": referer,
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        raw = response.read()
        wire = len(raw)
        if response.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return json.loads(raw.decode("utf-8")), wire


def gate_cycle(delay_min: float, delay_max: float, seatmap_fetches: int):
    """스케줄 풀스캔 + 좌석맵 N회 조회의 벽시계 시간과 전송량을 잰다."""
    started = time.time()
    today = datetime.date.today()
    wire = 0
    requests = 0
    screenings = []

    for offset in range(DAYS_AHEAD):
        if requests:
            time.sleep(random.uniform(delay_min, delay_max))
        date = (today + datetime.timedelta(days=offset)).strftime("%Y%m%d")
        payload, w = get(
            "searchMovScnInfo",
            {"coCd": "A420", "siteNo": SITE_NO, "scnYmd": date, "rtctlScopCd": "08"},
            "https://cgv.co.kr/cnm/movieBook/cinema",
        )
        wire += w
        requests += 1
        for row in payload.get("data") or []:
            if str(row.get("tcscnsGradCd")) == "03":
                screenings.append((date, row["scnSseq"], int(row["frSeatCnt"])))

    sched_elapsed = time.time() - started
    print(f"    스케줄 {requests}요청 / IMAX {len(screenings)}회차 확보 "
          f"| {wire / 1024:.0f}KB | {sched_elapsed:.1f}s")

    honey_total = 0
    for date, sseq, _ in screenings[:seatmap_fetches]:
        time.sleep(random.uniform(delay_min, delay_max))
        payload, w = get(
            "searchIfSeatData",
            {"coCd": "A420", "siteNo": SITE_NO, "scnYmd": date,
             "scnsNo": SCNS_NO, "scnSseq": sseq},
            "https://cgv.co.kr/cnm/bookMovie/chooseSeatMyself",
        )
        wire += w
        requests += 1
        seats = payload["data"]["items"][0]["seats"]
        honey_total += sum(
            1 for s in seats
            if s["seatSaleYn"] == "Y" and s["seatRowNm"] in HONEY_ROWS
            and 16 <= int(s["seatNo"]) <= 29
        )

    total = time.time() - started
    print(f"    + 좌석맵 {seatmap_fetches}회 (명당 가용 {honey_total}석) "
          f"→ 총 {requests}요청 {wire / 1024:.0f}KB")
    print(f"    ▶ 사이클 벽시계 {total:.1f}s / 60s  (여유 {60 - total:+.1f}s)")
    return total


def main() -> int:
    print("[A] 현행 봇과 동일한 딜레이 (1.0~2.0s), 좌석맵 6회")
    gate_cycle(1.0, 2.0, 6)

    print("\n[B] 딜레이 축소 (0.3~0.6s), 좌석맵 6회")
    gate_cycle(0.3, 0.6, 6)

    print("\n[C] 최악 가정 — 딜레이 0.3~0.6s, 좌석맵 20회 동시 변동")
    gate_cycle(0.3, 0.6, 20)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
