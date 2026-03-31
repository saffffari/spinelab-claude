import { Patient } from '../data/mockData';
import { useNavigate } from 'react-router';

interface PatientCardProps {
  patient: Patient;
  isSelected?: boolean;
  onClick?: () => void;
}

export function PatientCard({ patient, isSelected, onClick }: PatientCardProps) {
  const navigate = useNavigate();
  
  const statusColors = {
    active: 'bg-green-500/20 text-green-400 border-green-500/30',
    pending: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    completed: 'bg-blue-500/20 text-blue-400 border-blue-500/30'
  };

  const handleDoubleClick = () => {
    navigate(`/case/${patient.id}`);
  };

  return (
    <div
      onClick={onClick}
      onDoubleClick={handleDoubleClick}
      className={`
        relative p-3 rounded-xl cursor-pointer transition-all
        ${isSelected 
          ? 'bg-white/10 border border-white/15' 
          : 'bg-white/5 border border-white/10 hover:bg-white/10 hover:border-white/20'
        }
      `}
    >
      <div className="flex items-start justify-between mb-2">
        <div>
          <h3 className="text-sm font-semibold text-white/90">{patient.name}</h3>
          <p className="text-xs text-white/50 mt-0.5">ID: {patient.id}</p>
        </div>
        <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${statusColors[patient.status]}`}>
          {patient.status}
        </span>
      </div>
      
      <div className="space-y-1.5 text-xs text-white/60">
        <div className="flex justify-between">
          <span>Age / Sex:</span>
          <span className="text-white/80">{patient.age}y / {patient.sex}</span>
        </div>
        <div className="flex justify-between">
          <span>Diagnosis:</span>
          <span className="text-white/80 text-right ml-2 truncate">{patient.diagnosis}</span>
        </div>
        <div className="flex justify-between">
          <span>Last Visit:</span>
          <span className="text-white/80">{new Date(patient.lastVisit).toLocaleDateString()}</span>
        </div>
        <div className="flex justify-between">
          <span>Images:</span>
          <span className="text-white/80">{patient.imageCount}</span>
        </div>
        {patient.cobbAngle && (
          <div className="flex justify-between pt-1 border-t border-white/10">
            <span>Cobb Angle:</span>
            <span className="text-white/90 font-medium">{patient.cobbAngle}°</span>
          </div>
        )}
      </div>
    </div>
  );
}
