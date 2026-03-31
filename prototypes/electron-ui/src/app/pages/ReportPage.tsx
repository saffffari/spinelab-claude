import { useParams, useNavigate } from 'react-router';
import { DesktopPage } from '../components/DesktopPage';
import { mockPatients, mockAnalytics } from '../data/mockData';
import { ArrowLeft, Download, Share2, Printer, Calendar, User, Activity, CheckCircle2, AlertCircle, TrendingUp } from 'lucide-react';
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '../components/ui/resizable';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar } from 'recharts';
import { usePanelSize } from '../hooks/usePanelSize';
import { PrimaryActionButton } from '../components/PrimaryActionButton';

export default function ReportPage() {
  const { patientId } = useParams();
  const navigate = useNavigate();
  const { leftPanelSize, updateLeftPanel } = usePanelSize();

  const patient = mockPatients.find(p => p.id === patientId);
  const analytics = patientId ? mockAnalytics[patientId] : null;

  // Return early if no patient or analytics
  if (!patient || !analytics) {
    return (
      <DesktopPage title="SpineLab · Report">
        <div className="flex h-full items-center justify-center text-white/60">Loading patient data...</div>
      </DesktopPage>
    );
  }

  // Mock historical data for trend visualization
  const historicalData = [
    { date: '2025-09', cobbAngle: 38, thoracic: 38, lumbar: 16 },
    { date: '2025-12', cobbAngle: 40, thoracic: 40, lumbar: 17 },
    { date: '2026-03', cobbAngle: analytics.cobbAngle, thoracic: analytics.thoracicCurve, lumbar: analytics.lumbarCurve },
  ];

  // Spine assessment radar data
  const radarData = [
    { metric: 'Cobb Angle', value: Math.min(analytics.cobbAngle / 50 * 100, 100), fullMark: 100 },
    { metric: 'Thoracic', value: Math.min(analytics.thoracicCurve / 50 * 100, 100), fullMark: 100 },
    { metric: 'Lumbar', value: Math.min(analytics.lumbarCurve / 30 * 100, 100), fullMark: 100 },
    { metric: 'Rotation', value: Math.min(analytics.vertebralRotation / 20 * 100, 100), fullMark: 100 },
    { metric: 'Risser', value: analytics.risserSign * 20, fullMark: 100 },
  ];

  const getSeverityColor = (angle: number) => {
    if (angle < 10) return 'text-green-400';
    if (angle < 25) return 'text-yellow-400';
    if (angle < 40) return 'text-orange-400';
    return 'text-red-400';
  };

  const getSeverityLabel = (angle: number) => {
    if (angle < 10) return 'Normal';
    if (angle < 25) return 'Mild';
    if (angle < 40) return 'Moderate';
    return 'Severe';
  };

  const getTreatmentRecommendation = (angle: number) => {
    if (angle < 10) return 'Observation only';
    if (angle < 25) return 'Monitor every 6 months';
    if (angle < 40) return 'Consider bracing';
    return 'Surgical consultation recommended';
  };

  return (
    <DesktopPage
      title={`SpineLab · Report · ${patient.name}`}
      subtitle="Reporting and export workspace"
    >
        <ResizablePanelGroup direction="horizontal" className="h-full">
          {/* Left Sidebar - Summary */}
          <ResizablePanel defaultSize={leftPanelSize} minSize={10} maxSize={35} onResize={updateLeftPanel}>
            <div className="app-sidebar-acrylic h-full border-r border-white/10 flex flex-col">
              {/* Header */}
              <div className="px-3 py-2.5 border-b border-white/10">
                <button
                  onClick={() => navigate(`/measurement/${patientId}`)}
                  className="flex items-center gap-2 font-['SF_Pro',sans-serif] font-[590] text-[12px] leading-[15px] text-white/85 hover:text-white transition-colors mb-3"
                  style={{ fontVariationSettings: "'wdth' 100" }}
                >
                  <ArrowLeft className="w-4 h-4" />
                  Back to Measurement
                </button>
                
                <div>
                  <h2 className="font-['SF_Pro',sans-serif] font-[590] text-[13px] leading-[16px] text-white/85" style={{ fontVariationSettings: "'wdth' 100" }}>{patient.name}</h2>
                  <p className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55 mt-1" style={{ fontVariationSettings: "'wdth' 100" }}>Analysis Report</p>
                </div>
              </div>

              {/* Key Metrics */}
              <div className="flex-1 overflow-y-auto px-3 py-2.5 space-y-3">
                <div>
                  <h3 className="font-['SF_Pro',sans-serif] font-[590] text-[11px] leading-[14px] text-white/85 uppercase mb-2" style={{ fontVariationSettings: "'wdth' 100" }}>Key Measurements</h3>
                  
                  <div className="space-y-2">
                    <div className="p-2.5 bg-white/5 rounded-xl border border-white/10">
                      <div className="flex items-center gap-2 mb-1.5">
                        <User className="w-4 h-4 text-blue-400" />
                        <div className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55" style={{ fontVariationSettings: "'wdth' 100" }}>Primary Cobb Angle</div>
                      </div>
                      <div className="font-['SF_Pro',sans-serif] font-[590] text-[28px] leading-[34px] text-white/85" style={{ fontVariationSettings: "'wdth' 100" }}>{analytics.cobbAngle}°</div>
                      <div className={`font-['SF_Pro',sans-serif] font-normal text-[10px] leading-[13px] mt-1 ${getSeverityColor(analytics.cobbAngle)}`} style={{ fontVariationSettings: "'wdth' 100" }}>
                        {getSeverityLabel(analytics.cobbAngle)}
                      </div>
                    </div>

                    <div className="p-2.5 bg-white/5 rounded-xl border border-white/10">
                      <div className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55 mb-1" style={{ fontVariationSettings: "'wdth' 100" }}>Apical Vertebra</div>
                      <div className="font-['SF_Pro',sans-serif] font-[590] text-[17px] leading-[21px] text-white/85" style={{ fontVariationSettings: "'wdth' 100" }}>{analytics.apicalVertebra}</div>
                    </div>

                    <div className="grid grid-cols-2 gap-1.5">
                      <div className="p-2.5 bg-white/5 rounded-xl border border-white/10">
                        <div className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55 mb-1" style={{ fontVariationSettings: "'wdth' 100" }}>Thoracic</div>
                        <div className="font-['SF_Pro',sans-serif] font-[590] text-[15px] leading-[19px] text-white/85" style={{ fontVariationSettings: "'wdth' 100" }}>{analytics.thoracicCurve}°</div>
                      </div>
                      <div className="p-2.5 bg-white/5 rounded-xl border border-white/10">
                        <div className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55 mb-1" style={{ fontVariationSettings: "'wdth' 100" }}>Lumbar</div>
                        <div className="font-['SF_Pro',sans-serif] font-[590] text-[15px] leading-[19px] text-white/85" style={{ fontVariationSettings: "'wdth' 100" }}>{analytics.lumbarCurve}°</div>
                      </div>
                    </div>

                    <div className="p-2.5 bg-white/5 rounded-xl border border-white/10">
                      <div className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55 mb-1" style={{ fontVariationSettings: "'wdth' 100" }}>Vertebral Rotation</div>
                      <div className="flex items-center gap-2">
                        <Activity className="w-4 h-4 text-white/60" />
                        <div className="font-['SF_Pro',sans-serif] font-[590] text-[15px] leading-[19px] text-white/85" style={{ fontVariationSettings: "'wdth' 100" }}>{analytics.vertebralRotation}°</div>
                      </div>
                    </div>

                    <div className="p-2.5 bg-white/5 rounded-xl border border-white/10">
                      <div className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55 mb-1" style={{ fontVariationSettings: "'wdth' 100" }}>Risser Sign</div>
                      <div className="font-['SF_Pro',sans-serif] font-[590] text-[15px] leading-[19px] text-white/85" style={{ fontVariationSettings: "'wdth' 100" }}>Grade {analytics.risserSign}</div>
                      <div className="font-['SF_Pro',sans-serif] font-normal text-[10px] leading-[13px] text-white/25 mt-0.5" style={{ fontVariationSettings: "'wdth' 100" }}>Skeletal maturity indicator</div>
                    </div>
                  </div>
                </div>

                {/* Clinical Recommendation */}
                <div>
                  <h3 className="font-['SF_Pro',sans-serif] font-[590] text-[11px] leading-[14px] text-white/85 uppercase mb-2" style={{ fontVariationSettings: "'wdth' 100" }}>Recommendation</h3>
                  <div className="p-2.5 bg-purple-500/10 rounded-xl border border-purple-500/30">
                    <div className="flex items-start gap-2">
                      {analytics.cobbAngle < 40 ? (
                        <CheckCircle2 className="w-5 h-5 text-purple-400 shrink-0 mt-0.5" />
                      ) : (
                        <AlertCircle className="w-5 h-5 text-yellow-400 shrink-0 mt-0.5" />
                      )}
                      <div>
                        <div className="font-['SF_Pro',sans-serif] font-[590] text-[12px] leading-[15px] text-white/85 mb-1" style={{ fontVariationSettings: "'wdth' 100" }}>
                          {getTreatmentRecommendation(analytics.cobbAngle)}
                        </div>
                        <div className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55" style={{ fontVariationSettings: "'wdth' 100" }}>
                          Based on current measurements and patient age
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Export Button */}
              <div className="px-3 py-2.5 border-t border-white/10">
                <PrimaryActionButton
                  icon={<Download className="h-4 w-4" />}
                  className="w-full rounded-md bg-blue-500 px-4 py-2 transition-colors hover:bg-blue-600"
                  iconClassName="text-white"
                  spinnerClassName="text-white"
                  labelClassName="font-['SF_Pro',sans-serif] text-[12px] font-[590] leading-[15px] text-white"
                >
                  Export PDF Report
                </PrimaryActionButton>
              </div>
            </div>
          </ResizablePanel>

          <ResizableHandle withHandle />

          {/* Main Content - Charts & Detailed Analytics */}
          <ResizablePanel defaultSize={82} minSize={60}>
            <div className="h-full flex flex-col overflow-hidden">
              {/* Header */}
              <div className="app-topbar-acrylic p-6 border-b border-white/10">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-bold text-white/90">Comprehensive Analysis Report</h2>
                    <p className="text-sm text-white/50 mt-1">Automated measurements and trend analysis</p>
                  </div>
                  <button 
                    onClick={() => navigate('/')}
                    className="px-4 py-2 bg-white/5 hover:bg-white/10 text-white/80 text-sm font-medium rounded-md transition-colors border border-white/10"
                  >
                    Back to Home
                  </button>
                </div>
              </div>

              {/* Charts Grid */}
              <div className="flex-1 overflow-y-auto p-6">
                <div className="grid grid-cols-2 gap-6 mb-6">
                  {/* Progression Chart */}
                  <div className="bg-white/5 rounded-lg border border-white/10 p-4">
                    <div className="flex items-center gap-2 mb-4">
                      <TrendingUp className="w-5 h-5 text-blue-400" />
                      <h3 className="text-sm font-semibold text-white/90">Curve Progression</h3>
                    </div>
                    <ResponsiveContainer width="100%" height={250}>
                      <LineChart data={historicalData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                        <XAxis dataKey="date" stroke="rgba(255,255,255,0.5)" style={{ fontSize: '12px' }} />
                        <YAxis stroke="rgba(255,255,255,0.5)" style={{ fontSize: '12px' }} label={{ value: 'Degrees (°)', angle: -90, position: 'insideLeft', style: { fill: 'rgba(255,255,255,0.5)', fontSize: '12px' } }} />
                        <Tooltip 
                          contentStyle={{ backgroundColor: '#1e1e1e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}
                          labelStyle={{ color: 'rgba(255,255,255,0.9)' }}
                        />
                        <Legend wrapperStyle={{ fontSize: '12px' }} />
                        <Line key="line-cobb" type="monotone" dataKey="cobbAngle" stroke="#3b82f6" strokeWidth={2} name="Cobb Angle" />
                        <Line key="line-thoracic" type="monotone" dataKey="thoracic" stroke="#10b981" strokeWidth={2} name="Thoracic" />
                        <Line key="line-lumbar" type="monotone" dataKey="lumbar" stroke="#f59e0b" strokeWidth={2} name="Lumbar" />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Spine Assessment Radar */}
                  <div className="bg-white/5 rounded-lg border border-white/10 p-4">
                    <div className="flex items-center gap-2 mb-4">
                      <Activity className="w-5 h-5 text-purple-400" />
                      <h3 className="text-sm font-semibold text-white/90">Spine Assessment</h3>
                    </div>
                    <ResponsiveContainer width="100%" height={250}>
                      <RadarChart data={radarData}>
                        <PolarGrid stroke="rgba(255,255,255,0.2)" />
                        <PolarAngleAxis dataKey="metric" stroke="rgba(255,255,255,0.6)" style={{ fontSize: '11px' }} />
                        <PolarRadiusAxis stroke="rgba(255,255,255,0.3)" style={{ fontSize: '10px' }} />
                        <Radar name="Severity Index" dataKey="value" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.5} />
                        <Tooltip 
                          contentStyle={{ backgroundColor: '#1e1e1e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}
                        />
                      </RadarChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Detailed Measurements Table */}
                <div className="bg-white/5 rounded-lg border border-white/10 p-6">
                  <h3 className="text-sm font-semibold text-white/90 mb-4">Detailed Measurements</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-white/10">
                          <th className="text-left text-xs font-semibold text-white/60 pb-3 pr-4">Parameter</th>
                          <th className="text-left text-xs font-semibold text-white/60 pb-3 pr-4">Current Value</th>
                          <th className="text-left text-xs font-semibold text-white/60 pb-3 pr-4">Normal Range</th>
                          <th className="text-left text-xs font-semibold text-white/60 pb-3">Status</th>
                        </tr>
                      </thead>
                      <tbody className="text-sm">
                        <tr className="border-b border-white/5">
                          <td className="py-3 pr-4 text-white/80">Cobb Angle</td>
                          <td className="py-3 pr-4">
                            <span className={`font-semibold ${getSeverityColor(analytics.cobbAngle)}`}>
                              {analytics.cobbAngle}°
                            </span>
                          </td>
                          <td className="py-3 pr-4 text-white/60">&lt; 10°</td>
                          <td className="py-3">
                            <span className={`px-2 py-1 rounded text-xs ${
                              analytics.cobbAngle < 10 ? 'bg-green-500/20 text-green-400' :
                              analytics.cobbAngle < 25 ? 'bg-yellow-500/20 text-yellow-400' :
                              analytics.cobbAngle < 40 ? 'bg-orange-500/20 text-orange-400' :
                              'bg-red-500/20 text-red-400'
                            }`}>
                              {getSeverityLabel(analytics.cobbAngle)}
                            </span>
                          </td>
                        </tr>
                        <tr className="border-b border-white/5">
                          <td className="py-3 pr-4 text-white/80">Thoracic Curve</td>
                          <td className="py-3 pr-4">
                            <span className={`font-semibold ${getSeverityColor(analytics.thoracicCurve)}`}>
                              {analytics.thoracicCurve}°
                            </span>
                          </td>
                          <td className="py-3 pr-4 text-white/60">&lt; 10°</td>
                          <td className="py-3">
                            <span className={`px-2 py-1 rounded text-xs ${
                              analytics.thoracicCurve < 25 ? 'bg-yellow-500/20 text-yellow-400' : 'bg-orange-500/20 text-orange-400'
                            }`}>
                              {getSeverityLabel(analytics.thoracicCurve)}
                            </span>
                          </td>
                        </tr>
                        <tr className="border-b border-white/5">
                          <td className="py-3 pr-4 text-white/80">Lumbar Curve</td>
                          <td className="py-3 pr-4">
                            <span className={`font-semibold ${getSeverityColor(analytics.lumbarCurve)}`}>
                              {analytics.lumbarCurve}°
                            </span>
                          </td>
                          <td className="py-3 pr-4 text-white/60">&lt; 10°</td>
                          <td className="py-3">
                            <span className={`px-2 py-1 rounded text-xs ${
                              analytics.lumbarCurve < 25 ? 'bg-yellow-500/20 text-yellow-400' : 'bg-green-500/20 text-green-400'
                            }`}>
                              {getSeverityLabel(analytics.lumbarCurve)}
                            </span>
                          </td>
                        </tr>
                        <tr className="border-b border-white/5">
                          <td className="py-3 pr-4 text-white/80">Vertebral Rotation</td>
                          <td className="py-3 pr-4">
                            <span className="font-semibold text-white/90">{analytics.vertebralRotation}°</span>
                          </td>
                          <td className="py-3 pr-4 text-white/60">&lt; 5°</td>
                          <td className="py-3">
                            <span className={`px-2 py-1 rounded text-xs ${
                              analytics.vertebralRotation < 10 ? 'bg-yellow-500/20 text-yellow-400' : 'bg-orange-500/20 text-orange-400'
                            }`}>
                              {analytics.vertebralRotation < 10 ? 'Mild' : 'Moderate'}
                            </span>
                          </td>
                        </tr>
                        <tr>
                          <td className="py-3 pr-4 text-white/80">Risser Sign</td>
                          <td className="py-3 pr-4">
                            <span className="font-semibold text-white/90">Grade {analytics.risserSign}</span>
                          </td>
                          <td className="py-3 pr-4 text-white/60">0-5 (maturity scale)</td>
                          <td className="py-3">
                            <span className="px-2 py-1 rounded text-xs bg-blue-500/20 text-blue-400">
                              {analytics.risserSign >= 4 ? 'Mature' : 'Growing'}
                            </span>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Clinical Notes */}
                <div className="mt-6 bg-white/5 rounded-lg border border-white/10 p-6">
                  <h3 className="text-sm font-semibold text-white/90 mb-3">Clinical Notes</h3>
                  <div className="space-y-2 text-sm text-white/70">
                    <p>• Automated analysis completed successfully with high confidence</p>
                    <p>• Primary curve located in {analytics.apicalVertebra.includes('T') ? 'thoracic' : 'lumbar'} region</p>
                    <p>• {analytics.cobbAngle >= 40 ? 'Significant curvature detected - surgical evaluation recommended' : 'Curve within non-surgical range - continue monitoring'}</p>
                    <p>• Risser sign grade {analytics.risserSign} indicates {analytics.risserSign >= 4 ? 'skeletal maturity - low progression risk' : 'remaining growth potential - monitor progression'}</p>
                    <p>• Recommended follow-up: {analytics.cobbAngle >= 40 ? '1 month' : analytics.cobbAngle >= 25 ? '3 months' : '6 months'}</p>
                  </div>
                </div>
              </div>
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
    </DesktopPage>
  );
}
