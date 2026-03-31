export interface Patient {
  id: string;
  name: string;
  age: number;
  sex: string;
  diagnosis: string;
  lastVisit: string;
  imageCount: number;
  status: 'active' | 'pending' | 'completed';
  cobbAngle?: number;
  apicalVertebra?: string;
}

export interface MedicalImage {
  id: string;
  type: 'xray' | 'ct' | 'mri';
  view: string;
  date: string;
  thumbnail: string;
  url: string;
}

export interface Analytics {
  cobbAngle: number;
  apicalVertebra: string;
  thoracicCurve: number;
  lumbarCurve: number;
  vertebralRotation: number;
  risserSign: number;
}

export interface ProcedureHistoryItem {
  id: string;
  type: string;
  surgeon: string;
  facility: string;
  date: string;
  notes: string;
}

export const mockPatients: Patient[] = [
  {
    id: 'P001',
    name: 'Sarah Johnson',
    age: 16,
    sex: 'F',
    diagnosis: 'Adolescent Idiopathic Scoliosis',
    lastVisit: '2026-03-15',
    imageCount: 12,
    status: 'active',
    cobbAngle: 42,
    apicalVertebra: 'T8'
  },
  {
    id: 'P002',
    name: 'Michael Chen',
    age: 14,
    sex: 'M',
    diagnosis: 'Juvenile Scoliosis',
    lastVisit: '2026-03-10',
    imageCount: 8,
    status: 'active',
    cobbAngle: 28,
    apicalVertebra: 'T7'
  },
  {
    id: 'P003',
    name: 'Emily Rodriguez',
    age: 17,
    sex: 'F',
    diagnosis: 'Thoracic Scoliosis',
    lastVisit: '2026-03-08',
    imageCount: 15,
    status: 'completed',
    cobbAngle: 35,
    apicalVertebra: 'T9'
  },
  {
    id: 'P004',
    name: 'David Kim',
    age: 15,
    sex: 'M',
    diagnosis: 'Lumbar Scoliosis',
    lastVisit: '2026-03-05',
    imageCount: 10,
    status: 'pending',
    cobbAngle: 31,
    apicalVertebra: 'L2'
  },
  {
    id: 'P005',
    name: 'Jessica Martinez',
    age: 13,
    sex: 'F',
    diagnosis: 'Double Major Curve',
    lastVisit: '2026-03-01',
    imageCount: 18,
    status: 'active',
    cobbAngle: 45,
    apicalVertebra: 'T7/L1'
  },
];

export const mockAnalytics: Record<string, Analytics> = {
  'P001': {
    cobbAngle: 42,
    apicalVertebra: 'T8',
    thoracicCurve: 42,
    lumbarCurve: 18,
    vertebralRotation: 15,
    risserSign: 3
  },
  'P002': {
    cobbAngle: 28,
    apicalVertebra: 'T7',
    thoracicCurve: 28,
    lumbarCurve: 12,
    vertebralRotation: 10,
    risserSign: 2
  },
  'P003': {
    cobbAngle: 35,
    apicalVertebra: 'T9',
    thoracicCurve: 35,
    lumbarCurve: 15,
    vertebralRotation: 12,
    risserSign: 4
  },
};

export const procedureHistory: ProcedureHistoryItem[] = [
  {
    id: 'proc-001',
    type: 'Posterior Spinal Fusion',
    surgeon: 'Dr. Robert Martinez',
    facility: 'Children\'s Orthopedic Center',
    date: '2025-11-12',
    notes: 'Successful T4-L2 fusion with instrumentation. Patient tolerated procedure well.'
  },
  {
    id: 'proc-002',
    type: 'Pre-operative Assessment',
    surgeon: 'Dr. Sarah Williams',
    facility: 'Spine Institute',
    date: '2025-10-18',
    notes: 'Comprehensive evaluation completed. Patient cleared for surgical intervention.'
  },
  {
    id: 'proc-003',
    type: 'Initial Consultation',
    surgeon: 'Dr. Sarah Williams',
    facility: 'Spine Institute',
    date: '2025-09-05',
    notes: 'First visit. Cobb angle measured at 42°. Bracing recommended initially.'
  }
];