from pathlib import Path
import argparse, subprocess, os
parser=argparse.ArgumentParser()
parser.add_argument('--native-source',required=True,type=Path)
parser.add_argument('--baseline',required=True,type=Path)
parser.add_argument('--tools',required=True,type=Path)
args=parser.parse_args()
OUT=Path(__file__).resolve().parent
ROOT=args.native_source.resolve()
BASELINE=args.baseline.resolve()
TOOLS=args.tools.resolve()
os.environ['PATH']=str(TOOLS)+';'+os.environ['PATH']
def tail(src):
 start=src.index('    // Update flip status.',src.index('void VideoOutDriver::Flip('))
 end=src.index('\n}\n\nvoid VideoOutDriver::DrawBlankFrame()',start)
 return src[start:end]
harness=r"""
#include <array>
#include <cassert>
#include <cstdint>
#include <functional>
#include <mutex>
#include <vector>
#include <cstdlib>
using u64=std::uint64_t;
using s64=std::int64_t;
namespace BbFlipTrace { template<class... T> void Record(T...){} }
struct TestMutex {
 std::function<void()> on_unlock; bool held=false;
 void lock(){assert(!held);held=true;}
 void unlock(){assert(held);held=false;if(on_unlock)on_unlock();}
};
struct FlipStatus {u64 count=10,process_time=0,tsc=0; s64 flip_arg=0;int current_buffer=1,gc_queue_num=1,flip_pending_num=1;};
struct Port {
 TestMutex port_mutex;
 std::array<u64,3> buffer_labels{1,1,1};
 int prev_index=1;
 FlipStatus flip_status;
 std::vector<int> flip_events{1};
 int signals=0;
 std::function<void()> on_signal;
 void SignalVoLabel(){++signals;if(on_signal)on_signal();}
};
struct Request {Port* port; int index=2; s64 flip_arg=0xc32;bool eop=true;};
namespace Kernel {
 struct OrbisKernelEvent {enum class Filter {VideoOut};};
 inline std::function<void()> event_hook;
 struct Equeue {void TriggerEvent(u64,OrbisKernelEvent::Filter,void*){if(event_hook)event_hook();}};
 inline Equeue event;
 Equeue* GetEqueue(int id){return id?&event:nullptr;}
}
namespace Libraries::Kernel {u64 sceKernelGetProcessTime(){return 123;}u64 sceKernelReadTsc(){return 456;}}
enum class OrbisVideoOutInternalEventId {Flip=1};
void FinishFlip(const Request& req){
BODY
}
int main(int argc,char** argv){
 assert(argc==2);
 const int mode=std::atoi(argv[1]);
 Port port;Request req{&port};int reused=0;int observed_previous=-99;
 if(mode==4)req.index=-1;
 if(mode==5)req.index=1;
 const auto reuse=[&]{
  assert(port.flip_status.current_buffer==req.index && port.flip_status.count==11);
  observed_previous=port.prev_index;
  // Guest reacts immediately to completion: this is the next surface lock.
  port.buffer_labels[1]=1;++reused;
 };
 if(mode==0)port.port_mutex.on_unlock=reuse;
 if(mode==1 || mode==5)Kernel::event_hook=reuse;
 if(mode==2)port.on_signal=reuse;
 if(mode==3){port.prev_index=-1;port.flip_events={0};}
 FinishFlip(req);
 if(mode<3 || mode==5){
  assert(reused==1);
  assert(port.buffer_labels[1]==1); // no late retirement may clobber next use
  assert(observed_previous==req.index);
  assert(port.signals==1);
 } else if(mode==3) {
  assert(port.buffer_labels[1]==1 && port.signals==0);
 } else if(mode==4) {
  assert(port.buffer_labels[1]==0 && port.signals==1);
 }
 assert(port.prev_index==req.index && port.flip_status.count==11);
 assert(port.flip_status.flip_arg==0xc32 && port.flip_status.current_buffer==req.index);
 assert(port.flip_status.gc_queue_num==0 && port.flip_status.flip_pending_num==0);
}
"""
for label,src,good in [('publish-fixed',(ROOT/'gpu/shadps4/core/libraries/videoout/driver.cpp').read_text(),True),('publish-negative-original',BASELINE.read_text(),False)]:
 cpp=OUT/(label+'.cpp');exe=OUT/(label+'.exe')
 cpp.write_text(harness.replace('BODY',tail(src)))
 subprocess.run([str(TOOLS/'clang++.exe'),'-std=c++23','-O0','-UNDEBUG',str(cpp),'-o',str(exe)],check=True)
 for mode in range(6 if good else 2):
  r=subprocess.run([str(exe),str(mode)],capture_output=True,text=True)
  print(label,'mode',mode,'exit',r.returncode,r.stderr.strip())
  assert (r.returncode==0)==good
print('FLIP_PUBLICATION_ORDER_PASS: exact production tail; status/event immediate reuse preserved; label notification sees new previous index; initial/no-previous, blank -1, repeated index cases; old status/event paths lose new lock')
