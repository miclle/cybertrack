#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
mkdir -p build/audio-host
cc -std=c11 -g -fsanitize=address,undefined -Wall -Wextra -Werror \
  -Ifirmware/include -c firmware/src/control.c -o build/audio-host/control.o
c++ -std=c++17 -g -fsanitize=address,undefined -Wall -Wextra -Werror \
  -Ifirmware/include -Ifirmware/esp32-audio firmware/esp32-audio/state_test.cc \
  build/audio-host/control.o -o build/audio-host/state_test
build/audio-host/state_test
cc -std=c11 -g -fsanitize=address,undefined -Wall -Wextra -Werror \
  -Ifirmware/esp32-linx/main -c firmware/esp32-linx/main/water_policy.c -o build/audio-host/water_policy.o
c++ -std=c++17 -g -fsanitize=address,undefined -Wall -Wextra -Werror \
  -Ifirmware/esp32-linx/main -Ifirmware/esp32-audio firmware/esp32-audio/water_guard_test.cc \
  build/audio-host/water_policy.o -o build/audio-host/water_guard_test
build/audio-host/water_guard_test
