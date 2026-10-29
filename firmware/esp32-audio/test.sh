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
c++ -std=c++17 -g -fsanitize=address,undefined -Wall -Wextra -Werror \
  -Ifirmware/esp32-linx/main -Ifirmware/esp32-audio firmware/esp32-audio/tests/action_test.cc \
  build/audio-host/water_policy.o -o build/audio-host/action_test
build/audio-host/action_test
c++ -std=c++17 -g -fsanitize=address,undefined -Wall -Wextra -Werror \
  -Ifirmware/esp32-linx/main -Ifirmware/esp32-audio firmware/esp32-audio/tests/sessions_test.cc \
  build/audio-host/water_policy.o -o build/audio-host/sessions_test
build/audio-host/sessions_test
mkdir -p build/audio-host/stubs/driver
for header in gpio ledc; do
  echo '#include "output_stub.h"' > "build/audio-host/stubs/driver/$header.h"
done
c++ -std=c++17 -g -fsanitize=address,undefined -Wall -Wextra -Werror \
  -Ibuild/audio-host/stubs -Ifirmware/esp32-audio/tests -Ifirmware/esp32-audio -Ifirmware/esp32-linx/main \
  firmware/esp32-audio/tests/output_test.cc build/audio-host/water_policy.o -o build/audio-host/output_test
build/audio-host/output_test
c++ -std=c++17 -g -fsanitize=address,undefined -Wall -Wextra -Werror \
  -Ifirmware/esp32-linx/main -Ifirmware/esp32-audio firmware/esp32-audio/tests/effects_test.cc \
  build/audio-host/water_policy.o -o build/audio-host/effects_test
build/audio-host/effects_test
c++ -std=c++17 -g -fsanitize=address,undefined -Wall -Wextra -Werror \
  -Ifirmware/esp32-linx/main -Ifirmware/esp32-audio firmware/esp32-audio/tests/frenzy_test.cc \
  build/audio-host/water_policy.o -o build/audio-host/frenzy_test
build/audio-host/frenzy_test
c++ -std=c++17 -g -fsanitize=address,undefined -Wall -Wextra -Werror \
  -Ifirmware/esp32-linx/main -Ifirmware/esp32-audio firmware/esp32-audio/tests/sequence_test.cc \
  build/audio-host/water_policy.o -o build/audio-host/sequence_test
build/audio-host/sequence_test
c++ -std=c++17 -g -fsanitize=address,undefined -Wall -Wextra -Werror \
  -Ifirmware/esp32-linx/main -Ifirmware/esp32-audio firmware/esp32-audio/tests/speed_test.cc \
  build/audio-host/water_policy.o -o build/audio-host/speed_test
build/audio-host/speed_test
