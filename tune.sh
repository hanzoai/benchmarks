#!/usr/bin/env bash
# Network-stack tuning for max small-request req/sec. Run on the server AND every
# loader box. Idempotent; needs sudo. Usage: sudo ./tune.sh <nic>
#   sudo ./tune.sh enP7s7     # spark (server, 2.5GbE)
#   sudo ./tune.sh eno1       # evo    (loader, 2.5GbE)
set -uo pipefail
NIC=${1:-$(ip route get 8.8.8.8 2>/dev/null | awk '{print $5; exit}')}
NC=$(nproc)
MASK=$(printf '%x' $(( (1<<NC) - 1 )))
echo ">> tuning $(hostname) nic=$NIC cores=$NC"

# 1) CPU: performance governor on every core
for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do echo performance > "$g" 2>/dev/null; done

# 2) NIC ring buffers -> hardware max (evo ships at 256; drops under load)
RXMAX=$(ethtool -g "$NIC" 2>/dev/null | awk '/Pre-set maximums/{p=1} p&&/^RX:/{print $2; exit}')
TXMAX=$(ethtool -g "$NIC" 2>/dev/null | awk '/Pre-set maximums/{p=1} p&&/^TX:/{print $2; exit}')
[ -n "${RXMAX:-}" ] && ethtool -G "$NIC" rx "$RXMAX" tx "${TXMAX:-$RXMAX}" 2>/dev/null && echo "  ring -> rx=$RXMAX tx=${TXMAX:-$RXMAX}"

# 3) Offloads on (throughput)
ethtool -K "$NIC" gro on gso on tso on 2>/dev/null || true

# 4) RPS (RX softirq across all cores — this NIC has 1 hw queue) + RFS + XPS (TX)
sysctl -qw net.core.rps_sock_flow_entries=1048576 2>/dev/null
for q in /sys/class/net/$NIC/queues/rx-*; do echo "$MASK" > "$q/rps_cpus" 2>/dev/null; echo 65536 > "$q/rps_flow_cnt" 2>/dev/null; done
for q in /sys/class/net/$NIC/queues/tx-*; do echo "$MASK" > "$q/xps_cpus" 2>/dev/null; done

# 5) Kernel network sysctls (big buffers, deep backlog, wide ports, fast recycle)
sysctl -qw \
  net.core.rmem_max=268435456 net.core.wmem_max=268435456 \
  net.core.rmem_default=16777216 net.core.wmem_default=16777216 \
  net.core.optmem_max=65536 \
  net.core.netdev_max_backlog=300000 net.core.netdev_budget=60000 net.core.netdev_budget_usecs=8000 \
  net.core.somaxconn=65535 net.core.busy_read=0 net.core.busy_poll=0 \
  net.ipv4.tcp_rmem="4096 262144 268435456" net.ipv4.tcp_wmem="4096 262144 268435456" \
  net.ipv4.tcp_max_syn_backlog=65535 net.ipv4.tcp_tw_reuse=1 net.ipv4.tcp_fin_timeout=10 \
  net.ipv4.ip_local_port_range="1024 65535" net.ipv4.tcp_mtu_probing=1 \
  net.ipv4.tcp_slow_start_after_idle=0 net.ipv4.tcp_no_metrics_save=1 2>/dev/null

echo ">> done: gov=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor) ring_rx=$(ethtool -g $NIC 2>/dev/null | awk '/Current hardware/{c=1} c&&/^RX:/{print $2; exit}') backlog=$(sysctl -n net.core.netdev_max_backlog) somaxconn=$(sysctl -n net.core.somaxconn)"
