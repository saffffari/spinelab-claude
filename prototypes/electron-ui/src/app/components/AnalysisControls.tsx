import { useState } from 'react';
import { useNavigate } from 'react-router';
import { ChevronDown } from 'lucide-react';
import svgPaths from '../../imports/svg-r4tk1h87oe';
import { PrimaryActionButton } from './PrimaryActionButton';

interface AnalysisControlsProps {
  patientId?: string;
  onAnalyze?: () => void | Promise<void>;
  onGenerateReport?: () => void | Promise<void>;
}

export function AnalysisControls({ patientId, onAnalyze, onGenerateReport }: AnalysisControlsProps) {
  const navigate = useNavigate();
  const [primaryImage, setPrimaryImage] = useState<string>('Standing · X-Ray');
  const [secondaryImage, setSecondaryImage] = useState<string>('Flexion · CT');

  const handleAnalyze = () => {
    if (onAnalyze) {
      onAnalyze();
    } else if (patientId) {
      navigate(`/measurement/${patientId}`);
    }
  };

  const handleGenerateReport = () => {
    if (onGenerateReport) {
      onGenerateReport();
    } else if (patientId) {
      navigate(`/report/${patientId}`);
    }
  };

  return (
    <div className="flex flex-col gap-1.5 w-full">
      {/* Image Selection Buttons */}
      <div className="flex gap-1.5 w-full">
        {/* Primary Image Selector */}
        <button className="bg-[rgba(39,39,42,0.6)] hover:bg-[rgba(45,45,48,0.8)] transition-colors h-[46.5px] rounded-2xl flex items-center justify-between px-3 flex-1 border border-white/5">
          <div className="flex flex-col gap-0.5 items-start">
            <div className="font-['SF_Pro',sans-serif] font-[590] text-[8px] leading-[12px] text-white/30 uppercase tracking-[0.4px]" style={{ fontVariationSettings: "'wdth' 100" }}>
              Primary
            </div>
            <div className="font-['SF_Pro',sans-serif] font-[590] text-[11px] leading-[16.5px] text-white/60" style={{ fontVariationSettings: "'wdth' 100" }}>
              {primaryImage}
            </div>
          </div>
          <ChevronDown className="w-3 h-3 text-white/60" />
        </button>

        {/* Secondary Image Selector */}
        <button className="bg-[rgba(39,39,42,0.6)] hover:bg-[rgba(45,45,48,0.8)] transition-colors h-[46.5px] rounded-2xl flex items-center justify-between px-3 flex-1 border border-white/5">
          <div className="flex flex-col gap-0.5 items-start">
            <div className="font-['SF_Pro',sans-serif] font-[590] text-[8px] leading-[12px] text-white/30 uppercase tracking-[0.4px]" style={{ fontVariationSettings: "'wdth' 100" }}>
              Secondary
            </div>
            <div className="font-['SF_Pro',sans-serif] font-[590] text-[11px] leading-[16.5px] text-white/60" style={{ fontVariationSettings: "'wdth' 100" }}>
              {secondaryImage}
            </div>
          </div>
          <ChevronDown className="w-3 h-3 text-white/60" />
        </button>
      </div>

      {/* Analyze Button */}
      <PrimaryActionButton
        onAction={handleAnalyze}
        disabled={!patientId}
        className="h-[40px] w-full rounded-2xl border border-blue-500/20 bg-[rgba(43,127,255,0.15)] px-4 transition-colors hover:bg-[rgba(43,127,255,0.25)] hover:border-blue-500/30 disabled:cursor-not-allowed disabled:opacity-50"
        iconClassName="text-[#51a2ff]"
        spinnerClassName="text-[#51a2ff]"
        labelClassName="font-['SF_Pro',sans-serif] text-[14px] font-[590] leading-[20px] text-[#51a2ff]"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 16 16">
          <path d={svgPaths.p1d59db00} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.33333" />
        </svg>
        <span style={{ fontVariationSettings: "'wdth' 100" }}>
          Analyze
        </span>
      </PrimaryActionButton>

      {/* Generate Report Button */}
      <PrimaryActionButton
        onAction={handleGenerateReport}
        disabled={!patientId}
        className="h-[40px] w-full rounded-2xl border border-red-500/20 bg-[rgba(231,1,1,0.15)] px-4 transition-colors hover:bg-[rgba(231,1,1,0.25)] hover:border-red-500/30 disabled:cursor-not-allowed disabled:opacity-50"
        iconClassName="text-[#e70101]"
        spinnerClassName="text-[#e70101]"
        labelClassName="font-['SF_Pro',sans-serif] text-[14px] font-[590] leading-[20px] text-[#e70101]"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 16 16">
          <path d={svgPaths.p19416e00} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.33333" />
          <path d={svgPaths.p3e059a80} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.33333" />
          <path d="M6.66667 6H5.33333" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.33333" />
          <path d="M10.6667 8.66667H5.33333" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.33333" />
          <path d="M10.6667 11.3333H5.33333" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.33333" />
        </svg>
        <span style={{ fontVariationSettings: "'wdth' 100" }}>
          Generate Full Report
        </span>
      </PrimaryActionButton>
    </div>
  );
}
