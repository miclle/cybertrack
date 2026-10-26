#include "action_outputs.h"
#include <array>
#include <vector>
#include <cassert>
#include <iostream>
static std::array<int,49> levels;
static std::array<int,4> pwm, duty;
static unsigned calls, fail_at, motor_writes, water_writes, bubbles_writes, ignition_writes;
static bool fail() { return ++calls == fail_at; }
esp_err_t gpio_set_level(int pin, uint32_t v) {
    if (fail()) return -1;
    // Never change direction while either bridge is enabled.
    if (pin==9 || pin==10 || pin==12 || pin==13) assert(!pwm[2] && !pwm[3]);
    if (pin==18) ++water_writes; else if (pin==17) ++bubbles_writes; else if (pin==21) ++ignition_writes; else ++motor_writes;
    levels[pin]=v; return 0;
}
esp_err_t gpio_set_direction(int pin, int) {
    if (fail()) return -1;
    ++motor_writes;
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
esp_err_t ledc_stop(int, int ch, uint32_t) { if(fail()) return -1; ++motor_writes; pwm[ch]=0; return 0; }
esp_err_t ledc_set_duty(int, int ch, uint32_t d) {
    if(fail()) return -1;
    assert(!pwm[2] && !pwm[3] && d==204); ++motor_writes; duty[ch]=d; return 0;
}
esp_err_t ledc_update_duty(int, int ch) {
    if(fail()) return -1;
    ++motor_writes; pwm[ch]=duty[ch]; return 0;
}
static void reset() { levels.fill(0); pwm.fill(0); duty.fill(0); calls=fail_at=motor_writes=water_writes=bubbles_writes=ignition_writes=0; }
static void off() {
    for(int p : {8,9,10,11,12,13,17,18,21}) assert(!levels[p]);
    assert(!pwm[2] && !pwm[3]);
}
struct State { bool water; int left, right; bool bubbles=false, ignition=false; };
int main() {
    reset(); AudioActionOutputs a; assert(a.Init()); off();
    const unsigned init_calls=calls;
    for(unsigned at=1;at<=init_calls;++at) {
        reset();fail_at=at;AudioActionOutputs x;assert(!x.Init()&&x.fault);off();
        assert(!x.Apply(true,80,80));off();
    }
    const State base_states[]={{false,0,0},{true,0,0},{false,80,80},{true,80,80},
        {false,-80,-80},{true,-80,-80},{false,-80,80},{true,-80,80},{false,80,-80},{true,80,-80}};
    std::vector<State> states;
    for(auto state:base_states) for(bool b:{false,true}) for(bool i:{false,true}) {
        state.bubbles=b; state.ignition=i; states.push_back(state);
    }
    for(const auto& from:states) for(const auto& to:states) {
        reset();AudioActionOutputs x;assert(x.Init());assert(x.Apply(from.water,from.left,from.right,from.bubbles,from.ignition));
        calls=motor_writes=water_writes=bubbles_writes=ignition_writes=0;
        assert(x.Apply(to.water,to.left,to.right,to.bubbles,to.ignition));
        const unsigned transition_calls=calls;
        assert(levels[18]==to.water && levels[17]==to.bubbles && levels[21]==to.ignition);
        assert(pwm[2]==(to.left?204:0)&&pwm[3]==(to.right?204:0));
        assert(levels[9]==(to.left>0)&&levels[10]==(to.left<0));
        assert(levels[12]==(to.right>0)&&levels[13]==(to.right<0));
        if(from.left==to.left&&from.right==to.right) assert(motor_writes==0);
        if(from.water==to.water) assert(water_writes==0);
        if(from.bubbles==to.bubbles) assert(bubbles_writes==0);
        if(from.ignition==to.ignition) assert(ignition_writes==0);
        for(unsigned at=1;at<=transition_calls;++at) {
            reset();AudioActionOutputs y;assert(y.Init());assert(y.Apply(from.water,from.left,from.right,from.bubbles,from.ignition));
            calls=0;fail_at=at;
            assert(!y.Apply(to.water,to.left,to.right,to.bubbles,to.ignition)&&y.fault);off();
            assert(!y.Apply(true,80,80));off();
        }
    }
    reset();AudioActionOutputs x;assert(x.Init());assert(x.Apply(true,80,80));
    assert(!x.Apply(true,30,80)&&x.fault);off();
    std::cout << "PASS: actual output driver 40-state concurrent transition matrix, untouched-lane continuity, disable-before-direction, all init/transition API failures and latched global shutdown\n";
}
