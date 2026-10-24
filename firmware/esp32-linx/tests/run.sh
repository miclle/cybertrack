#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
mkdir -p ../build/linx-host
cc -std=c11 -g -fsanitize=address,undefined -Wall -Wextra -Werror \
  -DYYJSON_DISABLE_WRITER=1 -DYYJSON_DISABLE_UTILS=1 -DYYJSON_DISABLE_NON_STANDARD=1 \
  -Iinclude -Ithird_party/yyjson -Iesp32-linx/main \
  esp32-linx/tests/readonly_test.c esp32-linx/main/linx_wire.c \
  src/control.c src/protocol.c src/freshness.c src/replay_store.c src/replay_log.c \
  third_party/yyjson/yyjson.c -o ../build/linx-host/readonly_test
../build/linx-host/readonly_test
linx_idf_dir="${IDF_PATH:-$HOME/esp/esp-idf}"
# Vendor cJSON uses sprintf; silence only its macOS deprecation diagnostic.
cc -std=c11 -g -fsanitize=address,undefined -Wno-deprecated-declarations -c \
  "$linx_idf_dir/components/json/cJSON/cJSON.c" -o ../build/linx-host/cJSON.o
cc -std=c11 -g -fsanitize=address,undefined -Wall -Wextra -Werror \
  -DYYJSON_DISABLE_WRITER=1 -DYYJSON_DISABLE_UTILS=1 -DYYJSON_DISABLE_NON_STANDARD=1 \
  -Iinclude -Ithird_party/yyjson -Iesp32-linx/main -I"$linx_idf_dir/components/json/cJSON" \
  esp32-linx/tests/water_test.c esp32-linx/main/water_policy.c esp32-linx/main/water_mcp.c \
  src/control.c src/protocol.c src/freshness.c src/replay_store.c src/replay_log.c \
  third_party/yyjson/yyjson.c ../build/linx-host/cJSON.o -lm -o ../build/linx-host/water_test
../build/linx-host/water_test
