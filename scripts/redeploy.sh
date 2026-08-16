#!/usr/bin/env bash
# poller를 최신 커밋으로 교체 배포하고, 실제로 폴링이 돌고 있는지 확인한다.
#
# 잡은 5시간 20분짜리라 코드를 push해도 저절로 반영되지 않는다. 돌던 잡을
# 취소하고 새로 띄워야 하는데(취소는 watchdog 경고를 울리지 않는다), 새 잡이
# 시작만 하고 곧바로 죽어도 겉보기엔 in_progress로 보이므로 스텝 상태까지 본다.
set -uo pipefail

WAIT_START=${WAIT_START:-60}   # 새 잡이 뜨기를 기다리는 시간(초)
WAIT_ALIVE=${WAIT_ALIVE:-90}   # 폴링이 죽지 않고 살아있는지 지켜보는 시간(초)

cd "$(dirname "$0")/.." || exit 1

local_sha=$(git rev-parse HEAD)
git fetch -q origin main
if [ "$(git rev-parse origin/main)" != "$local_sha" ]; then
  echo "❌ 원격이 로컬과 다릅니다. 먼저 push 하세요."
  exit 1
fi
echo "배포 대상 커밋: ${local_sha:0:7} $(git log -1 --pretty=%s)"

old_runs=$(gh run list --workflow=poller --limit 10 --json databaseId,status \
  --jq '.[] | select(.status=="in_progress") | .databaseId')

gh workflow run poller || exit 1
echo "새 잡 요청 완료, 기존 잡 취소 중..."
sleep 8
for id in $old_runs; do
  gh run cancel "$id" >/dev/null 2>&1 && echo "  구 잡 취소: $id"
done

# 새 커밋으로 도는 잡이 뜰 때까지 대기
run_id=""
for _ in $(seq 1 $((WAIT_START / 5))); do
  run_id=$(gh run list --workflow=poller --limit 10 --json databaseId,status,headSha \
    --jq ".[] | select(.status==\"in_progress\" and .headSha==\"$local_sha\") | .databaseId" | head -1)
  [ -n "$run_id" ] && break
  sleep 5
done
if [ -z "$run_id" ]; then
  echo "❌ ${WAIT_START}초 안에 새 잡이 시작되지 않았습니다. gh run list로 확인하세요."
  exit 1
fi
echo "새 잡 시작: $run_id (${local_sha:0:7})"

echo "폴링이 살아있는지 ${WAIT_ALIVE}초간 확인..."
sleep "$WAIT_ALIVE"

# conclusion이 빈 문자열이면 탭이 연달아 붙어 read가 필드를 밀어버린다(탭은 IFS 공백류).
# 진행 중 스텝이 바로 그 경우라, 비었으면 "-"로 채운다.
steps=$(gh run view "$run_id" --json jobs \
  --jq '.jobs[].steps[] | "\(.status)\t\(if .conclusion == "" then "-" else .conclusion end)\t\(.name)"')
if [ -z "$steps" ]; then
  echo "❌ 스텝 상태를 읽지 못했습니다."
  exit 1
fi

echo "$steps" | while IFS=$'\t' read -r step_status conclusion name; do
  case "$name" in
    "폴링 + 멤버 봇 실행"*)
      if [ "$step_status" = "in_progress" ]; then
        echo "  ✅ $name — 실행 중 (프로세스 살아있음)"
      else
        echo "  ❌ $name — status=$step_status conclusion=$conclusion (즉시 종료됨)"
      fi
      ;;
    "Set up job"|"Run actions/checkout@v4"|"routes.json 생성"*|"의존성 설치"*)
      if [ "$conclusion" = "success" ]; then
        echo "  ✅ $name"
      else
        echo "  ❌ $name — conclusion=$conclusion"
      fi
      ;;
  esac
done

# 파이프 서브셸 때문에 위 루프의 결과를 다시 판정한다
alive=$(echo "$steps" | grep -c $'^in_progress\t-\t폴링')
setup_fail=$(echo "$steps" | grep -E $'^completed\t(failure|cancelled)\t' | grep -cv '폴링')
if [ "$alive" -eq 1 ] && [ "$setup_fail" -eq 0 ]; then
  echo "✅ 배포 정상 — https://github.com/theminjunchoi/yongamaek-bot/actions/runs/$run_id"
  exit 0
fi
echo "❌ 배포 확인 실패 — https://github.com/theminjunchoi/yongamaek-bot/actions/runs/$run_id"
exit 1
