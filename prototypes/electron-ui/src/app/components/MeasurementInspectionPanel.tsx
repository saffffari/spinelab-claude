import { useState } from 'react';
import { ChevronRight, ChevronDown, AlertCircle, AlertTriangle, CheckCircle, Info, Activity, Ruler, FileText, TrendingUp } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts';
import DisclosureButton from './DisclosureButton';

// SVG paths from Figma imports
const svgPaths = {
  upTrend: "M9.16667 2.91667L5.625 6.45833L3.54167 4.375L0.833333 7.08333",
  downTrend: "M9.16667 7.08333L5.625 3.54167L3.54167 5.625L0.833333 2.91667",
  cobbAngle: "M10.374 8.00695L6.374 1.00695C6.28678 0.85305 6.1603 0.725042 6.00746 0.635983C5.85462 0.546923 5.68089 0.5 5.504 0.5C5.3271 0.5 5.15338 0.546923 5.00054 0.635983C4.8477 0.725042 4.72122 0.85305 4.634 1.00695L0.633998 8.00695C0.545839 8.15963 0.499612 8.3329 0.500002 8.5092C0.500393 8.68551 0.547387 8.85857 0.636221 9.01086C0.725055 9.16315 0.852572 9.28924 1.00585 9.37636C1.15912 9.46348 1.3327 9.50853 1.509 9.50695H9.509C9.68445 9.50677 9.85676 9.46043 10.0086 9.37259C10.1605 9.28475 10.2866 9.15849 10.3743 9.00651C10.4619 8.85452 10.508 8.68214 10.508 8.50669C10.5079 8.33124 10.4617 8.15889 10.374 8.00695Z",
};

const segmentData = [
  { id: 'L5-S1', h: '11.2', ang: '12.5°', trans: '0.8 mm', str: '2.1%', rot: '1.2°', status: 'normal' },
  { id: 'L4-L5', h: '10.8', ang: '11.8°', trans: '2.4 mm', str: '4.8%', rot: '3.1°', status: 'warning', diff: '-1.2mm', trend: 'down' },
  { id: 'L3-L4', h: '11.5', ang: '10.2°', trans: '0.6 mm', str: '1.9%', rot: '0.8°', status: 'normal' },
  { id: 'L2-L3', h: '11.0', ang: '9.8°', trans: '0.5 mm', str: '1.7%', rot: '0.6°', status: 'normal' },
  { id: 'L1-L2', h: '10.9', ang: '8.5°', trans: '0.4 mm', str: '1.5%', rot: '0.5°', status: 'normal' },
  { id: 'T12-L1', h: '9.8', ang: '7.2°', trans: '1.8 mm', str: '3.6%', rot: '2.4°', status: 'warning', diff: '+0.8°', trend: 'up' },
  { id: 'T11-T12', h: '9.5', ang: '6.5°', trans: '0.3 mm', str: '1.2%', rot: '0.4°', status: 'normal' },
  { id: 'T10-T11', h: '9.2', ang: '5.8°', trans: '0.2 mm', str: '1.0%', rot: '0.3°', status: 'normal' },
];

const chartData = [
  { month: 1, val: 0.8 },
  { month: 2, val: 1.2 },
  { month: 3, val: 1.5 },
  { month: 4, val: 2.3 },
  { month: 5, val: 2.6 },
  { month: 6, val: 3.1 },
  { month: 7, val: 3.8 },
  { month: 8, val: 4.2 },
  { month: 9, val: 4.8 },
];

