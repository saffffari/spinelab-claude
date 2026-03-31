import { useEffect } from 'react';
import { AlertCircle, X } from 'lucide-react';

interface ToastProps {
  message: string;
  onClose: () => void;
  duration?: number;
}

export function Toast({ message, onClose, duration = 3000 }: ToastProps) {
  useEffect(() => {
    const timer = setTimeout(() => {
      onClose();
    }, duration);

    return () => clearTimeout(timer);
  }, [duration, onClose]);

  return (
    <div className="fixed top-8 left-1/2 -translate-x-1/2 z-50 animate-in fade-in slide-in-from-top-2 duration-300">
      <div className="bg-[#2d2d2d] border border-white/20 rounded-xl shadow-2xl backdrop-blur-xl flex items-center gap-3 px-4 py-3 min-w-[320px]">
        <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
        <p className="font-['SF_Pro',sans-serif] font-[590] text-[13px] leading-[16px] text-white/85 flex-1" style={{ fontVariationSettings: "'wdth' 100" }}>
          {message}
        </p>
        <button
          onClick={onClose}
          className="text-white/40 hover:text-white/80 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
