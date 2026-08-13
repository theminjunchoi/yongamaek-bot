#!/usr/bin/env bash
# VM에서 1회 실행하는 셋업 스크립트.
# 사전 조건: /opt/yongamaek-bot 에 코드(routes.json 포함)가 복사되어 있어야 한다.
set -euo pipefail

RUN_USER="${1:?사용법: setup.sh <실행 사용자 (ubuntu 또는 opc)>}"

# Python 3.9+ 설치 (Ubuntu: apt / Oracle Linux: dnf)
if command -v apt-get >/dev/null; then
    sudo apt-get update -y && sudo apt-get install -y python3
elif command -v dnf >/dev/null; then
    sudo dnf install -y python3
fi

python3 - <<'EOF'
import sys
assert sys.version_info >= (3, 9), f"Python 3.9+ 필요, 현재 {sys.version}"
EOF

sudo chown -R "$RUN_USER":"$RUN_USER" /opt/yongamaek-bot

# systemd 등록 (User=%i 템플릿에 실행 사용자 주입)
sudo cp /opt/yongamaek-bot/deploy/yongamaek-bot.service /etc/systemd/system/yongamaek-bot@.service
sudo systemctl daemon-reload
sudo systemctl enable --now "yongamaek-bot@${RUN_USER}"
sudo systemctl status "yongamaek-bot@${RUN_USER}" --no-pager
