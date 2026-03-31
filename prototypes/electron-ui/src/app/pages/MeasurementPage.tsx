import { useState, type DragEvent, type WheelEvent } from 'react';
import { useNavigate, useParams } from 'react-router';
import {
  ArrowLeft,
  Box,
  Calendar,
  Eraser,
  FileText,
  Info,
  Maximize2,
  MousePointer2,
  PenTool,
  Redo2,
  RotateCw,
  Ruler,
  Search,
  Trash2,
  Undo2,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { TooltipSimple, TooltipProvider } from '../components/Tooltip';
import { DesktopPage } from '../components/DesktopPage';
import { DisclosureButton } from '../components/DisclosureButton';
import { FolderTreeItem } from '../components/FolderTreeItem';
import { DropZone } from '../components/DropZone';
import { MediaViewport, type ViewportItem } from '../components/MediaViewport';
import { ImageWithFallback } from '../components/figma/ImageWithFallback';
import { mockAnalytics, mockPatients, procedureHistory, type Analytics, type Patient } from '../data/mockData';
import { usePanelSize } from '../hooks/usePanelSize';
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '../components/ui/resizable';

type Tool = 'select' | 'measure' | 'annotate' | 'erase';
type ViewportKey = 'ap' | 'frontal' | 'ct';
type ModelType = 'Mesh' | 'Segmentation' | 'Volume';
type ModelFormat = 'GLB' | 'OBJ' | 'PLY' | 'STL';

type ModelFile = {
  id: string;
  filename: string;
  type: ModelType;
  date: string;
  size: string;
  format: ModelFormat;
  url?: string;
};

type ViewportModel = ViewportItem<ModelFile>;

const viewportTitles: Record<ViewportKey, string> = {
  ap: 'Coronal',
  frontal: 'Sagittal',
  ct: 'Axial',
};

const createModelPreview = (label: string, detail: string) => {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="720" height="720" viewBox="0 0 720 720">
      <rect width="720" height="720" fill="#131313" />
      <rect x="28" y="28" width="664" height="664" rx="28" fill="#1c1c1c" stroke="#383838" />
      <path d="M198 246 360 164 522 246 522 472 360 556 198 472Z" fill="none" stroke="#858585" stroke-width="10" stroke-linejoin="round" />
      <path d="M360 164 360 556" fill="none" stroke="#6f6f6f" stroke-width="8" />
      <path d="M198 246 360 338 522 246" fill="none" stroke="#969696" stroke-width="8" stroke-linejoin="round" />
      <path d="M198 472 360 386 522 472" fill="none" stroke="#5f5f5f" stroke-width="8" stroke-linejoin="round" />
      <circle cx="360" cy="360" r="124" fill="none" stroke="#474747" stroke-width="6" stroke-dasharray="16 14" />
      <text x="64" y="620" fill="#f5f5f5" font-family="Segoe UI, Arial, sans-serif" font-size="44" font-weight="700">${label}</text>
      <text x="64" y="664" fill="#9a9a9a" font-family="Segoe UI, Arial, sans-serif" font-size="26">${detail}</text>
    </svg>
  `;

  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
};

const defaultModelFiles: ModelFile[] = [
  {
    id: 'model-1',
    filename: 'coronal_surface.glb',
    type: 'Mesh',
    date: '2026-03-18',
    size: '26.4 MB',
    format: 'GLB',
    url: createModelPreview('Coronal Model', 'Processed surface mesh'),
  },
  {
    id: 'model-2',
    filename: 'sagittal_reconstruction.glb',
    type: 'Mesh',
    date: '2026-03-18',
    size: '24.1 MB',
    format: 'GLB',
    url: createModelPreview('Sagittal Model', 'Processed sagittal mesh'),
  },
  {
    id: 'model-3',
    filename: 'axial_segmentation.ply',
    type: 'Segmentation',
    date: '2026-03-19',
    size: '18.8 MB',
    format: 'PLY',
    url: createModelPreview('Axial Model', 'Segmented vertebral anatomy'),
  },
  {
    id: 'model-4',
    filename: 'vertebral_volume.obj',
    type: 'Volume',
    date: '2026-03-19',
    size: '31.2 MB',
    format: 'OBJ',
    url: createModelPreview('Volume Study', 'Reconstructed 3D volume'),
  },
];

const buildFallbackAnalytics = (patient: Patient): Analytics => {
  const cobbAngle = patient.cobbAngle ?? 32;

  return {
    cobbAngle,
    apicalVertebra: patient.apicalVertebra ?? 'T8',
    thoracicCurve: cobbAngle,
    lumbarCurve: Math.max(12, Math.round(cobbAngle * 0.45)),
    vertebralRotation: 12,
    risserSign: 3,
  };
};

export default function MeasurementPage() {
  const { patientId } = useParams();
  const navigate = useNavigate();
  const { leftPanelSize, updateLeftPanel, rightPanelSize, updateRightPanel } = usePanelSize();
  const [zoom, setZoom] = useState(100);
  const [rotation, setRotation] = useState(0);
  const [draggedModel, setDraggedModel] = useState<ModelFile | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);
  const [selectedTool, setSelectedTool] = useState<Tool>('measure');
  const [isLeftPanelOpen, setIsLeftPanelOpen] = useState(true);
  const [isRightPanelOpen, setIsRightPanelOpen] = useState(true);
  const [expandedProcedureId, setExpandedProcedureId] = useState<string | null>(null);
  const [showPatientBrowser, setShowPatientBrowser] = useState(!patientId);
  const [showPatientInfo, setShowPatientInfo] = useState(true);
  const [showProcedureHistory, setShowProcedureHistory] = useState(true);
  const [showImportModels, setShowImportModels] = useState(true);
  const [showModelsList, setShowModelsList] = useState(true);
  const [showModelInspector, setShowModelInspector] = useState(true);
  const [apView, setApView] = useState<ViewportModel>({
    file: defaultModelFiles[0],
    url: defaultModelFiles[0].url,
  });
  const [frontalView, setFrontalView] = useState<ViewportModel>({
    file: defaultModelFiles[1],
    url: defaultModelFiles[1].url,
  });
  const [ctView, setCtView] = useState<ViewportModel>({
    file: defaultModelFiles[2],
    url: defaultModelFiles[2].url,
  });
  const [selectedViewport, setSelectedViewport] = useState<ViewportKey | null>('ct');
  const [modelFiles, setModelFiles] = useState<ModelFile[]>(defaultModelFiles);

  const patient = patientId ? mockPatients.find((entry) => entry.id === patientId) : selectedPatient;
  const analytics = patient ? mockAnalytics[patient.id] ?? buildFallbackAnalytics(patient) : null;

  const filteredPatients = mockPatients.filter((entry) => {
    const query = searchQuery.toLowerCase();
    return entry.name.toLowerCase().includes(query) || entry.id.toLowerCase().includes(query);
  });

  const centerPanelSize = isLeftPanelOpen && isRightPanelOpen
    ? 100 - (leftPanelSize || 22) - (rightPanelSize || 22)
    : isLeftPanelOpen
      ? 100 - (leftPanelSize || 22)
      : isRightPanelOpen
        ? 100 - (rightPanelSize || 22)
        : 100;

  const handleZoomIn = () => setZoom((previous) => Math.min(previous + 10, 400));
  const handleZoomOut = () => setZoom((previous) => Math.max(previous - 10, 50));
  const handleRotate = () => setRotation((previous) => (previous + 90) % 360);

  const inferModelMeta = (file: File): { type: ModelType; format: ModelFormat } => {
    const lowerName = file.name.toLowerCase();

    if (lowerName.endsWith('.ply')) {
      return { type: 'Segmentation', format: 'PLY' };
    }

    if (lowerName.endsWith('.obj')) {
      return { type: 'Volume', format: 'OBJ' };
    }

    if (lowerName.endsWith('.stl')) {
      return { type: 'Mesh', format: 'STL' };
    }

    return { type: 'Mesh', format: 'GLB' };
  };

  const getTypeBadgeColor = (type: ModelType) => {
    switch (type) {
      case 'Mesh':
        return 'bg-[#2b2b2b] text-white/80 border-white/10';
      case 'Segmentation':
        return 'bg-[#332a22] text-[#d8b48a] border-[#6a5a48]';
      case 'Volume':
        return 'bg-[#24312d] text-[#9bc9bc] border-[#4a6c63]';
      default:
        return 'bg-white/10 text-white/70 border-white/10';
    }
  };

  const handleBackToImport = () => {
    if (patient) {
      navigate(`/case/${patient.id}`);
      return;
    }

    navigate('/case');
  };

  const handleFilesAdded = (files: File[]) => {
    const newModels = files.map((file, index) => {
      const { type, format } = inferModelMeta(file);
      const name = file.name.replace(/\.[^.]+$/, '');
      return {
        id: `model-${Date.now()}-${index}`,
        filename: file.name,
        type,
        date: new Date().toISOString().split('T')[0],
        size: `${(file.size / (1024 * 1024)).toFixed(1)} MB`,
        format,
        url: createModelPreview(name.slice(0, 22) || 'Imported Model', `${type} ${format}`),
      };
    });

    setModelFiles((previous) => [...newModels, ...previous]);
  };

  const handleDragStart = (file: ModelFile) => setDraggedModel(file);
  const handleDragEnd = () => setDraggedModel(null);

  const handleViewportDrop = (viewport: ViewportKey) => {
    if (!draggedModel) {
      return;
    }

    const nextModel = { file: draggedModel, url: draggedModel.url };

    if (viewport === 'ap') {
      setApView(nextModel);
    }

    if (viewport === 'frontal') {
      setFrontalView(nextModel);
    }

    if (viewport === 'ct') {
      setCtView(nextModel);
    }

    setSelectedViewport(viewport);
    setDraggedModel(null);
  };

  const handleDragOver = (event: DragEvent) => {
    event.preventDefault();
  };

  const handleViewportWheel = (viewport: ViewportKey, event: WheelEvent<HTMLDivElement>) => {
    if (event.ctrlKey || event.metaKey) {
      event.preventDefault();
      setSelectedViewport(viewport);
      setZoom((previous) => {
        const delta = event.deltaY < 0 ? 10 : -10;
        return Math.min(400, Math.max(50, previous + delta));
      });
      return;
    }

    const container = event.currentTarget;
    const canScrollVertically = container.scrollHeight > container.clientHeight;
    const canScrollHorizontally = container.scrollWidth > container.clientWidth;

    if (!canScrollVertically && !canScrollHorizontally) {
      return;
    }

    event.preventDefault();
    setSelectedViewport(viewport);
    container.scrollTop += event.deltaY;
    container.scrollLeft += event.shiftKey && event.deltaX === 0 ? event.deltaY : event.deltaX;
  };

  const handleRemoveModel = (fileId: string) => {
    setModelFiles((previous) => previous.filter((file) => file.id !== fileId));

    if (apView?.file.id === fileId) {
      setApView(null);
    }

    if (frontalView?.file.id === fileId) {
      setFrontalView(null);
    }

    if (ctView?.file.id === fileId) {
      setCtView(null);
    }

    if (
      (selectedViewport === 'ap' && apView?.file.id === fileId) ||
      (selectedViewport === 'frontal' && frontalView?.file.id === fileId) ||
      (selectedViewport === 'ct' && ctView?.file.id === fileId)
    ) {
      setSelectedViewport(null);
    }
  };

  const getCurrentModel = (): ViewportModel => {
    if (selectedViewport === 'ap') {
      return apView;
    }

    if (selectedViewport === 'frontal') {
      return frontalView;
    }

    if (selectedViewport === 'ct') {
      return ctView;
    }

    return null;
  };

  const currentModel = getCurrentModel();
  const toolButtons = [
    { id: 'select', label: 'Select', icon: MousePointer2 },
    { id: 'measure', label: 'Measure', icon: Ruler },
    { id: 'annotate', label: 'Annotate', icon: PenTool },
    { id: 'erase', label: 'Erase', icon: Eraser },
  ] as const;

  if (!patient || !analytics) {
    return (
      <DesktopPage title="SpineLab · Measurement" subtitle="Processed model measurement workspace">
        <div className="flex h-full items-center justify-center text-white/60">Loading measurement workspace...</div>
      </DesktopPage>
    );
  }

  const windowTitle = `SpineLab · Measurement · ${patient.name}`;

  return (
    <TooltipProvider>
      <DesktopPage title={windowTitle} subtitle="Processed model measurement workspace">
        <div className="flex h-full overflow-hidden">
          <div className="app-content-surface flex flex-1 flex-col">
            <ResizablePanelGroup direction="horizontal" className="flex-1">
              {isLeftPanelOpen && (
                <>
                  <ResizablePanel
                    defaultSize={leftPanelSize || 22}
                    minSize={15}
                    maxSize={30}
                    onResize={updateLeftPanel}
                  >
                    <div className="app-sidebar-acrylic flex h-full flex-col border-r border-white/10 p-3">
                      {showPatientBrowser ? (
                        <div className="app-panel-acrylic mb-3 rounded-xl border border-white/10">
                          <div className="flex items-center justify-between px-3 py-2.5">
                            <h3 className="font-['SF_Pro',sans-serif] text-[11px] font-[590] uppercase leading-[14px] text-white/85">
                              Patients
                            </h3>
                            <DisclosureButton
                              isOpen={showPatientBrowser}
                              onClick={() => setShowPatientBrowser(false)}
                              direction="down"
                            />
                          </div>
                          <div className="space-y-2 px-3 pb-3">
                            <div className="relative">
                              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-white/35" />
                              <input
                                type="text"
                                placeholder="Search patients..."
                                value={searchQuery}
                                onChange={(event) => setSearchQuery(event.target.value)}
                                className="w-full rounded-lg border border-white/10 bg-[#1b1b1b] py-2 pl-9 pr-3 text-[12px] leading-[15px] text-white/85 placeholder:text-white/25 focus:border-white/20 focus:outline-none"
                              />
                            </div>
                            <TooltipSimple content="Return to the import workspace" side="bottom">
                              <button
                                onClick={handleBackToImport}
                                className="flex w-full items-center justify-center gap-2 rounded-lg border border-white/10 bg-[#1b1b1b] px-3 py-2 text-[12px] font-[590] leading-[15px] text-white/80 transition-colors hover:bg-[#222222] hover:text-white"
                              >
                                <ArrowLeft className="h-4 w-4" />
                                Back to Import
                              </button>
                            </TooltipSimple>
                          </div>
                          <div className="mx-3 h-px bg-white/8" />
                          <div className="max-h-[200px] px-2 py-2">
                            <div className="max-h-[184px] overflow-y-auto">
                              {filteredPatients.map((entry) => (
                                <FolderTreeItem
                                  key={entry.id}
                                  patient={entry}
                                  isSelected={patient.id === entry.id}
                                  onClick={() => {
                                    setSelectedPatient(entry);
                                    navigate(`/measurement/${entry.id}`);
                                  }}
                                  onDoubleClick={() => navigate(`/measurement/${entry.id}`)}
                                />
                              ))}
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="app-panel-acrylic mb-3 flex items-center justify-between rounded-xl border border-white/10 px-3 py-2.5">
                          <h3 className="font-['SF_Pro',sans-serif] text-[11px] font-[590] uppercase leading-[14px] text-white/85">
                            Patients
                          </h3>
                          <DisclosureButton
                            isOpen={showPatientBrowser}
                            onClick={() => setShowPatientBrowser(true)}
                            direction="down"
                          />
                        </div>
                      )}

                      {showPatientInfo ? (
                        <div className="app-panel-acrylic mb-3 rounded-xl border border-white/10">
                          <div className="flex items-center justify-between px-3 py-2.5">
                            <h3 className="font-['SF_Pro',sans-serif] text-[11px] font-[590] uppercase leading-[14px] text-white/85">
                              Patient Info
                            </h3>
                            <DisclosureButton
                              isOpen={showPatientInfo}
                              onClick={() => setShowPatientInfo(false)}
                              direction="down"
                            />
                          </div>
                          <div className="space-y-2 px-3 pb-3">
                            <div className="flex items-start gap-2">
                              <Info className="mt-0.5 h-3.5 w-3.5 text-white/40" />
                              <div className="flex-1">
                                <div className="text-[11px] leading-[14px] text-white/55">Name</div>
                                <div className="text-[12px] font-[590] leading-[15px] text-white/85">{patient.name}</div>
                              </div>
                            </div>
                            <div className="flex items-start gap-2">
                              <Calendar className="mt-0.5 h-3.5 w-3.5 text-white/40" />
                              <div className="flex-1">
                                <div className="text-[11px] leading-[14px] text-white/55">Age / Sex</div>
                                <div className="text-[12px] font-[590] leading-[15px] text-white/85">
                                  {patient.age} years / {patient.sex}
                                </div>
                              </div>
                            </div>
                            <div className="flex items-start gap-2">
                              <FileText className="mt-0.5 h-3.5 w-3.5 text-white/40" />
                              <div className="flex-1">
                                <div className="text-[11px] leading-[14px] text-white/55">Patient ID</div>
                                <div className="text-[12px] font-[590] leading-[15px] text-white/85">{patient.id}</div>
                              </div>
                            </div>
                            <div className="flex items-start gap-2">
                              <FileText className="mt-0.5 h-3.5 w-3.5 text-white/40" />
                              <div className="flex-1">
                                <div className="text-[11px] leading-[14px] text-white/55">Diagnosis</div>
                                <div className="text-[12px] font-[590] leading-[15px] text-white/85">{patient.diagnosis}</div>
                              </div>
                            </div>
                            <div className="flex items-start gap-2">
                              <Ruler className="mt-0.5 h-3.5 w-3.5 text-white/40" />
                              <div className="flex-1">
                                <div className="text-[11px] leading-[14px] text-white/55">Primary Cobb Angle</div>
                                <div className="text-[12px] font-[590] leading-[15px] text-white/85">{analytics.cobbAngle}°</div>
                              </div>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="app-panel-acrylic mb-3 flex items-center justify-between rounded-xl border border-white/10 px-3 py-2.5">
                          <h3 className="font-['SF_Pro',sans-serif] text-[11px] font-[590] uppercase leading-[14px] text-white/85">
                            Patient Info
                          </h3>
                          <DisclosureButton
                            isOpen={showPatientInfo}
                            onClick={() => setShowPatientInfo(true)}
                            direction="down"
                          />
                        </div>
                      )}

                      {showProcedureHistory ? (
                        <div className="app-panel-acrylic mb-3 rounded-xl border border-white/10">
                          <div className="flex items-center justify-between px-3 py-2.5">
                            <h3 className="font-['SF_Pro',sans-serif] text-[11px] font-[590] uppercase leading-[14px] text-white/85">
                              Procedure History
                            </h3>
                            <DisclosureButton
                              isOpen={showProcedureHistory}
                              onClick={() => setShowProcedureHistory(false)}
                              direction="down"
                            />
                          </div>
                          <div className="space-y-2 px-3 pb-3">
                            {procedureHistory.map((procedure) => (
                              <div key={procedure.id} className="overflow-hidden rounded-lg border border-white/10 bg-[#2d2d2d]">
                                <div
                                  onClick={() =>
                                    setExpandedProcedureId((current) =>
                                      current === procedure.id ? null : procedure.id,
                                    )
                                  }
                                  className="flex cursor-pointer items-center justify-between px-3 py-2 transition-colors hover:bg-white/5"
                                >
                                  <div className="text-[11px] font-[590] leading-[14px] text-white/85">{procedure.type}</div>
                                  <DisclosureButton
                                    isOpen={expandedProcedureId === procedure.id}
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      setExpandedProcedureId((current) =>
                                        current === procedure.id ? null : procedure.id,
                                      );
                                    }}
                                    direction="down"
                                  />
                                </div>
                                {expandedProcedureId === procedure.id && (
                                  <div className="space-y-2 border-t border-white/5 bg-black/10 px-3 pb-3 pt-1">
                                    <div>
                                      <div className="mb-0.5 text-[9px] uppercase tracking-wider text-white/30">Surgeon</div>
                                      <div className="text-[11px] text-white/70">{procedure.surgeon}</div>
                                    </div>
                                    <div>
                                      <div className="mb-0.5 text-[9px] uppercase tracking-wider text-white/30">Facility</div>
                                      <div className="text-[11px] text-white/70">{procedure.facility}</div>
                                    </div>
                                    <div>
                                      <div className="mb-0.5 text-[9px] uppercase tracking-wider text-white/30">Date</div>
                                      <div className="text-[11px] text-white/70">{procedure.date}</div>
                                    </div>
                                    <div>
                                      <div className="mb-0.5 text-[9px] uppercase tracking-wider text-white/30">Notes</div>
                                      <div className="text-[11px] text-white/60">{procedure.notes}</div>
                                    </div>
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : (
                        <div className="app-panel-acrylic mb-3 flex items-center justify-between rounded-xl border border-white/10 px-3 py-2.5">
                          <h3 className="font-['SF_Pro',sans-serif] text-[11px] font-[590] uppercase leading-[14px] text-white/85">
                            Procedure History
                          </h3>
                          <DisclosureButton
                            isOpen={showProcedureHistory}
                            onClick={() => setShowProcedureHistory(true)}
                            direction="down"
                          />
                        </div>
                      )}

                      {showImportModels ? (
                        <div className="app-panel-acrylic mb-3 rounded-xl border border-white/10">
                          <div className="flex items-center justify-between px-3 py-2.5">
                            <h3 className="font-['SF_Pro',sans-serif] text-[11px] font-[590] uppercase leading-[14px] text-white/85">
                              Import Models
                            </h3>
                            <DisclosureButton
                              isOpen={showImportModels}
                              onClick={() => setShowImportModels(false)}
                              direction="down"
                            />
                          </div>
                          <div className="px-3 pb-3">
                            <DropZone
                              onFilesAdded={handleFilesAdded}
                              accept=".glb,.gltf,.obj,.stl,.ply"
                              title="Drop processed models"
                              subtitle="or click to browse .glb, .obj, .ply, .stl"
                            />
                          </div>
                        </div>
                      ) : (
                        <div className="app-panel-acrylic mb-3 flex items-center justify-between rounded-xl border border-white/10 px-3 py-2.5">
                          <h3 className="font-['SF_Pro',sans-serif] text-[11px] font-[590] uppercase leading-[14px] text-white/85">
                            Import Models
                          </h3>
                          <DisclosureButton
                            isOpen={showImportModels}
                            onClick={() => setShowImportModels(true)}
                            direction="down"
                          />
                        </div>
                      )}

                      {showModelsList ? (
                        <div className="app-panel-acrylic min-h-0 flex-1 rounded-xl border border-white/10">
                          <div className="flex items-center justify-between px-3 py-2.5">
                            <h3 className="font-['SF_Pro',sans-serif] text-[11px] font-[590] uppercase leading-[14px] text-white/85">
                              Processed Models ({modelFiles.length})
                            </h3>
                            <DisclosureButton
                              isOpen={showModelsList}
                              onClick={() => setShowModelsList(false)}
                              direction="down"
                            />
                          </div>
                          <div className="max-h-[240px] space-y-2 overflow-y-auto px-3 pb-3">
                            {modelFiles.map((file) => (
                              <div
                                key={file.id}
                                draggable
                                onDragStart={() => handleDragStart(file)}
                                onDragEnd={handleDragEnd}
                                className={`group flex cursor-grab items-center gap-3 rounded-lg border px-2.5 py-2 transition-colors active:cursor-grabbing ${
                                  draggedModel?.id === file.id
                                    ? 'border-white/20 bg-white/10'
                                    : 'border-white/10 bg-[#232323] hover:bg-[#292929]'
                                }`}
                              >
                                <div className="h-12 w-12 shrink-0 overflow-hidden rounded-md border border-white/10 bg-black/20">
                                  {file.url ? (
                                    <ImageWithFallback
                                      src={file.url}
                                      className="h-full w-full object-cover"
                                      alt={file.filename}
                                    />
                                  ) : null}
                                </div>
                                <div className="min-w-0 flex-1">
                                  <div className="truncate text-[11px] font-[590] leading-[14px] text-white/85">
                                    {file.filename}
                                  </div>
                                  <div className="mt-1 flex items-center gap-2">
                                    <span
                                      className={`inline-flex rounded border px-2 py-0.5 text-[10px] font-[510] leading-[13px] ${getTypeBadgeColor(file.type)}`}
                                    >
                                      {file.type}
                                    </span>
                                    <span className="text-[10px] leading-[13px] text-white/25">{file.date}</span>
                                  </div>
                                </div>
                                <TooltipSimple content="Remove model" side="left">
                                  <button
                                    onClick={() => handleRemoveModel(file.id)}
                                    className="rounded p-1 opacity-0 transition-opacity hover:bg-white/10 group-hover:opacity-100"
                                  >
                                    <Trash2 className="h-3.5 w-3.5 text-white/40 hover:text-red-400" />
                                  </button>
                                </TooltipSimple>
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : (
                        <div className="app-panel-acrylic flex items-center justify-between rounded-xl border border-white/10 px-3 py-2.5">
                          <h3 className="font-['SF_Pro',sans-serif] text-[11px] font-[590] uppercase leading-[14px] text-white/85">
                            Processed Models ({modelFiles.length})
                          </h3>
                          <DisclosureButton
                            isOpen={showModelsList}
                            onClick={() => setShowModelsList(true)}
                            direction="down"
                          />
                        </div>
                      )}
                    </div>
                  </ResizablePanel>
                  <ResizableHandle withHandle />
                </>
              )}
              <ResizablePanel defaultSize={centerPanelSize} minSize={40}>
                <div className="flex h-full flex-col">
                  {!isLeftPanelOpen && (
                    <div className="absolute left-0 top-1/2 z-10 -translate-y-1/2 pl-2">
                      <DisclosureButton
                        isOpen={isLeftPanelOpen}
                        onClick={() => setIsLeftPanelOpen(true)}
                        direction="right"
                      />
                    </div>
                  )}

                  <div className="app-topbar-acrylic relative flex items-center justify-between border-b border-white/10 px-3 py-2.5">
                    <div className="flex items-center gap-4">
                      <TooltipSimple content={isLeftPanelOpen ? 'Hide Sidebar' : 'Show Sidebar'} side="bottom">
                        <button
                          onClick={() => setIsLeftPanelOpen((current) => !current)}
                          className="rounded-md p-1.5 text-[18px] leading-none text-white/55 transition-colors hover:bg-white/10 hover:text-white/85"
                        >
                          􀱤
                        </button>
                      </TooltipSimple>
                      <div className="flex items-center gap-2">
                        <TooltipSimple content="Zoom Out" side="bottom">
                          <button
                            onClick={handleZoomOut}
                            className="rounded-md bg-white/5 p-1.5 text-white/55 transition-colors hover:bg-white/10 hover:text-white/85"
                          >
                            <ZoomOut className="h-3.5 w-3.5" />
                          </button>
                        </TooltipSimple>
                        <span className="min-w-[50px] text-center text-[11px] leading-[14px] text-white/55">{zoom}%</span>
                        <TooltipSimple content="Zoom In" side="bottom">
                          <button
                            onClick={handleZoomIn}
                            className="rounded-md bg-white/5 p-1.5 text-white/55 transition-colors hover:bg-white/10 hover:text-white/85"
                          >
                            <ZoomIn className="h-3.5 w-3.5" />
                          </button>
                        </TooltipSimple>
                        <div className="mx-1 h-5 w-px bg-white/10" />
                        <TooltipSimple content="Rotate View" side="bottom">
                          <button
                            onClick={handleRotate}
                            className="rounded-md bg-white/5 p-1.5 text-white/55 transition-colors hover:bg-white/10 hover:text-white/85"
                          >
                            <RotateCw className="h-3.5 w-3.5" />
                          </button>
                        </TooltipSimple>
                        <TooltipSimple content="Fullscreen" side="bottom">
                          <button className="rounded-md bg-white/5 p-1.5 text-white/55 transition-colors hover:bg-white/10 hover:text-white/85">
                            <Maximize2 className="h-3.5 w-3.5" />
                          </button>
                        </TooltipSimple>
                      </div>
                    </div>
                  </div>

                  <div className="relative flex-1 bg-black/40 p-3">
                    {!isLeftPanelOpen && (
                      <div className="absolute left-4 top-4 z-50 flex flex-col gap-2">
                        <TooltipSimple content="Show Sidebar" side="right">
                          <button
                            onClick={() => setIsLeftPanelOpen(true)}
                            className="rounded-md border border-white/10 bg-[#2d2d2d] p-1.5 text-[18px] leading-none text-white/55 shadow-lg transition-colors hover:text-white/85"
                          >
                            􀱤
                          </button>
                        </TooltipSimple>
                      </div>
                    )}

                    <ResizablePanelGroup direction="horizontal" className="h-full">
                      <ResizablePanel defaultSize={50} minSize={30}>
                        <div className="h-full pr-1.5">
                          <ResizablePanelGroup direction="vertical">
                            <ResizablePanel defaultSize={50} minSize={25}>
                              <div className="flex h-full flex-col pb-1.5">
                                <MediaViewport
                                  item={apView}
                                  label="Coronal"
                                  viewport="ap"
                                  rotation={rotation}
                                  zoom={zoom}
                                  isSelected={selectedViewport === 'ap'}
                                  onSelect={(viewport) => setSelectedViewport(viewport as ViewportKey)}
                                  onDrop={(viewport) => handleViewportDrop(viewport as ViewportKey)}
                                  onDragOver={handleDragOver}
                                  onWheel={(viewport, event) => handleViewportWheel(viewport as ViewportKey, event)}
                                  getTypeBadgeColor={(type) => getTypeBadgeColor(type as ModelType)}
                                />
                              </div>
                            </ResizablePanel>
                            <ResizableHandle withHandle />
                            <ResizablePanel defaultSize={50} minSize={25}>
                              <div className="flex h-full flex-col pt-1.5">
                                <MediaViewport
                                  item={frontalView}
                                  label="Sagittal"
                                  viewport="frontal"
                                  rotation={rotation}
                                  zoom={zoom}
                                  isSelected={selectedViewport === 'frontal'}
                                  onSelect={(viewport) => setSelectedViewport(viewport as ViewportKey)}
                                  onDrop={(viewport) => handleViewportDrop(viewport as ViewportKey)}
                                  onDragOver={handleDragOver}
                                  onWheel={(viewport, event) => handleViewportWheel(viewport as ViewportKey, event)}
                                  getTypeBadgeColor={(type) => getTypeBadgeColor(type as ModelType)}
                                />
                              </div>
                            </ResizablePanel>
                          </ResizablePanelGroup>
                        </div>
                      </ResizablePanel>
                      <ResizableHandle withHandle />
                      <ResizablePanel defaultSize={50} minSize={30}>
                        <div className="flex h-full flex-col pl-1.5">
                          <MediaViewport
                            item={ctView}
                            label="Axial"
                            viewport="ct"
                            rotation={rotation}
                            zoom={zoom}
                            isSelected={selectedViewport === 'ct'}
                            onSelect={(viewport) => setSelectedViewport(viewport as ViewportKey)}
                            onDrop={(viewport) => handleViewportDrop(viewport as ViewportKey)}
                            onDragOver={handleDragOver}
                            onWheel={(viewport, event) => handleViewportWheel(viewport as ViewportKey, event)}
                            getTypeBadgeColor={(type) => getTypeBadgeColor(type as ModelType)}
                          />
                        </div>
                      </ResizablePanel>
                    </ResizablePanelGroup>
                  </div>
                </div>
              </ResizablePanel>
              {isRightPanelOpen && (
                <>
                  <ResizableHandle withHandle />
                  <ResizablePanel
                    defaultSize={rightPanelSize || 22}
                    minSize={15}
                    maxSize={30}
                    onResize={updateRightPanel}
                  >
                    <div className="app-sidebar-acrylic flex h-full flex-col border-l border-white/10 p-3">
                      {showModelInspector ? (
                        <div className="app-panel-acrylic mb-3 flex-1 overflow-y-auto rounded-xl border border-white/10">
                          <div className="flex items-center justify-between border-b border-white/10 px-3 py-2.5">
                            <h3 className="font-['SF_Pro',sans-serif] text-[11px] font-[590] uppercase leading-[14px] text-white/85">
                              Model Inspector
                            </h3>
                            <DisclosureButton
                              isOpen={showModelInspector}
                              onClick={() => setShowModelInspector(false)}
                              direction="down"
                            />
                          </div>
                          {currentModel ? (
                            <div className="space-y-3 px-3 pb-3 pt-3">
                              <div className="aspect-square overflow-hidden rounded-lg border border-white/10 bg-black/30">
                                {currentModel.url ? (
                                  <ImageWithFallback
                                    src={currentModel.url}
                                    className="h-full w-full object-cover"
                                    alt={currentModel.file.filename}
                                  />
                                ) : null}
                              </div>
                              <div className="border-b border-white/10 pb-2">
                                <div className="mb-1 text-[11px] leading-[14px] text-white/55">Viewport</div>
                                <div className="text-[12px] font-[590] uppercase leading-[15px] text-white/85">
                                  {selectedViewport ? viewportTitles[selectedViewport] : 'Unassigned'}
                                </div>
                              </div>
                              <div className="flex items-start gap-2">
                                <FileText className="mt-0.5 h-3.5 w-3.5 text-white/40" />
                                <div className="flex-1">
                                  <div className="text-[11px] leading-[14px] text-white/55">Filename</div>
                                  <div className="break-all text-[12px] font-[590] leading-[15px] text-white/85">
                                    {currentModel.file.filename}
                                  </div>
                                </div>
                              </div>
                              <div className="flex items-start gap-2">
                                <Box className="mt-0.5 h-3.5 w-3.5 text-white/40" />
                                <div className="flex-1">
                                  <div className="text-[11px] leading-[14px] text-white/55">Model Type</div>
                                  <span
                                    className={`mt-1 inline-block rounded border px-2 py-0.5 text-[11px] font-[510] leading-[14px] ${getTypeBadgeColor(currentModel.file.type)}`}
                                  >
                                    {currentModel.file.type}
                                  </span>
                                </div>
                              </div>
                              <div className="flex items-start gap-2">
                                <Calendar className="mt-0.5 h-3.5 w-3.5 text-white/40" />
                                <div className="flex-1">
                                  <div className="text-[11px] leading-[14px] text-white/55">Generated Date</div>
                                  <div className="text-[12px] font-[590] leading-[15px] text-white/85">
                                    {currentModel.file.date}
                                  </div>
                                </div>
                              </div>
                              <div className="flex items-start gap-2">
                                <Info className="mt-0.5 h-3.5 w-3.5 text-white/40" />
                                <div className="flex-1">
                                  <div className="text-[11px] leading-[14px] text-white/55">File Size</div>
                                  <div className="text-[12px] font-[590] leading-[15px] text-white/85">
                                    {currentModel.file.size}
                                  </div>
                                </div>
                              </div>
                              <div className="flex items-start gap-2">
                                <FileText className="mt-0.5 h-3.5 w-3.5 text-white/40" />
                                <div className="flex-1">
                                  <div className="text-[11px] leading-[14px] text-white/55">Format</div>
                                  <div className="text-[12px] font-[590] leading-[15px] text-white/85">
                                    {currentModel.file.format}
                                  </div>
                                </div>
                              </div>
                            </div>
                          ) : (
                            <div className="px-3 py-8 text-center">
                              <Box className="mx-auto mb-2 h-8 w-8 text-white/20" />
                              <div className="text-[11px] leading-[14px] text-white/40">
                                Select a processed model to view details
                              </div>
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="app-panel-acrylic mb-3 flex items-center justify-between rounded-xl border border-white/10 px-3 py-2.5">
                          <h3 className="font-['SF_Pro',sans-serif] text-[11px] font-[590] uppercase leading-[14px] text-white/85">
                            Model Inspector
                          </h3>
                          <DisclosureButton
                            isOpen={showModelInspector}
                            onClick={() => setShowModelInspector(true)}
                            direction="down"
                          />
                        </div>
                      )}

                      <div className="app-panel-acrylic rounded-xl border border-white/10 p-3">
                        <div className="mb-3 flex items-center justify-between">
                          <h3 className="font-['SF_Pro',sans-serif] text-[11px] font-[590] uppercase leading-[14px] text-white/85">
                            Measurement Tools
                          </h3>
                          <span className="text-[10px] leading-[13px] text-white/35">3D Model Workspace</span>
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          {toolButtons.map((tool) => {
                            const Icon = tool.icon;
                            const isActive = selectedTool === tool.id;

                            return (
                              <button
                                key={tool.id}
                                onClick={() => setSelectedTool(tool.id)}
                                className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-left transition-colors ${
                                  isActive
                                    ? 'border-white/20 bg-[rgba(255,255,255,0.12)] text-white'
                                    : 'border-white/10 bg-[#232323] text-white/65 hover:bg-[#292929] hover:text-white/85'
                                }`}
                              >
                                <Icon className="h-4 w-4" />
                                <span className="text-[11px] font-[590] leading-[14px]">{tool.label}</span>
                              </button>
                            );
                          })}
                        </div>
                        <div className="my-3 h-px bg-white/10" />
                        <div className="mb-3 flex items-center gap-2">
                          <button className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-white/10 bg-[#232323] px-3 py-2 text-[11px] font-[590] leading-[14px] text-white/70 transition-colors hover:bg-[#292929] hover:text-white">
                            <Undo2 className="h-4 w-4" />
                            Undo
                          </button>
                          <button className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-white/10 bg-[#232323] px-3 py-2 text-[11px] font-[590] leading-[14px] text-white/70 transition-colors hover:bg-[#292929] hover:text-white">
                            <Redo2 className="h-4 w-4" />
                            Redo
                          </button>
                        </div>
                        <div className="space-y-2">
                          <div className="rounded-lg border border-white/10 bg-[#232323] px-3 py-2.5">
                            <div className="text-[11px] leading-[14px] text-white/55">Primary Cobb Angle</div>
                            <div className="mt-1 text-[20px] font-[590] leading-[24px] text-white/90">
                              {analytics.cobbAngle}°
                            </div>
                          </div>
                          <div className="rounded-lg border border-white/10 bg-[#232323] px-3 py-2.5">
                            <div className="text-[11px] leading-[14px] text-white/55">Vertebral Rotation</div>
                            <div className="mt-1 text-[20px] font-[590] leading-[24px] text-white/90">
                              {analytics.vertebralRotation}°
                            </div>
                          </div>
                        </div>
                        <button
                          onClick={() => navigate(`/report/${patient.id}`)}
                          className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-white/10 bg-[#262626] px-4 py-2.5 text-[12px] font-[590] leading-[15px] text-white/85 transition-colors hover:bg-[#2d2d2d]"
                        >
                          <FileText className="h-4 w-4" />
                          Generate Report
                        </button>
                      </div>
                    </div>
                  </ResizablePanel>
                </>
              )}
            </ResizablePanelGroup>
          </div>
        </div>
      </DesktopPage>
    </TooltipProvider>
  );
}
