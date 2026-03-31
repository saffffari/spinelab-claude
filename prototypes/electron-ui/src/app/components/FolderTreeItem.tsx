import { ChevronRight, User, Circle } from 'lucide-react';
import { Patient } from '../data/mockData';

interface FolderTreeItemProps {
  patient: Patient;
  isSelected?: boolean;
  onClick?: () => void;
  onDoubleClick?: () => void;
}

export function FolderTreeItem({ patient, isSelected, onClick, onDoubleClick }: FolderTreeItemProps) {
  const statusColors = {
    active: 'text-green-400',
    pending: 'text-yellow-400',
    completed: 'text-blue-400'
  };

  return (
    <div
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      className={`
        group flex items-center gap-2 px-3 py-1.5 cursor-pointer transition-all rounded-md
        ${isSelected 
          ? 'bg-white/10 text-white/90' 
          : 'text-white/70 hover:bg-white/5 hover:text-white/90'
        }
      `}
    >
      <ChevronRight className={`w-3 h-3 text-white/40 transition-transform ${isSelected ? 'rotate-90' : ''}`} />
      <User className="w-3.5 h-3.5 text-white/40 shrink-0" />
      <span className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] flex-1 truncate" style={{ fontVariationSettings: "'wdth' 100" }}>
        {patient.name}
      </span>
      <Circle className={`w-1.5 h-1.5 fill-current shrink-0 ${statusColors[patient.status]}`} />
    </div>
  );
}