export function MeasurementInspectionPanel() {
  const [showMeasurements, setShowMeasurements] = useState(false);
  const [showAnalysis, setShowAnalysis] = useState(true);
  const [showFindings, setShowFindings] = useState(true);
  const [showProgression, setShowProgression] = useState(true);

  return (
    <div className="h-full flex flex-col bg-[#1e1e1e] border-l border-white/10 overflow-hidden">
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {/* Segment Table */}
        <div className="bg-white/5 rounded-2xl overflow-hidden border border-white/10">
          <div className="grid grid-cols-6 gap-2 px-3 py-2 border-b border-white/10 bg-white/5">
            <div className="text-[9px] text-white/40 uppercase font-bold">Seg</div>
            <div className="text-[9px] text-white/40 uppercase font-bold text-right">H</div>
            <div className="text-[9px] text-white/40 uppercase font-bold text-right">Ang</div>
            <div className="text-[9px] text-white/40 uppercase font-bold text-right">Trans</div>
            <div className="text-[9px] text-white/40 uppercase font-bold text-right">Str</div>
            <div className="text-[9px] text-white/40 uppercase font-bold text-right">Rot</div>
          </div>
          <div className="max-h-[220px] overflow-y-auto">
            {segmentData.map((seg) => (
              <div key={seg.id} className={`grid grid-cols-6 gap-2 px-3 py-2 items-center border-b border-white/5 last:border-0 ${seg.status === 'warning' ? 'bg-orange-500/10' : ''}`}>
                <div className="flex items-center gap-1.5">
                  <div className={`size-1.5 rounded-full ${seg.status === 'warning' ? 'bg-orange-500' : 'bg-emerald-500'}`} />
                  <span className="text-[11px] text-white/85 font-medium">{seg.id}</span>
                </div>
                <div className="text-[10px] text-white/70 text-right">{seg.h}</div>
                <div className="text-[10px] text-white/70 text-right">{seg.ang}</div>
                <div className="text-[10px] text-white/70 text-right">{seg.trans}</div>
                <div className="text-[10px] text-white/70 text-right">{seg.str}</div>
                <div className="flex flex-col items-end">
                  <span className="text-[10px] text-white/70">{seg.rot}</span>
                  {seg.diff && (
                    <div className={`flex items-center gap-0.5 text-[8px] ${seg.trend === 'up' ? 'text-orange-500' : 'text-red-500'}`}>
                      <svg width="8" height="8" viewBox="0 0 10 10" fill="none">
                        <path d={seg.trend === 'up' ? svgPaths.upTrend : svgPaths.downTrend} stroke="currentColor" strokeWidth="1" />
                      </svg>
                      {seg.diff}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Measurements */}
        <div className="bg-white/5 rounded-2xl border border-white/10">
          <button 
            onClick={() => setShowMeasurements(!showMeasurements)}
            className="w-full px-4 py-3 flex items-center justify-between hover:bg-white/5 transition-colors"
          >
            <div className="flex items-center gap-3">
              <Ruler className="size-4 text-red-500" />
              <span className="text-[12px] font-semibold text-white/85">Measurements</span>
            </div>
            <DisclosureButton isOpen={showMeasurements} onClick={() => {}} direction="down" />
          </button>
          {showMeasurements && (
            <div className="px-4 pb-4 text-center">
              <p className="text-[11px] text-white/40 italic">No annotations yet. Use the tools to measure.</p>
            </div>
          )}
        </div>

        {/* Analysis Results */}
        <div className="bg-white/5 rounded-2xl border border-white/10">
          <button 
            onClick={() => setShowAnalysis(!showAnalysis)}
            className="w-full px-4 py-3 flex items-center justify-between hover:bg-white/5 transition-colors"
          >
            <div className="flex items-center gap-3">
              <Activity className="size-4 text-red-500" />
              <span className="text-[12px] font-semibold text-white/85">Analysis Results</span>
            </div>
            <DisclosureButton isOpen={showAnalysis} onClick={() => {}} direction="down" />
          </button>
          {showAnalysis && (
            <div className="px-4 pb-4 space-y-2">
              <ResultRow icon={<CheckCircle className="size-3 text-emerald-500" />} label="L4 Height" value="28.5 mm" />
              <ResultRow 
                icon={
                  <div className="size-3 text-orange-500">
                    <svg viewBox="0 0 12 12" fill="none" className="size-full">
                      <path d={svgPaths.cobbAngle} stroke="currentColor" strokeWidth="1" />
                    </svg>
                  </div>
                } 
                label="Cobb Angle" 
                value="14.2°" 
                trend="+2.1°" 
                trendType="up"
              />
              <ResultRow 
                icon={
                   <div className="size-3 text-orange-500">
                    <svg viewBox="0 0 12 12" fill="none" className="size-full">
                      <path d={svgPaths.cobbAngle} stroke="currentColor" strokeWidth="1" />
                    </svg>
                  </div>
                } 
                label="L4-L5 Height" 
                value="8.3 mm" 
                trend="-1.2mm" 
                trendType="down"
              />
              <ResultRow icon={<CheckCircle className="size-3 text-emerald-500" />} label="Spinal Canal Diameter" value="11.8 mm" />
            </div>
          )}
        </div>

        {/* Key Findings Report */}
        <div className="bg-white/5 rounded-2xl border border-white/10">
          <button 
            onClick={() => setShowFindings(!showFindings)}
            className="w-full px-4 py-3 flex items-center justify-between hover:bg-white/5 transition-colors"
          >
            <div className="flex items-center gap-3">
              <FileText className="size-4 text-red-500" />
              <span className="text-[12px] font-semibold text-white/85">Key Findings Report</span>
            </div>
            <DisclosureButton isOpen={showFindings} onClick={() => {}} direction="down" />
          </button>
          {showFindings && (
            <div className="px-4 pb-4 space-y-3">
              <div className="flex items-center justify-between bg-black/20 rounded-xl px-3 py-1.5">
                <StatusBadge color="bg-red-500" label="1 Critical" />
                <div className="w-px h-3 bg-white/10" />
                <StatusBadge color="bg-orange-500" label="2 Warning" />
                <div className="w-px h-3 bg-white/10" />
                <StatusBadge color="bg-emerald-500" label="3 Normal" />
              </div>
              
              <FindingCard 
                type="critical" 
                title="Ligamentum Flavum Hypertrophy" 
                segment="L4-L5" 
                desc="Thickening noted at L4-L5 contributing to canal narrowing. Correlate clinically." 
                trend="-1.2mm"
              />
              <FindingCard 
                type="warning" 
                title="Mild Central Stenosis" 
                segment="L4-L5" 
                desc="Narrowing of the spinal canal at L4-L5 measuring 11.8mm. Approaching threshold for surgical consideration." 
                trend="-1.2mm"
              />
              <FindingCard 
                type="warning" 
                title="Disc Height Loss" 
                segment="L4-L5" 
                desc="Progressive disc space narrowing at L4-L5 with 1.2mm decrease from prior study." 
                trend="-1.2mm"
              />
              <FindingCard 
                type="info" 
                title="Mild Scoliotic Curvature" 
                segment="T12-L4" 
                desc="Cobb angle measured at 14.2°, increased 2.1° from prior. Monitor for progression." 
                trend="-1.2mm"
              />
            </div>
          )}
        </div>

        {/* Post-Op Slip Progression */}
        <div className="bg-white/5 rounded-2xl border border-white/10">
          <button 
            onClick={() => setShowProgression(!showProgression)}
            className="w-full px-4 py-3 flex items-center justify-between hover:bg-white/5 transition-colors"
          >
            <div className="flex items-center gap-3">
              <TrendingUp className="size-4 text-orange-500" />
              <span className="text-[12px] font-semibold text-white/85">Post-Op Slip Progression</span>
              <span className="text-[10px] text-orange-500 font-medium ml-auto">+0.7 mm <span className="text-white/40">last mo.</span></span>
            </div>
            <DisclosureButton isOpen={showProgression} onClick={() => {}} direction="down" />
          </button>
          {showProgression && (
            <div className="px-4 pb-4">
              <div className="h-[120px] w-full mt-2">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" vertical={false} />
                    <XAxis 
                      dataKey="month" 
                      fontSize={8} 
                      axisLine={false} 
                      tickLine={false} 
                      stroke="#ffffff40" 
                    />
                    <YAxis 
                      fontSize={8} 
                      axisLine={false} 
                      tickLine={false} 
                      stroke="#ffffff40" 
                    />
                    <RechartsTooltip 
                      contentStyle={{ backgroundColor: '#2d2d2d', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', fontSize: '10px' }}
                      itemStyle={{ color: '#ff6900' }}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="val" 
                      stroke="#ff6900" 
                      strokeWidth={2} 
                      dot={{ r: 3, fill: '#ff6900', strokeWidth: 0 }} 
                      activeDot={{ r: 4, fill: '#ff6900' }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="flex items-center justify-between mt-4">
                <span className="text-[9px] text-white/40">Current: 4.8 mm at Mo. 9</span>
                <span className="text-[9px] text-orange-500 font-medium">Approaching threshold</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ResultRow({ icon, label, value, trend, trendType }: { icon: React.ReactNode, label: string, value: string, trend?: string, trendType?: 'up' | 'down' }) {
  return (
    <div className="flex items-center gap-3 py-1.5 px-2 bg-white/5 rounded-lg border border-white/5">
      {icon}
      <span className="text-[11px] text-white/70 flex-1">{label}</span>
      <span className="text-[11px] text-white/90 font-medium">{value}</span>
      {trend && (
        <div className={`flex items-center gap-0.5 text-[9px] font-medium ${trendType === 'up' ? 'text-red-500' : 'text-red-500'}`}>
          <svg width="8" height="8" viewBox="0 0 10 10" fill="none">
             <path d={trendType === 'up' ? svgPaths.upTrend : svgPaths.downTrend} stroke="currentColor" strokeWidth="1" />
          </svg>
          {trend}
        </div>
      )}
    </div>
  );
}

function StatusBadge({ color, label }: { color: string, label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={`size-1.5 rounded-full ${color}`} />
      <span className="text-[10px] text-white/60">{label}</span>
    </div>
  );
}

function FindingCard({ type, title, segment, desc, trend }: { type: 'critical' | 'warning' | 'info', title: string, segment: string, desc: string, trend: string }) {
  const getStyles = () => {
    switch (type) {
      case 'critical': return { bg: 'bg-red-500/10', border: 'border-red-500/20', icon: <AlertCircle className="size-3 text-red-500" /> };
      case 'warning': return { bg: 'bg-orange-500/10', border: 'border-orange-500/20', icon: <AlertTriangle className="size-3 text-orange-500" /> };
      case 'info': return { bg: 'bg-slate-500/10', border: 'border-slate-500/20', icon: <Info className="size-3 text-white/40" /> };
    }
  };
  const styles = getStyles();

  return (
    <div className={`${styles.bg} ${styles.border} border rounded-xl p-3 space-y-2`}>
      <div className="flex items-start gap-2">
        {styles.icon}
        <div className="flex-1">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-white/90 leading-none">{title}</span>
            <div className="flex items-center gap-1.5">
              <span className="text-[9px] bg-black/40 text-white/40 px-1.5 py-0.5 rounded-md font-medium uppercase tracking-wider">{segment}</span>
              <div className="flex items-center gap-0.5 text-[8px] text-red-500">
                <svg width="8" height="8" viewBox="0 0 10 10" fill="none">
                  <path d={svgPaths.downTrend} stroke="currentColor" strokeWidth="1" />
                </svg>
              </div>
            </div>
          </div>
          <p className="text-[9px] text-white/40 leading-relaxed mt-1">{desc}</p>
        </div>
      </div>
    </div>
  );
}
