#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
mkdir -p build/audio-host
c++ -std=c++17 -g -fsanitize=address,undefined -Wall -Wextra -Werror \
  -Ifirmware/esp32-audio firmware/esp32-audio/tests/draft_duration_intent_test.cc -o build/audio-host/draft_duration_intent_test
build/audio-host/draft_duration_intent_test
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
c++ -std=c++17 -g -fsanitize=address,undefined -Wall -Wextra -Werror \
  -Ifirmware/esp32-audio firmware/esp32-audio/tests/distance_test.cc -o build/audio-host/distance_test
build/audio-host/distance_test
mkdir -p build/audio-host/range-stubs/driver build/audio-host/range-stubs/freertos
for header in driver/gpio driver/rmt_rx esp_log esp_rom_sys esp_timer freertos/FreeRTOS freertos/task freertos/queue; do
  echo '#include "ultrasonic_stub.h"' > "build/audio-host/range-stubs/$header.h"
done
c++ -std=c++17 -g -fsanitize=address,undefined -Wall -Wextra -Werror \
  -Ibuild/audio-host/range-stubs -Ifirmware/esp32-audio/tests -Ifirmware/esp32-audio \
  firmware/esp32-audio/tests/ultrasonic_test.cc -o build/audio-host/ultrasonic_test
build/audio-host/ultrasonic_test
python3 - <<'PYCODE'
from pathlib import Path
source = Path('firmware/esp32-audio/cybertrack_tools.cc').read_text()
start = source.index('void TickLocked(')
end = source.index('\n}', start) + 2
Path('build/audio-host/proximity_tick.inc').write_text(source[start:end])
PYCODE
c++ -std=c++17 -g -fsanitize=address,undefined -Wall -Wextra -Werror \
  -Ibuild/audio-host -Ifirmware/esp32-linx/main -Ifirmware/esp32-audio firmware/esp32-audio/tests/proximity_test.cc \
  build/audio-host/water_policy.o -o build/audio-host/proximity_test
build/audio-host/proximity_test
c++ -std=c++17 -g -fsanitize=address,undefined -Wall -Wextra -Werror \
  -Ifirmware/esp32-audio firmware/esp32-audio/tests/recent_command_test.cc -o build/audio-host/recent_command_test
build/audio-host/recent_command_test
c++ -std=c++17 -g -fsanitize=address,undefined -Wall -Wextra -Werror \
  -Ifirmware/esp32-linx/main -Ifirmware/esp32-audio firmware/esp32-audio/tests/show_test.cc \
  build/audio-host/water_policy.o -o build/audio-host/show_test
build/audio-host/show_test
c++ -std=c++17 -g -fsanitize=address,undefined -Wall -Wextra -Werror \
  -Ifirmware/esp32-linx/main -Ifirmware/esp32-audio firmware/esp32-audio/tests/voice_turn_test.cc \
  build/audio-host/water_policy.o -o build/audio-host/voice_turn_test
build/audio-host/voice_turn_test
