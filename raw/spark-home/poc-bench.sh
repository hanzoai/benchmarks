#!/bin/bash
exec > ~/poc-bench.log 2>&1
DS=~/ds-rebrand/build-final/programs/datastore.bolt
CH=~/ch-official/clickhouse
QS=("agg:SELECT c,count(),avg(v),sum(v),quantile(0.9)(v) FROM bench GROUP BY c" \
    "filter:SELECT count() FROM bench WHERE v>0.5 AND c='api'" \
    "topk:SELECT uid,sum(v) s FROM bench GROUP BY uid ORDER BY s DESC LIMIT 20" \
    "scan:SELECT count() FROM bench WHERE v>0.999")

# --- B: datastore over SeaweedFS (S-Chain), already loaded ---
$DS server --config-file=/tmp/poc_ds/config.xml & DSV=$!
for i in $(seq 1 40); do $DS client --port 62100 -q "SELECT 1" >/dev/null 2>&1 && break; sleep 1; done
echo "### datastore over SeaweedFS (S-Chain storage, optimized binary) ###"
sleep 2; dsrss=$(awk '/VmRSS/{print int($2/1024)}' /proc/$DSV/status)
for q in "${QS[@]}"; do n=${q%%:*}; sql=${q#*:}
  $DS client --port 62100 -q "$sql FORMAT Null" 2>/dev/null  # warm
  best=99; for r in 1 2 3; do t=$($DS client --port 62100 --time -q "$sql FORMAT Null" 2>&1 | tail -1); awk -v t=$t -v b=$best 'BEGIN{exit !(t<b)}' && best=$t; done
  printf "  %-7s %ss\n" "$n" "$best"
done
echo "  RSS: ${dsrss}MB  | parts on SeaweedFS (S-Chain), local dir: $(du -sh /tmp/poc_ds/data/store 2>/dev/null|awk '{print $1}')"
kill -9 $DSV 2>/dev/null; sleep 1

# --- A: vanilla ClickHouse, local disk ---
A=/tmp/ch_local; rm -rf $A; mkdir -p $A/data $A/tmp
cat > $A/c.xml <<XML
<clickhouse><logger><level>error</level><log>$A/s.log</log></logger><tcp_port>62200</tcp_port>
<path>$A/data/</path><tmp_path>$A/tmp/</tmp_path><listen_host>127.0.0.1</listen_host>
<user_directories><users_xml><path>$A/u.xml</path></users_xml></user_directories></clickhouse>
XML
echo "<clickhouse><users><default><password></password><networks><ip>::/0</ip></networks><profile>default</profile><quota>default</quota></default></users><profiles><default/></profiles><quotas><default/></quotas></clickhouse>" > $A/u.xml
$CH server --config-file=$A/c.xml & CHV=$!
for i in $(seq 1 40); do $CH client --port 62200 -q "SELECT 1" >/dev/null 2>&1 && break; sleep 1; done
$CH client --port 62200 -q "CREATE TABLE bench (id UInt64,uid UInt32,ts DateTime,v Float64,c LowCardinality(String)) ENGINE=MergeTree ORDER BY (c,ts)" 2>&1
$CH client --port 62200 -q "INSERT INTO bench SELECT number,rand()%100000,now()-(rand()%2592000),rand()/4e6,['ads','web','api','iot'][(number%4)+1] FROM numbers(5000000)" 2>&1
echo "### vanilla ClickHouse (local disk, official binary) ###"
sleep 2; chrss=$(awk '/VmRSS/{print int($2/1024)}' /proc/$CHV/status)
for q in "${QS[@]}"; do n=${q%%:*}; sql=${q#*:}
  $CH client --port 62200 -q "$sql FORMAT Null" 2>/dev/null
  best=99; for r in 1 2 3; do t=$($CH client --port 62200 --time -q "$sql FORMAT Null" 2>&1 | tail -1); awk -v t=$t -v b=$best 'BEGIN{exit !(t<b)}' && best=$t; done
  printf "  %-7s %ss\n" "$n" "$best"
done
echo "  RSS: ${chrss}MB  | local disk: $(du -sh $A/data/store 2>/dev/null|awk '{print $1}')"
kill -9 $CHV 2>/dev/null
echo "BENCH_DONE"
