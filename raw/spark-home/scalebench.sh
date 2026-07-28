#!/bin/bash
BIN="$1"; NAME="$2"; PORT="$3"; OUT="$4"; D=/tmp/sc_$NAME; rm -rf $D; mkdir -p $D/data $D/tmp
ulimit -n 500000
cat > $D/config.xml <<XML
<clickhouse>
 <logger><level>error</level><log>$D/s.log</log></logger>
 <tcp_port>$PORT</tcp_port><path>$D/data/</path><tmp_path>$D/tmp/</tmp_path>
 <user_directories><users_xml><path>$D/u.xml</path></users_xml></user_directories>
 <listen_host>127.0.0.1</listen_host><max_connections>40000</max_connections><max_concurrent_queries>0</max_concurrent_queries>
</clickhouse>
XML
echo "<clickhouse><users><default><password></password><networks><ip>::/0</ip></networks><profile>default</profile><quota>default</quota></default></users><profiles><default/></profiles><quotas><default/></quotas></clickhouse>" > $D/u.xml
$BIN server --config-file=$D/config.xml >$D/boot.log 2>&1 & SRV=$!
for i in $(seq 1 40); do $BIN client --port $PORT -q "SELECT 1" >/dev/null 2>&1 && break; sleep 1; done
base=$(awk '/VmRSS/{print int($2/1024)}' /proc/$SRV/status)
echo "[$NAME] idle RSS: ${base}MB" >> $OUT
for C in 10 100 1000 10000; do
  : > $D/rss_$C
  ( while kill -0 $SRV 2>/dev/null; do awk '/VmRSS/{print int($2/1024)}' /proc/$SRV/status 2>/dev/null; sleep 0.1; done > $D/rss_$C ) & SP=$!
  res=$($BIN benchmark --port $PORT --concurrency $C --timelimit 8 --query "SELECT 1" 2>&1)
  kill $SP 2>/dev/null; sleep 0.2
  qps=$(echo "$res" | grep -oE 'QPS: [0-9.]+' | head -1 | awk '{print $2}')
  pk=$(sort -rn $D/rss_$C 2>/dev/null | head -1)
  printf "[%s] clients=%-6s QPS=%-10s peakRSS=%sMB  Δvs-idle=%sMB  per-conn=%.1fKB\n" "$NAME" "$C" "${qps:-ERR}" "${pk:-?}" "$((${pk:-0}-base))" "$(awk -v p=${pk:-0} -v b=$base -v c=$C 'BEGIN{printf (p-b)*1024.0/c}')" >> $OUT
done
kill -9 $SRV 2>/dev/null
echo "[$NAME] SCALEDONE" >> $OUT
