"""러너 IP에서 좌석맵 API(searchIfSeatData)가 무인증으로 통하는지 진단한다.

명당석 취소표 알림 기능의 전제 조건 검증용. 로컬(맥)에서는 통하지만
CGV WAF는 IP 대역별로 다르게 반응하므로 러너에서 별도 확인이 필요하다.
"""

import datetime
import gzip
import json
import time
import urllib.parse
import urllib.request

BASE = "https://cgv.co.kr/api/v1/booking/"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)
SITE_NO = "0013"  # 용산아이파크몰
SCNS_NO = "018"  # IMAX관
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
    started = time.time()
    with urllib.request.urlopen(request, timeout=25) as response:
        raw = response.read()
        wire = len(raw)
        elapsed = time.time() - started
        if response.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return json.loads(raw.decode("utf-8")), wire, elapsed


def is_honey(seat: dict) -> bool:
    return seat["seatRowNm"] in HONEY_ROWS and 16 <= int(seat["seatNo"]) <= 29


def main() -> int:
    today = datetime.date.today()
    target = None
    for offset in range(1, 8):
        date = (today + datetime.timedelta(days=offset)).strftime("%Y%m%d")
        payload, _, _ = get(
            "searchMovScnInfo",
            {"coCd": "A420", "siteNo": SITE_NO, "scnYmd": date, "rtctlScopCd": "08"},
            "https://cgv.co.kr/cnm/movieBook/cinema",
        )
        imax = [r for r in (payload.get("data") or []) if str(r.get("tcscnsGradCd")) == "03"]
        if imax:
            target = (date, imax[0])
            break
        time.sleep(1)

    if target is None:
        print("진단 불가: 향후 7일 내 IMAX 회차 없음")
        return 1

    date, row = target
    print(f"대상 회차: {date} 회차{row['scnSseq']} {row['scnsrtTm']} "
          f"{row['movNm']} 잔여 {row['frSeatCnt']}/{row['stcnt']}")

    # 좌석맵 5회 연속 조회 — 러너 IP에서 레이트 리밋/차단이 걸리는지 확인
    for attempt in range(1, 6):
        payload, wire, elapsed = get(
            "searchIfSeatData",
            {
                "coCd": "A420",
                "siteNo": SITE_NO,
                "scnYmd": date,
                "scnsNo": SCNS_NO,
                "scnSseq": row["scnSseq"],
            },
            "https://cgv.co.kr/cnm/bookMovie/chooseSeatMyself",
        )
        seats = payload["data"]["items"][0]["seats"]
        available = [s for s in seats if s["seatSaleYn"] == "Y"]
        honey = [s for s in available if is_honey(s)]
        print(
            f"  {attempt}회차 조회 OK: statusCode={payload['statusCode']} "
            f"좌석 {len(seats)}석 / 가용 {len(available)}석 / 명당 {len(honey)}석 "
            f"| gzip {wire / 1024:.1f}KB {elapsed * 1000:.0f}ms"
        )
        if attempt == 1:
            print(f"     frSeatCnt({row['frSeatCnt']}) == 좌석맵 가용수({len(available)}): "
                  f"{int(row['frSeatCnt']) == len(available)}")
        time.sleep(1)

    print("결론: 러너 IP에서 좌석맵 API 무인증 접근 가능")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
