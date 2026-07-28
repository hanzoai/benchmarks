#!/bin/bash
exec > ~/zap-bench4.log 2>&1
set -x
cd ~/zap-cpp-core/c++
ZB=src/benchmark
ZAPD="$(pwd)/build/src/zap"; export PATH="$ZAPD:$PATH"
export CXX=clang++-21
FLAGS="-std=gnu++23 -stdlib=libc++ -O2 -DNDEBUG -fno-char8_t -w -pthread"
INC="-Isrc -Ibuild/src -I$ZB"
for w in carsales catrank; do
  "$ZAPD/zap" compile -I src -oc++ $ZB/$w.zap 2>&1 | tail -1
  protoc --cpp_out=$ZB --proto_path=$ZB $ZB/$w.proto 2>&1 | tail -1
done
ls $ZB/carsales.zap.c++ $ZB/carsales.pb.cc >/dev/null 2>&1 && echo "CODEGEN OK"
SRC="$ZB/runner.c++"
for w in carsales catrank; do SRC="$SRC $ZB/zap-$w.c++ $ZB/protobuf-$w.c++ $ZB/null-$w.c++ $ZB/$w.zap.c++ $ZB/$w.pb.cc"; done
LIBS="build/src/zap/libzap.a build/src/kj/libkj-async.a build/src/kj/libkj.a -lprotobuf -lsnappy -lpthread"
$CXX $FLAGS $INC $SRC $LIBS -o /tmp/zapbench 2>&1 | tail -6
echo "  bench: $([ -x /tmp/zapbench ] && echo BUILT || echo FAILED)"
if [ -x /tmp/zapbench ]; then
  for w in carsales catrank; do for impl in protobuf zap; do
    echo "=== $impl / $w (object reuse, 100k iters) ==="
    /tmp/zapbench $impl $w object reuse none 100000 2>&1 | tail -5
  done; done
fi
echo "=== BENCH4 DONE ==="
