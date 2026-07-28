#!/bin/bash
BIN="$1"; NAME="$2"; PORT="$3"; OUT="$4"; D=/tmp/mc_$NAME; rm -rf $D; mkdir -p $D/data $D/tmp
cat > $D/config.xml <<XML
<clickhouse>
    <logger><level>error</level><log>$D/srv.log</log></logger>
    <tcp_port>$PORT</tcp_port>
    <path>$D/data/</path>
    <tmp_path>$D/tmp/</tmp_path>
    <user_directories><users_xml><path>$D/users.xml</path></users_xml></user_directories>
    <mark_cache_size>5368709120</mark_cache_size>
    <listen_host>127.0.0.1</listen_host>
</clickhouse>
XML
cat > $D/users.xml <<XML
<clickhouse><users><default><password></password><networks><ip>::/0</ip></networks><profile>default</profile><quota>default</quota></default></users><profiles><default/></profiles><quotas><default/></quotas></clickhouse>
XML
$BIN server --config-file=$D/config.xml > $D/boot.log 2>&1 &
SRV=$!
up=0; for i in $(seq 1 40); do $BIN client --port $PORT --query "SELECT 1" >/dev/null 2>&1 && { up=1; break; }; kill -0 $SRV 2>/dev/null || break; sleep 1; done
if [ "$up" != 1 ]; then echo "[$NAME] SERVER FAILED TO START:" >> $OUT; grep -aiE "error|exception" $D/srv.log $D/boot.log 2>/dev/null | grep -avE "@ 0x" | head -3 >> $OUT; kill -9 $SRV 2>/dev/null; return 2>/dev/null || exit 1; fi
echo "[$NAME] server up (pid $SRV, port $PORT)" >> $OUT
$BIN client --port $PORT --query "CREATE TABLE bench (id UInt64, user_id UInt32, ts DateTime, value Float64, category LowCardinality(String)) ENGINE=MergeTree ORDER BY (category, ts)" 2>>$OUT
$BIN client --port $PORT --query "INSERT INTO bench SELECT number, rand()%100000, now()-(rand()%2592000), rand()/4294967.0, ['ads','web','api','iot'][(number%4)+1] FROM numbers(10000000)" 2>>$OUT
echo "[$NAME] loaded $($BIN client --port $PORT --query 'SELECT count() FROM bench' 2>/dev/null) rows" >> $OUT
declare -A Q=( [agg]="SELECT category,count(),avg(value) FROM bench GROUP BY category" [topk]="SELECT user_id,sum(value) s FROM bench GROUP BY user_id ORDER BY s DESC LIMIT 10" [filter]="SELECT count() FROM bench WHERE value>0.5 AND category='api'" )
for qn in agg topk filter; do for C in 1 4 16 64; do
  res=$($BIN benchmark --port $PORT --concurrency $C --iterations $((C*20)) --query "${Q[$qn]}" 2>&1)
  qps=$(echo "$res" | grep -oE "QPS: [0-9.]+" | head -1 | awk '{print $2}')
  p50=$(echo "$res" | grep -A30 "0.000%" | grep -oE "50.000%.*sec" | grep -oE "[0-9.]+ sec" | head -1 | awk '{print $1}')
  p99=$(echo "$res" | grep -oE "99.000%.*sec" | grep -oE "[0-9.]+ sec" | head -1 | awk '{print $1}')
  rss=$(awk "/VmRSS/{print \$2}" /proc/$SRV/status 2>/dev/null)
  printf "[%s] %-7s c=%-3d QPS=%-9s p50=%-8ss p99=%-8ss RSS=%sMB\n" "$NAME" "$qn" "$C" "${qps:-ERR}" "${p50:-?}" "${p99:-?}" "$((${rss:-0}/1024))" >> $OUT
done; done
kill -9 $SRV 2>/dev/null
echo "[$NAME] DONE" >> $OUT
