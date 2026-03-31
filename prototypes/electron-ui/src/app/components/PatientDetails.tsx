import { Patient } from '../data/mockData';
import { Calendar, User, FolderOpen } from 'lucide-react';
import { useNavigate } from 'react-router';
import { PrimaryActionButton } from './PrimaryActionButton';

interface PatientDetailsProps {
  patient: Patient | null;
}

export function PatientDetails({ patient }: PatientDetailsProps) {
  const navigate = useNavigate();

  if (!patient) {
    return (
      <div className="flex items-center justify-center h-full text-white/40">
        <div className="text-center">
          <User className="w-16 h-16 mx-auto mb-4 opacity-30" />
          <p className="text-sm">Select a patient to view details</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-6 border-b border-white/10">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-xl font-bold text-white/90">{patient.name}</h2>
            <p className="text-sm text-white/50 mt-1">Patient ID: {patient.id}</p>
          </div>
          <PrimaryActionButton
            onAction={() => navigate(`/case/${patient.id}`)}
            icon={<FolderOpen className="h-4 w-4" />}
            className="rounded-md bg-blue-500 px-4 py-2 text-white transition-colors hover:bg-blue-600"
            iconClassName="text-white"
            spinnerClassName="text-white"
            labelClassName="text-sm font-medium text-white"
          >
            Open Case
          </PrimaryActionButton>
        </div>
        
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-2 text-white/60">
            <User className="w-4 h-4" />
            <span className="text-xs">
              {patient.age} years • {patient.sex === 'M' ? 'Male' : 'Female'}
            </span>
          </div>
          <div className="flex items-center gap-2 text-white/60">
            <Calendar className="w-4 h-4" />
            <span className="text-xs">
              {new Date(patient.lastVisit).toLocaleDateString()}
            </span>
          </div>
        </div>
      </div>

      {/* Details */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Image Library */}
        <div>
          <h3 className="text-sm font-semibold text-white/80 mb-3">Image Library</h3>
          <div className="grid grid-cols-3 gap-2">
            {[...Array(Math.min(patient.imageCount, 6))].map((_, i) => (
              <div
                key={i}
                className="aspect-square bg-white/5 rounded-lg border border-white/10 flex items-center justify-center hover:bg-white/10 transition-colors cursor-pointer"
              >
                <span className="text-xs text-white/40">
                  {i % 3 === 0 ? 'X-Ray' : i % 3 === 1 ? 'CT' : 'MRI'}
                </span>
              </div>
            ))}
          </div>
          {patient.imageCount > 6 && (
            <p className="text-xs text-white/40 mt-2 text-center">
              +{patient.imageCount - 6} more images
            </p>
          )}
        </div>

        {/* Status */}
        <div>
          <h3 className="text-sm font-semibold text-white/80 mb-3">Status</h3>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${
              patient.status === 'active' ? 'bg-green-400' :
              patient.status === 'pending' ? 'bg-yellow-400' :
              'bg-blue-400'
            }`} />
            <div className="text-xs text-white/40">{patient.status}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
