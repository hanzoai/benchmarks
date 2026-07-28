#!/bin/bash
exec > ~/zap-bench3.log 2>&1
set -x
cd ~/zap-cpp-core/c++
ZB=src/benchmark
ZAPD="$(pwd)/build/src/zap"   # ABSOLUTE so the plugin resolves
export PATH="$ZAPD:$PATH"
export CXX=clang++-21
FLAGS="-std=gnu++23 -stdlib=libc++ -O2 -DNDEBUG -fno-char8_t -w -pthread"
INC="-Isrc -Ibuild/src -I$ZB"
for w in carsales catrank; do
  "$ZAPD/zap" compile -I src -oc++:$ZB --src-prefix=src $ZB/$w.zap 2>&1 | tail -2
  protoc --cpp_out=$ZB --proto_path=$ZB $ZB/$w.proto 2>&1 | tail -1
done
ls $ZB/carsales.zap.c++ $ZB/carsales.pb.cc 2>&1 | sed 's|.*/||' | tr '\n' ' '; echo
SRC="$ZB/runner.c++"
for w in carsales catrank; do SRC="$SRC $ZB/zap-$w.c++ $ZB/protobuf-$w.c++ $ZB/null-$w.c++ $ZB/$w.zap.c++ $ZB/$w.pb.cc"; done
LIBS="build/src/zap/libzap.a build/src/kj/libkj-async.a build/src/kj/libkj.a -lprotobuf -lsnappy -lpthread"
$CXX $FLAGS $INC $SRC $LIBS -o /tmp/zapbench 2>&1 | tail -6
echo "  bench binary: $([ -x /tmp/zapbench ] && echo BUILT || echo FAILED)"
[ -x /tmp/zapbench ] && for impl in protobuf zap; do
  echo "=== $impl / carsales ==="; /tmp/zapbench $impl carsales object reuse no-compression 100000 2>&1 | tail -4
done
echo "=== BENCH3 DONE ==="
