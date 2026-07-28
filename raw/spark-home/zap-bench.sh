#!/bin/bash
exec > ~/zap-bench.log 2>&1
set -x
cd ~/zap-cpp-core/c++
echo "=== protoc + libprotobuf available? ==="
which protoc; protoc --version 2>/dev/null || { echo "installing protobuf"; sudo apt-get install -y protobuf-compiler libprotobuf-dev 2>&1 | tail -2; }
ZB=src/benchmark
ZAPTOOL=build/src/zap/zap
ZAPCPP=build/src/zap
echo "=== generate zap + proto code for the bench workloads ==="
for w in carsales catrank eval; do
  PATH="$ZAPCPP:$PATH" "$ZAPTOOL" compile -oc++ --src-prefix=$ZB $ZB/$w.zap 2>&1 | tail -1
  protoc --cpp_out=$ZB --proto_path=$ZB $ZB/$w.proto 2>&1 | tail -1
done
ls $ZB/*.zap.h $ZB/*.pb.h 2>/dev/null | sed 's|.*/||' | tr '\n' ' '; echo
echo "=== compile the benchmark runner (zap + protobuf + null) ==="
CXX=clang++-21
INC="-Isrc -Ibuild/src -I$ZB"
FLAGS="-std=gnu++23 -stdlib=libc++ -O2 -DNDEBUG -fno-char8_t -w"
$CXX $FLAGS $INC -c $ZB/runner.c++ -o /tmp/runner.o 2>&1 | tail -5
echo "  (runner.o built: $([ -f /tmp/runner.o ] && echo yes || echo NO))"
echo "=== BENCH SETUP DONE ==="
