"""Mediciones del proceso actual; no estiman recursos de proveedores remotos."""
import os
from pathlib import Path
import platform
import threading
import time


def unavailable(reason):
    return {'status':'unavailable','display':'no disponibles','reason':reason,
            'cpu_seconds':None,'rss_peak_sampled_bytes':None,'gpu':None}


class ProcessResources:
    """RSS y asignaciones PyTorch muestreadas; CPU acumulada del proceso, no del host."""
    def __init__(self, scope, torch_module=None, interval=.05):
        self.scope, self.torch, self.interval = scope, torch_module, interval
        self.stop_event=threading.Event()
        self.rss=[]
        self.gpus={}
        self.gpu_error=None
        self.samples=0

    def sample(self):
        self.samples+=1
        try:
            with open('/proc/self/statm') as f:
                self.rss.append(int(f.read().split()[1])*os.sysconf('SC_PAGE_SIZE'))
        except (OSError,ValueError,IndexError):pass
        if self.torch is not None:
            try:
                for device in range(self.torch.cuda.device_count()):
                    allocated=self.torch.cuda.memory_allocated(device)
                    reserved=self.torch.cuda.memory_reserved(device)
                    row=self.gpus.setdefault(device,{'device':device,'name':self.torch.cuda.get_device_name(device),
                        'allocated_start_bytes':allocated,'reserved_start_bytes':reserved,
                        'allocated_peak_sampled_bytes':allocated,'reserved_peak_sampled_bytes':reserved})
                    row['allocated_peak_sampled_bytes']=max(row['allocated_peak_sampled_bytes'],allocated)
                    row['reserved_peak_sampled_bytes']=max(row['reserved_peak_sampled_bytes'],reserved)
            except Exception:
                self.gpu_error='cuda_metrics_unavailable'

    def loop(self):
        while not self.stop_event.wait(self.interval):self.sample()

    def __enter__(self):
        self.start=time.perf_counter();self.cpu=time.process_time()
        self.sample()
        self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start()
        return self

    def __exit__(self,*args):
        self.stop_event.set();self.thread.join();self.sample()
        wall=time.perf_counter()-self.start
        cpu=time.process_time()-self.cpu
        self.result={'status':'available','scope':self.scope,'pid':os.getpid(),
            'hardware':{'machine':platform.machine(),'logical_cpu_count':os.cpu_count()},
            'sampling_interval_ms':self.interval*1000,'sample_count':self.samples,
            'wall_seconds':wall,'cpu_seconds':cpu,
            'rss_start_bytes':self.rss[0] if self.rss else None,
            'rss_peak_sampled_bytes':max(self.rss) if self.rss else None,
            'ram_status':'available' if self.rss else 'unavailable',
            'gpu':{'status':'available' if self.gpus and not self.gpu_error else 'unavailable',
                   'reason':self.gpu_error or (None if self.gpus else 'no_cuda_measurement'),
                   'scope':'PyTorch allocator in this process; excludes non-PyTorch allocations',
                   'devices':list(self.gpus.values()) if self.gpus else None}}
