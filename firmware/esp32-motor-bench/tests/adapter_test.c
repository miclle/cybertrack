#include <assert.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include "idf_stub.h"

static int test_printf(const char *format, ...);
#define printf test_printf
#include "../main/motor_bench.c"
#undef printf

typedef struct { uint64_t at; const char *keys; } input_event;
typedef struct { uint64_t at; int channel, in1, in2; } pulse_event;
typedef struct { uint64_t at; int channel; } off_event;
static struct {
    uint64_t now, end, stop_at, release_at, uart_fault_at;
    const input_event *inputs;
    size_t input_count, input_index;
    uint32_t levels[10];
    unsigned energized;
    bool fault_delivered, boot_during_read, delay_during_read;
    const char *fail_api;
    int fail_channel;
    bool failed, persistent_stop_failure, error_logged, ready_logged, boot_logged;
    unsigned pulse_count, off_count;
    pulse_event pulses[16];
    off_event stops[16];
} sim;
static jmp_buf done;

static bool fail(const char *api, int channel)
{
    if (sim.fail_api && strcmp(sim.fail_api, api) == 0 && sim.fail_channel == channel &&
        (!sim.failed || (sim.persistent_stop_failure && strcmp(api, "stop") == 0))) {
        sim.failed = true;
        return true;
    }
    return false;
}
static void disable(int channel)
{
    if (sim.energized & (1u << channel)) {
        assert(sim.off_count < 16);
        sim.stops[sim.off_count++] = (off_event){sim.now,channel};
    }
    sim.energized &= ~(1u << channel);
}
static int test_printf(const char *format, ...)
{
    assert(!sim.energized);
    char text[512];
    va_list args;
    va_start(args, format);
    int n = vsnprintf(text, sizeof(text), format, args);
    va_end(args);
    if (strstr(text, "BENCH READY")) {
        assert(strstr(text, "0.3.2-l298n-dual-10s A=4/5/6 B=7/8/9"));
        assert(strstr(text, "PWM=1000Hz/60% pulse=10000ms"));
        assert(strstr(text, "target=NONE at boot"));
        sim.ready_logged = true;
    }
    if (strstr(text, "BENCH ERROR")) sim.error_logged = true;
    if (strstr(text, "BOOT held")) sim.boot_logged = true;
    return n;
}
esp_err_t gpio_set_level(int pin, uint32_t level)
{
    assert(pin >= 4 && pin <= 9);
    if (pin != 4 && pin != 7) assert(!sim.energized); /* both disabled before any direction change */
    if ((pin == 6 || pin == 9) && level && fail("input2", pin == 6 ? 0 : 1)) return ESP_FAIL;
    sim.levels[pin] = level;
    return ESP_OK;
}
esp_err_t gpio_set_direction(int pin, int mode)
{
    assert((pin == 4 || pin == 7) && mode == GPIO_MODE_OUTPUT && sim.levels[pin] == 0);
    disable(pin == 4 ? 0 : 1);
    return ESP_OK;
}
esp_err_t gpio_config(const gpio_config_t *c)
{
    if (c->mode == GPIO_MODE_OUTPUT) {
        assert(c->pin_bit_mask == UINT64_C(0x3f0) && c->pull_down_en);
        for (int i=4; i<=9; ++i) assert(sim.levels[i] == 0);
    } else assert(c->pin_bit_mask == 1 && c->pull_up_en);
    return ESP_OK;
}
int gpio_get_level(int pin)
{
    assert(pin == 0);
    return !(sim.now >= sim.stop_at && sim.now < sim.release_at);
}
esp_err_t ledc_stop(int mode, int channel, uint32_t idle)
{
    assert(mode == 0 && channel >= 0 && channel < 2 && idle == 0);
    if ((sim.energized & (1u << channel)) && fail("stop",channel)) return ESP_FAIL;
    disable(channel);
    return ESP_OK;
}
esp_err_t ledc_timer_config(const ledc_timer_config_t *c)
{
    assert(c->freq_hz == 1000 && c->duty_resolution == 8);
    return fail("timer",-1) ? ESP_FAIL : ESP_OK;
}
esp_err_t ledc_channel_config(const ledc_channel_config_t *c)
{
    assert(c->channel >= 0 && c->channel < 2);
    assert(c->gpio_num == (c->channel == 0 ? 4 : 7) && c->duty == 0);
    return fail("channel",c->channel) ? ESP_FAIL : ESP_OK;
}
esp_err_t ledc_set_duty(int mode, int channel, uint32_t duty)
{
    assert(mode == 0 && channel >= 0 && channel < 2 && duty == 154 && !sim.energized);
    return fail("duty",channel) ? ESP_FAIL : ESP_OK;
}
esp_err_t ledc_update_duty(int mode, int channel)
{
    assert(mode == 0 && channel >= 0 && channel < 2 && !(sim.energized & (1u<<channel)));
    int in1=channel == 0 ? 5 : 8, in2=in1+1;
    assert(sim.levels[in1] != sim.levels[in2]);
    assert(sim.pulse_count < 16 && !sim.error_logged);
    sim.pulses[sim.pulse_count++] = (pulse_event){sim.now,channel,sim.levels[in1],sim.levels[in2]};
    sim.energized |= 1u << channel;
    return fail("update",channel) ? ESP_FAIL : ESP_OK; /* failure after applying duty */
}
esp_err_t uart_param_config(int port, const uart_config_t *c)
{
    assert(port == 0 && c->baud_rate == 115200); return ESP_OK;
}
esp_err_t uart_driver_install(int port, int rx, int tx, int count, QueueHandle_t *q, int flags)
{
    assert(port == 0 && rx == 512 && tx == 0 && count == 16 && flags == 0);
    *q = &sim; return ESP_OK;
}
esp_err_t uart_flush_input(int port)
{
    assert(port == 0);
    while (sim.input_index < sim.input_count && sim.inputs[sim.input_index].at <= sim.now)
        ++sim.input_index;
    return ESP_OK;
}
esp_err_t uart_get_buffered_data_len(int port, size_t *size)
{
    assert(port == 0);
    *size = sim.input_index < sim.input_count && sim.inputs[sim.input_index].at <= sim.now
          ? strlen(sim.inputs[sim.input_index].keys) : 0;
    return ESP_OK;
}
int uart_read_bytes(int port, void *buffer, uint32_t size, uint32_t ticks)
{
    assert(port == 0 && ticks == 0 && sim.input_index < sim.input_count);
    const char *keys = sim.inputs[sim.input_index++].keys;
    size_t n = strlen(keys); assert(n <= size); memcpy(buffer, keys, n);
    if (sim.boot_during_read && strcmp(keys, "f") == 0) sim.stop_at = sim.now;
    if (sim.delay_during_read && strcmp(keys, "f") == 0) sim.now += BENCH_PULSE_MS;
    return (int)n;
}
int xQueueReceive(QueueHandle_t q, void *event, uint32_t ticks)
{
    assert(q == &sim && ticks == 0);
    if (sim.now == sim.uart_fault_at && !sim.fault_delivered) {
        ((uart_event_t *)event)->type = UART_FIFO_OVF; sim.fault_delivered = true; return pdTRUE;
    }
    return 0;
}
esp_err_t esp_task_wdt_add(void *task) { assert(task == NULL); return ESP_OK; }
esp_err_t esp_task_wdt_reset(void) { return ESP_OK; }
int64_t esp_timer_get_time(void) { return (int64_t)sim.now * 1000; }
const char *esp_err_to_name(esp_err_t error) { assert(error == ESP_FAIL); return "injected"; }
void vTaskDelay(uint32_t ticks)
{
    sim.now += ticks;
    if (sim.now >= sim.end) longjmp(done, 1);
}
static void setup(const input_event *inputs, size_t count, uint64_t end)
{
    memset(&sim, 0, sizeof(sim));
    sim.inputs=inputs; sim.input_count=count; sim.end=end; sim.fail_channel=-1;
    sim.stop_at=sim.release_at=sim.uart_fault_at=UINT64_MAX;
    pwm_ready_mask=0;
}
static void run(void)
{
    if (setjmp(done) == 0) app_main();
    assert(!sim.energized);
    for (int i=4; i<=9; ++i) assert(sim.levels[i] == 0);
}
static void stopped_both_at(uint64_t at)
{
    assert(sim.pulse_count == 2 && sim.off_count == 2);
    assert(sim.stops[0].at == at && sim.stops[1].at == at);
    assert(sim.stops[0].channel != sim.stops[1].channel);
}
int main(void)
{
    const input_event singles[]={{40,"1"},{50,"a"},{100,"f"},{13000,"2"},{13100,"2"},{13110,"a"},{13120,"r"}};
    setup(singles,7,23500); run();
    assert(sim.ready_logged && sim.pulse_count == 2 && sim.off_count == 2);
    assert(sim.pulses[0].channel == 0 && sim.pulses[0].at == 100 && sim.pulses[0].in1 == 1 && sim.pulses[0].in2 == 0);
    assert(sim.pulses[1].channel == 1 && sim.pulses[1].at == 13120 && sim.pulses[1].in1 == 0 && sim.pulses[1].in2 == 1);
    assert(sim.stops[0].at == 10100 && sim.stops[1].at == 23120);
    const input_event dual[]={{40,"3"},{50,"a"},{100,"f"},{13100,"a"},{13105,"r"}};
    setup(dual,5,23500); run();
    assert(sim.pulse_count == 4 && sim.off_count == 4);
    for (unsigned i=0; i<4; ++i) {
        assert(sim.pulses[i].channel == (int)(i%2));
        assert(sim.pulses[i].in1 == (i<2) && sim.pulses[i].in2 == (i>=2));
        assert(sim.stops[i].at == (i<2 ? 10100 : 23105));
    }
    const struct { const char *select, *key; unsigned mask; bool reverse_a, reverse_b; } cases[] = {
        {"1","f",1,false,false}, {"1","r",1,true,true},
        {"2","f",2,false,false}, {"2","r",2,true,true},
        {"3","f",3,false,false}, {"3","r",3,true,true},
        {"3","x",3,false,true}, {"3","y",3,true,false},
    };
    for (unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);++i) {
        input_event inputs[]={{40,cases[i].select},{50,"a"},{100,cases[i].key}};
        setup(inputs,3,10500);run();
        assert(sim.pulse_count==(cases[i].mask==3 ? 2u : 1u));
        unsigned j=0;
        for (unsigned ch=0;ch<2;++ch) {
            if (!(cases[i].mask & (1u<<ch))) continue;
            bool rev=ch==0 ? cases[i].reverse_a : cases[i].reverse_b;
            assert(sim.pulses[j].channel==(int)ch && sim.pulses[j].in1==!rev && sim.pulses[j].in2==rev);
            assert(sim.stops[j].channel==(int)ch && sim.stops[j].at==10100);
            ++j;
        }
    }
    const input_event late_stop[]={{40,"3"},{50,"a"},{100,"x"},{9100,"s"}};
    setup(late_stop,4,13000);run();stopped_both_at(9100);
    setup(late_stop,3,13000);sim.stop_at=9100;sim.release_at=9200;run();stopped_both_at(9100);
    for (unsigned ch=1;ch<=2;++ch) {
        const input_event forbidden[]={{40,ch==1 ? "1" : "2"},{50,"a"},{100,"x"},{150,"a"},{200,"y"}};
        setup(forbidden,5,3500);run();assert(!sim.pulse_count);
    }
    const char *cancel_keys[]={"s","r","x","y","1","2","3","?","af"};
    for (unsigned i=0; i<sizeof(cancel_keys)/sizeof(cancel_keys[0]); ++i) {
        input_event cancel[]={{40,"3"},{50,"a"},{100,"f"},{150,cancel_keys[i]},{1200,"f"}};
        setup(cancel,5,1500);run();stopped_both_at(150);
    }
    setup(dual,3,1600); sim.stop_at=150;sim.release_at=200;run();stopped_both_at(150);
    setup(dual,3,500);sim.boot_during_read=true;run();assert(sim.pulse_count==0);
    setup(dual,3,600);sim.delay_during_read=true;run();assert(sim.pulse_count==0);
    setup(dual,3,500);sim.uart_fault_at=150;run();stopped_both_at(150);
    const input_event invalid[]={{40,"a"},{100,"f"},{150,"3af"},{200,"r"},{250,"3"},{260,"a"},{270,"2"},{280,"f"}};
    setup(invalid,8,600);run();assert(sim.pulse_count==0);
    const input_event fault_run[]={{40,"3"},{50,"a"},{100,"r"},{13500,"a"},{13550,"f"}};
    const char *failures[]={"channel","input2","duty","update","stop"};
    for(int ch=0;ch<2;++ch) for(unsigned i=0;i<5;++i) {
        setup(fault_run,5,14000);sim.fail_api=failures[i];sim.fail_channel=ch;run();
        assert(sim.failed && sim.error_logged);
        assert(sim.pulse_count == (i<3 ? 0u : i==3 ? (unsigned)ch+1 : 2u));
        if(i==3) for(unsigned j=0;j<sim.off_count;++j) assert(sim.stops[j].at==100);
    }
    for(int ch=0;ch<2;++ch) {
        setup(fault_run,5,14000);sim.fail_api="stop";sim.fail_channel=ch;sim.persistent_stop_failure=true;
        run();assert(sim.failed && sim.error_logged);stopped_both_at(10100);
    }
    setup(NULL,0,500);sim.fail_api="timer";run();assert(sim.failed && sim.error_logged && !sim.pulse_count);
    setup(NULL,0,500);run();assert(!sim.pulse_count && sim.ready_logged);
    setup(NULL,0,500);sim.stop_at=100;sim.release_at=200;run();
    assert(!sim.pulse_count && sim.boot_logged); /* observable stop even between runs */
    puts("PASS: actual six-GPIO task, isolated A/B, all eight direction combinations, 10 s cutoff / 3 s cooldown, early/late stop, explicit selection, both-off on BOOT/UART/live changes, partial initialization, either-channel faults and persistent stop failures");
}
