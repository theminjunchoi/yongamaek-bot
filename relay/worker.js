// CGV 예매 API 중계 Worker (https://cgv-relay.yongamaek.workers.dev).
// 2026-09-17부터 CGV가 GitHub Actions 러너 IP를 전부 403으로 막아, 러너 → 이 Worker → CGV로 돌린다.
// 토큰이 맞고 /api/v1/booking/ 경로일 때만 전달해 공개 프록시로 악용되지 않게 한다.
// 배포: cd relay && npx wrangler deploy / 토큰: npx wrangler secret put RELAY_TOKEN
//       (같은 값을 GitHub Secret CGV_RELAY_TOKEN에도 넣는다)
export default {
  async fetch(request, env) {
    if (request.headers.get("X-Relay-Token") !== env.RELAY_TOKEN) {
      return new Response("forbidden", { status: 403 });
    }
    const url = new URL(request.url);
    if (!url.pathname.startsWith("/api/v1/booking/")) {
      return new Response("not found", { status: 404 });
    }
    const upstream = await fetch("https://cgv.co.kr" + url.pathname + url.search, {
      headers: {
        "User-Agent": request.headers.get("User-Agent") || "",
        "Referer": request.headers.get("Referer") || "https://cgv.co.kr/cnm/movieBook/cinema",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9",
      },
    });
    const body = await upstream.arrayBuffer();
    return new Response(body, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("Content-Type") || "application/json" },
    });
  },
};
