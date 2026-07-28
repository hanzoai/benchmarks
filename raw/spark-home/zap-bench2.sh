#!/bin/bash
exec > ~/zap-bench2.log 2>&1
set -x
cd ~/zap-cpp-core/c++
ZB=src/benchmark; ZAPD=build/src/zap
export CXX=clang++-21
FLAGS="-std=gnu++23 -stdlib=libc++ -O2 -DNDEBUG -fno-char8_t -w -pthread"
INC="-Isrc -Ibuild/src -I$ZB"
for w in carsales catrank eval; do
  PATH="$ZAPD:$PATH" $ZAPD/zap compile -I src -oc++ --src-prefix=$ZB $ZB/$w.zap 2>&1 | tail -1
  protoc --cpp_out=$ZB --proto_path=$ZB $ZB/$w.proto 2>&1 | tail -1
done
echo "=== compile + link the benchmark (zap + protobuf + null impls) ==="
SRC="$ZB/runner.c++"
for w in carsales catrank eval; do SRC="$SRC $ZB/zap-$w.c++ $ZB/protobuf-$w.c++ $ZB/null-$w.c++ $ZB/$w.zap.c++ $ZB/$w.pb.cc"; done
LIBS="build/src/zap/libzap.a build/src/zap/libkj.a -lprotobuf -lpthread"
$CXX $FLAGS $INC $SRC $LIBS -o /tmp/zapbench 2>&1 | tail -8
echo "  bench binary: $([ -x /tmp/zapbench ] && echo BUILT || echo FAILED)"
echo "=== RUN: zap vs protobuf, carsales (object reuse mode, count iterations) ==="
[ -x /tmp/zapbench ] && for impl in protobuf zap; do
  echo "--- $impl carsales ---"
  /tmp/zapbench $impl carsales object reuse no-compression 200000 2>&1 | tail -3
done
echo "=== BENCH DONE ==="
