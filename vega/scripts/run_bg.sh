#!/usr/bin/env bash
# Run a VEGA job detached from the agent session, low priority, logged, resumable by design.
# usage: scripts/run_bg.sh <name> <command...>
set -euo pipefail
cd "$(dirname "$0")/.."
name="$1"; shift
for p in /home/ubuntu/nextgen-market-lab /home/ubuntu/worktrees/nova-v2-evolution \
         /home/ubuntu/worktrees/nova-v3-evolution /home/ubuntu/bot-nextgen; do
  case "$*" in *"$p"*) echo "refusing: command references protected path $p" >&2; exit 2;; esac
done
mkdir -p logs
setsid nohup nice -n 10 ionice -c3 "$@" > "logs/$name.log" 2>&1 < /dev/null &
echo $! > "logs/$name.pid"
echo "started $name pid $(cat logs/$name.pid) log logs/$name.log"
