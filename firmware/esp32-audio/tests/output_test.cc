#include "action_outputs.h"
#include "control_sessions.h"
#include <array>
#include <vector>
#include <cassert>
#include <iostream>
static std::array<int,49> levels;
static std::array<int,4> pwm, duty;
static unsigned calls, fail_at, motor_writes, water_writes, bubbles_writes, ignition_writes;
static bool water_input_enabled = false;
static int forced_water_pad = -1;
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
esp_err_t gpio_input_enable(int pin) {
    assert(pin==18);
    if(fail()) return -1;
    water_input_enabled=true; return 0;
}
int gpio_get_level(int pin) {
    assert(pin==18 && water_input_enabled);
    return forced_water_pad < 0 ? levels[pin] : forced_water_pad;
}
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
    assert(!pwm[2] && !pwm[3] && d==230); ++motor_writes; duty[ch]=d; return 0;
}
esp_err_t ledc_update_duty(int, int ch) {
    if(fail()) return -1;
    ++motor_writes; pwm[ch]=duty[ch]; return 0;
}
static void reset() { levels.fill(0); pwm.fill(0); duty.fill(0); calls=fail_at=motor_writes=water_writes=bubbles_writes=ignition_writes=0; water_input_enabled=false;forced_water_pad=-1; }
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
        assert(!x.Apply(true,90,90));off();
    }
    const State base_states[]={{false,90,0},{false,0,90},{false,-90,0},{false,0,-90},
        {false,0,0},{true,0,0},{false,90,90},{true,90,90},
        {false,-90,-90},{true,-90,-90},{false,-90,90},{true,-90,90},{false,90,-90},{true,90,-90}};
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
        // Assembled chassis: A drives right, B drives left; positive stays forward.
        assert(pwm[2]==(to.right?230:0)&&pwm[3]==(to.left?230:0));
        assert(levels[9]==(to.right>0)&&levels[10]==(to.right<0));
        assert(levels[12]==(to.left>0)&&levels[13]==(to.left<0));
        if(from.left==to.left&&from.right==to.right) assert(motor_writes==0);
        if(from.water==to.water) assert(water_writes==0);
        if(from.bubbles==to.bubbles) assert(bubbles_writes==0);
        if(from.ignition==to.ignition) assert(ignition_writes==0);
        for(unsigned at=1;at<=transition_calls;++at) {
            reset();AudioActionOutputs y;assert(y.Init());assert(y.Apply(from.water,from.left,from.right,from.bubbles,from.ignition));
            calls=0;fail_at=at;
            assert(!y.Apply(to.water,to.left,to.right,to.bubbles,to.ignition)&&y.fault);off();
            assert(!y.Apply(true,90,90));off();
        }
    }
    reset();AudioActionOutputs x;assert(x.Init());assert(x.Apply(true,90,90));
    assert(!x.Apply(true,30,90)&&x.fault);off();
    { // Read the pad independently of commanded output; observation never retries output.
        reset(); AudioActionOutputs y; assert(y.Init()); assert(y.WaterPadLevel()==0);
        assert(y.Apply(true,-90,90));
        assert(y.water_pad.high==1 && y.water_pad.motor_high==1 && y.water_pad.first==1);
        auto writes=water_writes;
        forced_water_pad=0;
        assert(y.Apply(true,-90,90));
        assert(levels[18]==1 && !y.fault && water_writes==writes);
        assert(y.water_pad.low==1 && y.water_pad.motor_low==1 && y.water_pad.last==0);
        forced_water_pad=-1;
        assert(y.Apply(true,0,0));
        assert(y.water_pad.high==2 && y.water_pad.motor_high==1);
        assert(y.Apply(false,0,0));
        const auto saved=y.water_pad;
        assert(saved.off==0 && saved.last==1 && saved.low==1);
        assert(y.Apply(false,0,0)); assert(y.water_pad.high==2 && y.water_pad.low==1);
        assert(y.Apply(true,0,0));
        assert(y.water_pad.high==1 && y.water_pad.low==0 && y.water_pad.motor_high==0 && y.water_pad.off==-1);
        assert(saved.low==1); // A queued snapshot survives the next action.
        y.water_pad.high=UINT_MAX; y.water_pad.motor_high=UINT_MAX;
        assert(y.Apply(true,-90,90));
        assert(y.water_pad.high==UINT_MAX && y.water_pad.motor_high==UINT_MAX);
        calls=0;fail_at=1;assert(!y.Apply(false,0,0));off();
        assert(y.water_pad.off==0 && y.fault);
    }
    // Exercise the scheduler AND real output driver at the device's 5 ms cadence.
    // Every nonempty lane combination must survive the transition into a later
    // step, with independent deadlines, not merely report active guard flags.
    for (const char* direction : {"forward", "backward", "left", "right"}) {
        for (unsigned mask=1; mask<16; ++mask) {
            reset(); AudioActionOutputs output; assert(output.Init());
            ControlSessions session;
            session.WifiLink(0,true); session.VoiceLink(0,true); session.Tick(0,false);
            ActionPlan plan; plan.count=2;
            plan.steps[0]={"forward",5000,0,0,0};
            plan.steps[1]={mask&1 ? direction : "none", mask&1 ? 1000 : 0,
                mask&2 ? 1500 : 0, mask&4 ? 2000 : 0, mask&8 ? 500 : 0};
            assert(!std::strcmp(session.VoicePlan(0,
                session.VoiceClaim(0,1,AudioActionGuard::PlanMode),plan),"accepted"));
            int left=0,right=0; assert(AudioActionGuard::Direction(direction,left,right));
            unsigned water_on_ms=0;
            for (uint64_t now=0;now<=7500;now+=5) {
                session.Tick(now,false);
                const auto& g=session.guard;
                assert(output.Apply(g.Watering(),g.Moving()?g.left:0,g.Moving()?g.right:0,
                                    g.Bubbling(),g.Igniting()));
                const bool move=(mask&1)&&now>=5200&&now<6200;
                const bool water=(mask&2)&&now>=5200&&now<6700;
                const bool bubbles=(mask&4)&&now>=5200&&now<7200;
                const bool ignition=(mask&8)&&now>=5200&&now<5700;
                assert(levels[18]==water && levels[17]==bubbles && levels[21]==ignition);
                assert(pwm[2]==((now<5000||move)?230:0));
                assert(pwm[3]==((now<5000||move)?230:0));
                if(move) {
                    assert(levels[9]==(right>0)&&levels[10]==(right<0));
                    assert(levels[12]==(left>0)&&levels[13]==(left<0));
                }
                if(levels[18]) water_on_ms+=5;
            }
            assert(water_on_ms==((mask&2)?1500u:0u));
            assert(!session.plan_active&&!std::strcmp(session.plan_result,"completed"));
            off();
        }
    }
    std::cout << "PASS: actual output driver 56-state concurrent transition matrix, A/right B/left mapping, untouched-lane continuity, disable-before-direction, all init/transition API failures and latched global shutdown\n";
    std::cout << "PASS: scheduler-to-GPIO/PWM integration, four directions x 15 parallel lane combinations, second-step start and independent deadlines at 5 ms cadence\n";
    std::cout << "PASS: GPIO18 input enable failure, independent pad readback, high/low/motor samples, per-action reset, snapshot, saturation and fault shutdown\n";
}
