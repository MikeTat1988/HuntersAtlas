"""Compile exact production gate/ASC function bodies against deterministic scheduler stubs."""
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[1]
g=(root/'gpu/shadps4/core/libraries/gnmdriver/gnmdriver.cpp').read_text()
l=(root/'gpu/shadps4/video_core/amdgpu/liverpool.cpp').read_text()
def function(s, signature):
    start=s.index(signature); brace=s.index('{',start); depth=1; end=brace+1
    while depth:
        depth += (s[end]=='{')-(s[end]=='}'); end+=1
    return s[start:end]
code=r'''
#include <mutex>
#include <condition_variable>
#include <atomic>
#include <cassert>
#include <span>
#include <queue>
#include <algorithm>
#include <iostream>
using u32=unsigned; using s32=int; using u64=unsigned long long;
#define PS4_SYSV_ABI
#define HLE_TRACE
#define LOG_DEBUG(...)
#define LOG_TRACE(...)
#define ASSERT_MSG(x,...) assert(x)
constexpr int ORBIS_OK=0;
namespace Platform { enum class InterruptId { GpuIdle }; }
struct CheckedMutex {
 std::mutex mutex; std::atomic<u32>* count; bool* retired;
 void lock(){mutex.lock();}
 void unlock(){assert(*count>0); assert(!*retired); mutex.unlock();}
};
struct Liverpool {
 std::atomic<u32> num_submits{0}; bool work_retired=true;
 std::mutex submit_mutex; std::condition_variable submit_cv;
 static constexpr u32 NumTotalQueues=2; u32 num_mapped_queues=1;
 struct Queue {CheckedMutex m_access; std::queue<int> submits;};
 Queue mapped_queues[2]{{{ {}, &num_submits, &work_retired},{}},{{ {}, &num_submits, &work_retired},{}}};
 struct Task {int handle=1;}; Task ProcessCompute(std::span<const u32>,u32){return {};}
 bool IsGpuIdle(){std::scoped_lock lk{submit_mutex}; return num_submits==0 && work_retired;}
 void SubmitDone(){}
 void SubmitAsc(u32,std::span<const u32>);
};
Liverpool gpu; Liverpool* liverpool=&gpu;
static u32 submission_lock{};
std::condition_variable cv_lock; std::mutex m_wait_idle,m_submit_lock;
static bool send_init_packet=true; static u64 frames_submitted=0;
struct Debug {void IncGnmFrameNum(){}} DebugState;
'''
for sig in ['static void ResetSubmissionLock(', 'static void WaitGpuIdle(', 'int PS4_SYSV_ABI sceGnmAreSubmitsAllowed(', 's32 PS4_SYSV_ABI sceGnmSubmitDone(']:
    code += '\n'+function(g,sig)
code+='\n'+function(l,'void Liverpool::SubmitAsc(')
code+=r'''
int main(){
 // Old drain has completed but a newer submission is queued and closes the gate.
 gpu.num_submits=1; gpu.work_retired=false;
 sceGnmSubmitDone(); assert(!sceGnmAreSubmitsAllowed());
 ResetSubmissionLock(Platform::InterruptId::GpuIdle);
 assert(!sceGnmAreSubmitsAllowed());
 // Decode completion alone must not release guest memory before deferred writes retire.
 gpu.num_submits=0;
 ResetSubmissionLock(Platform::InterruptId::GpuIdle);
 assert(!sceGnmAreSubmitsAllowed());
 gpu.work_retired=true;
 ResetSubmissionLock(Platform::InterruptId::GpuIdle);
 assert(sceGnmAreSubmitsAllowed());
 // Already-idle SubmitDone must leave the gate open.
 sceGnmSubmitDone(); assert(sceGnmAreSubmitsAllowed());
 // Queue mutex unlock is the first possible consumer observation. CheckedMutex
 // asserts accounting is published at that exact boundary (old code fails here).
 gpu.SubmitAsc(1,{});
 assert(gpu.num_submits==1 && gpu.num_mapped_queues==2);
 assert(gpu.mapped_queues[1].submits.size()==1);
 std::cout << "PASS stale idle, deferred retirement, idle submit, queue publication\n";
}
'''
out=root/'out/renderer-sync-test'; out.mkdir(exist_ok=True)
(out/'test.cpp').write_text(code)
compiler=Path('D:/Bloodborne/tools/map-build/msys64/clang64/bin/clang++.exe')
subprocess.run([str(compiler),'-std=c++20','-O0',str(out/'test.cpp'),'-o',str(out/'test.exe')],check=True)
subprocess.run([str(out/'test.exe')],check=True)
# Negative controls exercise the original defects without editing production files.
mutations = {
    'stale-idle': code.replace('if (liverpool->IsGpuIdle()) {', 'if (true) {', 1),
    'queue-publication': code.replace('        ++num_submits;\n        work_retired = false;', '        /* omit pre-publication accounting */', 1),
}
for name, mutant in mutations.items():
    source=out/(name+'.cpp'); exe=out/(name+'.exe'); source.write_text(mutant)
    subprocess.run([str(compiler),'-std=c++20','-O0',str(source),'-o',str(exe)],check=True)
    result=subprocess.run([str(exe)],capture_output=True,text=True)
    assert result.returncode != 0, f'Negative control {name} was not detected'
    print(f'PASS negative control {name}: rejected (exit {result.returncode})')
