#include "action_outputs.h"
#include <array>
#include <cassert>
#include <iostream>
static std::array<int,49> levels;
static std::array<int,4> pwm, duty;
static unsigned calls, fail_at;
static bool fail() { return ++calls == fail_at; }
esp_err_t gpio_set_level(int pin, uint32_t v) {
    if (fail()) return -1;
    // Never change direction while either bridge is enabled.
    if (pin==9 || pin==10 || pin==12 || pin==13) assert(!pwm[2] && !pwm[3]);
    if (pin==18 && v) assert(!pwm[2] && !pwm[3]);
    levels[pin]=v; return 0;
}
esp_err_t gpio_set_direction(int pin, int) {
    if (fail()) return -1;
    if (pin==8) pwm[2]=0;
    if (pin==11) pwm[3]=0;
    return 0;
}
esp_err_t gpio_config(const gpio_config_t*) { return fail() ? -1 : 0; }
esp_err_t ledc_timer_config(const ledc_timer_config_t* c) {
    assert(c->timer_num==2 && c->freq_hz==1000 && c->duty_resolution==8);
    return fail() ? -1 : 0;
}
esp_err_t ledc_channel_config(const ledc_channel_config_t* c) {
    assert(c->duty==0 && c->timer_sel==2);
    assert((c->gpio_num==8 && c->channel==2)||(c->gpio_num==11 && c->channel==3));
    return fail() ? -1 : 0;
}
esp_err_t ledc_stop(int, int ch, uint32_t) { if(fail()) return -1; pwm[ch]=0; return 0; }
esp_err_t ledc_set_duty(int, int ch, uint32_t d) {
    if(fail()) return -1;
    assert(!pwm[2] && !pwm[3] && d==154); duty[ch]=d; return 0;
}
esp_err_t ledc_update_duty(int, int ch) {
    if(fail()) return -1;
    assert(!levels[18]); pwm[ch]=duty[ch]; return 0;
}
static void reset() { levels.fill(0); pwm.fill(0); duty.fill(0); calls=fail_at=0; }
static void off() {
    for(int p : {8,9,10,11,12,13,18}) assert(!levels[p]);
    assert(!pwm[2] && !pwm[3]);
}
int main() {
    reset(); AudioActionOutputs a; assert(a.Init()); off();
    const unsigned init_calls=calls;
    for (int l : {-60,60}) for (int r : {-60,60}) {
        assert(a.Apply(false,l,r));
        assert(pwm[2]==154 && pwm[3]==154);
        assert(levels[9]==(l>0) && levels[10]==(l<0));
        assert(levels[12]==(r>0) && levels[13]==(r<0));
        assert(a.Apply(false,0,0)); off();
    }
    assert(a.Apply(true,0,0) && levels[18]);
    assert(a.Apply(false,0,0)); off();
    calls=0; assert(a.Apply(false,60,60)); unsigned start_calls=calls;
    calls=0; assert(a.Apply(false,0,0)); unsigned stop_calls=calls;
    // Fail each startup API and every API in a start/stop transition once.
    for(unsigned at=1;at<=init_calls;++at) {
        reset(); fail_at=at; AudioActionOutputs x; assert(!x.Init() && x.fault); off();
        assert(!x.Apply(false,60,60)); off();
    }
    for(bool stopping : {false,true}) for(unsigned at=1;at<=(stopping?stop_calls:start_calls);++at) {
        reset(); AudioActionOutputs x; assert(x.Init());
        if(stopping) assert(x.Apply(false,60,60));
        calls=0; fail_at=at;
        assert(!x.Apply(false,stopping?0:60,stopping?0:60)); assert(x.fault); off();
        assert(!x.Apply(true,0,0)); off();
    }
    reset(); AudioActionOutputs x; assert(x.Init());
    assert(!x.Apply(true,60,60) && x.fault); off();
    std::cout << "PASS: actual output driver, six pins, four directions, disable-before-direction, mutual exclusion, every init/start/stop API failure, latched shutdown\n";
}
