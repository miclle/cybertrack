#include "control_sessions.h"
#include <cassert>
#include <cstring>
#include <iostream>
using G=AudioActionGuard;
static bool is(const char* a,const char* b){return !std::strcmp(a,b);}
static ControlSessions ready(){ControlSessions s;s.WifiLink(0,true);s.VoiceLink(0,true);s.Tick(0,false);return s;}
int main(){
 for(const char* direction:{"forward","backward","left","right"}) for(int speed:{60,70,80,100}) {
  auto s=ready();assert(is(s.guard.MoveAndWater(0,s.VoiceClaim(0,1,G::Both),5000,3000,direction,speed),"accepted"));
  assert((s.guard.left<0?-s.guard.left:s.guard.left)==speed);
  assert((s.guard.right<0?-s.guard.right:s.guard.right)==speed);
  auto end=s.guard.motion.ends_at;auto starts=s.guard.Starts();
  assert(is(s.VoiceAdjustSpeed(100,s.VoiceClaim(100,2,G::SpeedMode),-10),"accepted"));
  assert((s.guard.left<0?-s.guard.left:s.guard.left)==(speed>70?speed-10:60));
  assert(s.guard.motion.ends_at==end && s.guard.spray.ends_at==3000 && s.guard.Starts()==starts);
  s.Tick(3000,false);assert(s.guard.Moving()&&!s.guard.Watering());s.Tick(5000,false);assert(!s.guard.Moving());
 }
 for(int speed:{0,1,50,59,-1,101}){auto s=ready();assert(!is(s.guard.Move(0,s.VoiceClaim(0,1,G::MoveOnly),1000,"left",speed),"accepted"));assert(!s.guard.Starts());}
 {
  auto s=ready();assert(!s.VoiceClaim(0,1,G::SpeedMode));assert(!s.guard.SetMoveSpeed(50));
  assert(is(s.guard.Move(0,s.VoiceClaim(0,2,G::MoveOnly),1000,"forward"),"accepted"));assert(s.guard.left==100);
  auto ticket=s.VoiceClaim(10,3,G::SpeedMode);assert(is(s.VoiceAdjustSpeed(10,ticket,10),"accepted"));assert(s.guard.left==100);
  assert(!is(s.VoiceAdjustSpeed(11,ticket,-10),"accepted"));assert(!s.VoiceClaim(11,3,G::SpeedMode));
  ticket=s.VoiceClaim(20,4,G::SpeedMode);s.Stop(30);assert(!is(s.VoiceAdjustSpeed(40,ticket,-10),"accepted"));assert(!s.guard.Moving());
 }
 { // A delayed adjustment cannot target a later sequence step.
  auto s=ready();ActionPlan p;p.count=2;p.steps[0]={"forward",1000,0,0,0,80};p.steps[1]={"left",1000,1000,0,0,60};
  assert(is(s.VoicePlan(0,s.VoiceClaim(0,1,G::PlanMode),p),"accepted"));
  auto ticket=s.VoiceClaim(100,2,G::SpeedMode);assert(is(s.VoiceAdjustSpeed(100,ticket,10),"accepted"));assert(s.guard.left==90);
  ticket=s.VoiceClaim(200,3,G::SpeedMode);s.Tick(1000,false);assert(!s.VoiceClaim(1100,4,G::SpeedMode));s.Tick(1200,false);
  assert(s.guard.left==-60&&s.guard.right==60&&s.guard.Watering());
  assert(!is(s.VoiceAdjustSpeed(1201,ticket,10),"accepted"));assert(s.guard.left==-60);
 }
 { // Web preference applies live without changing leases, starts or other outputs.
  auto s=ready();auto web=s.Acquire(0);assert(s.Heartbeat(0,web));
  assert(is(s.WebSpeed(0,web,1,s.window,60),"ok"));assert(!s.guard.Starts());
  assert(s.Heartbeat(1,web));assert(is(s.DriveStart(1,web,2,s.window,"left",3000),"accepted"));
  auto end=s.guard.motion.ends_at;auto starts=s.guard.Starts();assert(s.guard.left==-60);
  assert(s.Heartbeat(100,web));auto window=s.window;
  assert(is(s.WebSpeed(100,web,3,window,80),"ok"));assert(s.guard.left==-80&&s.guard.Watering());
  assert(s.guard.motion.ends_at==end&&s.guard.Starts()==starts&&s.drive_id==2&&s.drive_renewal==1);
  assert(!is(s.WebSpeed(100,web,3,window,60),"ok"));assert(is(s.VoiceAdjustSpeed(100,s.VoiceClaim(100,5,G::SpeedMode),-10),"accepted"));assert(s.guard.left==-70&&s.web_speed_percent==70);assert(s.guard.motion.ends_at==end&&s.guard.Starts()==starts);
  s.Stop(150);assert(!is(s.WebSpeed(151,web,4,window,60),"ok"));assert(!s.guard.Moving());
  s.Release(152,web);web=s.Acquire(153);assert(web&&s.web_speed_percent==100);
 }
 { // Opening and setting web speed must leave voice movement alone.
  auto s=ready();assert(is(s.guard.Move(0,s.VoiceClaim(0,1,G::MoveOnly),5000,"forward",80),"accepted"));
  auto web=s.Acquire(1);assert(s.Heartbeat(1,web));assert(is(s.WebSpeed(1,web,1,s.window,60),"ok"));assert(s.guard.left==80);
  assert(is(s.VoiceAdjustSpeed(100,s.VoiceClaim(100,2,G::SpeedMode),-10),"accepted"));assert(s.guard.left==70&&s.web_speed_percent==60);
 }
 for(const char* dir:{"forward","backward","left","right"}) {
  auto s=ready();assert(is(s.guard.MoveAndWater(0,s.VoiceClaim(0,1,G::Both),15000,10000,dir,80),"accepted"));
  auto starts=s.guard.Starts();
  for(int i=0;i<3;++i){int speed=i==0?60:i==1?100:70;auto ticket=s.VoiceClaim(100+i,10+i,G::SpeedMode);
   assert(is(s.VoiceSetSpeed(100+i,ticket,speed),"accepted"));assert((s.guard.left<0?-s.guard.left:s.guard.left)==speed);
   assert(is(s.guard.direction,dir)&&s.guard.motion.ends_at==15000&&s.guard.spray.ends_at==10000&&s.guard.Starts()==starts);
   assert(!is(s.VoiceSetSpeed(101+i,ticket,80),"accepted"));
  }
  auto ticket=s.VoiceClaim(500,20,G::SpeedMode);s.Stop(501);assert(!is(s.VoiceSetSpeed(502,ticket,100),"accepted"));assert(!s.guard.Moving());
 }
 { // Invalid absolute targets cannot alter the active speed.
  auto s=ready();assert(is(s.guard.Move(0,s.VoiceClaim(0,1,G::MoveOnly),1000,"left",80),"accepted"));
  for(int speed:{0,1,50,59,101}){assert(!is(s.VoiceSetSpeed(1,s.VoiceClaim(1,speed+10,G::SpeedMode),speed),"accepted"));assert(s.guard.left==-80);}
 }
 { // Absolute speed on web motion updates its displayed preference, not its lease.
  auto s=ready();auto web=s.Acquire(0);assert(s.Heartbeat(0,web));assert(is(s.DriveStart(0,web,1,s.window,"right",0),"accepted"));
  auto end=s.guard.motion.ends_at;assert(is(s.VoiceSetSpeed(100,s.VoiceClaim(100,2,G::SpeedMode),60),"accepted"));
  assert(s.web_speed_percent==60&&s.guard.right==-60&&s.guard.motion.ends_at==end&&s.drive_renewal==1&&s.guard.Starts()==1);
  assert(is(s.VoiceAdjustSpeed(200,s.VoiceClaim(200,3,G::SpeedMode),-10),"accepted"));assert(s.guard.right==-60);
 }
 { // Absolute speed cannot leak into the next step or start from idle.
  auto s=ready();assert(!s.VoiceClaim(0,1,G::SpeedMode));ActionPlan p;p.count=2;p.steps[0]={"forward",1000,0,0,0,80};p.steps[1]={"left",1000,0,0,0,70};
  assert(is(s.VoicePlan(0,s.VoiceClaim(0,2,G::PlanMode),p),"accepted"));auto ticket=s.VoiceClaim(100,3,G::SpeedMode);
  s.Tick(1000,false);s.Tick(1200,false);assert(!is(s.VoiceSetSpeed(1201,ticket,100),"accepted"));assert(s.guard.left==-70);
 }
 std::cout<<"PASS: 60% floor, absolute target speed, speed defaults/ranges, four directions, bounded 10-point voice changes, replay and step binding, live web speed without restarts/extensions, source isolation\n";
}
