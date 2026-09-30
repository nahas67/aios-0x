import React from 'react';
import { 
  Server, 
   
  Cpu, 
   
  ShieldCheck, 
  Wifi, 
   
  HardDrive,
  

} from 'lucide-react';
import { mockSystemHealth } from '../../data/mockData';

export const SystemHealthWorkspace: React.FC = () => {
  const categories = ['DATA_PLANE', 'CONTROL_PLANE', 'EXECUTION_PLANE', 'OBSERVABILITY', 'GOVERNANCE'] as const;

  const getCategoryTitle = (cat: string) => {
    switch (cat) {
      case 'DATA_PLANE': return 'Data Plane (Ingestion & Storage)';
      case 'CONTROL_PLANE': return 'Control Plane (Agents & LangGraph)';
      case 'EXECUTION_PLANE': return 'Execution Plane (SOR & Slicers)';
      case 'OBSERVABILITY': return 'Observability (Telemetry & Logs)';
      case 'GOVERNANCE': return 'Governance (Constitution & Merkle Vault)';
      default: return cat;
    }
  };

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Header */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Server className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
              SYSTEM HEALTH & 38/38 WIRED SERVICES
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
              FRAME 13
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            Distributed Container Fabric • Sub-millisecond IPC • High Availability (99.998% Uptime)
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">SERVICES:</span>{' '}
            <span className="text-emerald-400 font-bold">38 / 38 WIRED (100% HEALTHY)</span>
          </div>
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">MEAN LATENCY:</span>{' '}
            <span className="text-cyan-300 font-bold">1.4 MS</span>
          </div>
        </div>
      </div>

      {/* Cluster Overview Stat Ribbon */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
        <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-3 shadow-2xl flex items-center gap-3">
          <Cpu className="w-6 h-6 text-cyan-400" />
          <div>
            <div className="text-[10px] text-slate-400">CPU UTILIZATION</div>
            <div className="text-base font-bold text-white font-mono-num">24.2% (128 Cores)</div>
          </div>
        </div>

        <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-3 shadow-2xl flex items-center gap-3">
          <HardDrive className="w-6 h-6 text-indigo-400" />
          <div>
            <div className="text-[10px] text-slate-400">MEMORY ALLOCATED</div>
            <div className="text-base font-bold text-white font-mono-num">48.2 GB / 256 GB</div>
          </div>
        </div>

        <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-3 shadow-2xl flex items-center gap-3">
          <Wifi className="w-6 h-6 text-emerald-400" />
          <div>
            <div className="text-[10px] text-slate-400">NETWORK INGESTION</div>
            <div className="text-base font-bold text-emerald-400 font-mono-num">1.84 GB/s</div>
          </div>
        </div>

        <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-3 shadow-2xl flex items-center gap-3">
          <ShieldCheck className="w-6 h-6 text-cyan-400" />
          <div>
            <div className="text-[10px] text-slate-400">SERVICE MESH</div>
            <div className="text-base font-bold text-cyan-300">mTLS ENCRYPTED</div>
          </div>
        </div>
      </div>

      {/* Categorized 38 Services Breakdown */}
      <div className="space-y-4">
        {categories.map((cat) => {
          const services = mockSystemHealth.components.filter(c => c.category === cat);
          if (services.length === 0) return null;

          return (
            <div key={cat} className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
              <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
                <h3 className="text-xs font-bold uppercase text-white tracking-wider">
                  {getCategoryTitle(cat)}
                </h3>
                <span className="text-[10px] text-emerald-400">
                  {services.length} SERVICES ALL OPERATIONAL
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 my-3">
                {services.map((svc) => (
                  <div
                    key={svc.name}
                    className="p-2.5 rounded bg-white/[0.02] border border-white/[0.05] flex items-center justify-between text-xs"
                  >
                    <div>
                      <div className="font-bold text-slate-200 flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                        <span>{svc.name}</span>
                      </div>
                      <div className="text-[10px] text-slate-400 mt-0.5">
                        Uptime: <span className="text-slate-200">{svc.uptimePct}%</span> • Latency: <span className="text-cyan-300">{svc.latencyMs}ms</span>
                      </div>
                    </div>

                    <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
                      HEALTHY
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
