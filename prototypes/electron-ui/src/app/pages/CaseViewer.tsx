import { TooltipSimple, TooltipProvider } from '../components/Tooltip';
import { useState } from 'react';
import { useParams, useNavigate } from 'react-router';
import { DesktopPage } from '../components/DesktopPage';
import { DisclosureButton } from '../components/DisclosureButton';
import { FolderTreeItem } from '../components/FolderTreeItem';
import { AnalysisControls } from '../components/AnalysisControls';
import { DropZone } from '../components/DropZone';
import { MediaViewport, type ViewportItem } from '../components/MediaViewport';
import { ImageWithFallback } from '../components/figma/ImageWithFallback';
import { mockPatients, Patient, procedureHistory } from '../data/mockData';
import { usePanelSize } from '../hooks/usePanelSize';
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '../components/ui/resizable';
import { 
  Search, Plus, User, Calendar, FileText, Trash2, ZoomIn, ZoomOut, 
  RotateCw, Maximize2, Info, Image as ImageIcon
} from 'lucide-react';

type ImageFile = {
  id: string;
  filename: string;
  type: 'CT' | 'MRI' | 'X-Ray';
  date: string;
  size: string;
  url?: string;
};

type ViewportImage = ViewportItem<ImageFile>;

type ViewportKey = 'ap' | 'frontal' | 'ct';

export default function CaseViewer() {
  const { patientId } = useParams();
  const navigate = useNavigate();
  const { leftPanelSize, updateLeftPanel, rightPanelSize, updateRightPanel } = usePanelSize();
  const [zoom, setZoom] = useState(100);
  const [rotation, setRotation] = useState(0);
  const [draggedFile, setDraggedFile] = useState<ImageFile | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);
  
  // Panel visibility states
  const [isLeftPanelOpen, setIsLeftPanelOpen] = useState(true);
  const [isRightPanelOpen, setIsRightPanelOpen] = useState(true);
  const [expandedProcedureId, setExpandedProcedureId] = useState<string | null>(null);
  const [showPatientBrowser, setShowPatientBrowser] = useState(!patientId);
  const [showPatientInfo, setShowPatientInfo] = useState(true);
  const [showProcedureHistory, setShowProcedureHistory] = useState(true);
  const [showImportImages, setShowImportImages] = useState(true);
  const [showImagesList, setShowImagesList] = useState(true);
  const [showImageInspector, setShowImageInspector] = useState(true);
  
  // State for the three viewports
  const [apView, setApView] = useState<ViewportImage>(null);
  const [frontalView, setFrontalView] = useState<ViewportImage>(null);
  const [ctView, setCtView] = useState<ViewportImage>(null);
  
  // Track selected viewport for inspector
  const [selectedViewport, setSelectedViewport] = useState<'ap' | 'frontal' | 'ct' | null>(null);

  const filteredPatients = mockPatients.filter(pat =>
    pat.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    pat.id.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const patient = patientId ? mockPatients.find(p => p.id === patientId) : selectedPatient;

  const handleZoomIn = () => setZoom(prev => Math.min(prev + 10, 400));
  const handleZoomOut = () => setZoom(prev => Math.max(prev - 10, 50));
  const handleRotate = () => setRotation(prev => (prev + 90) % 360);

  const inferImportedImageType = (file: File): ImageFile['type'] => {
    const lowerName = file.name.toLowerCase();
    const is2DImage = file.type.startsWith('image/') || /\.(png|jpe?g|bmp|gif|webp)$/i.test(file.name);
    const isStack = /(zstack|z-stack|stack|series|volume|slice)/.test(lowerName);

    if (is2DImage && !isStack) {
      return 'X-Ray';
    }

    if (/(mri|t1|t2|sag|axial)/.test(lowerName)) {
      return 'MRI';
    }

    if (/(ct|dcm|dicom|volume)/.test(lowerName)) {
      return 'CT';
    }

    return 'X-Ray';
  };

  const handleCreateCase = () => {
    setSelectedPatient(null);
    setApView(null);
    setFrontalView(null);
    setCtView(null);
    setSelectedViewport(null);
    navigate('/case');
  };

  // Image files state
  const [imageFiles, setImageFiles] = useState<ImageFile[]>([
    { id: '1', filename: 'thoracic_t2w_sag.dcm', type: 'MRI', date: '2026-03-15', size: '58.2 MB' },
    { id: '2', filename: 'lumbar_frontal.dcm', type: 'CT', date: '2026-03-01', size: '46.8 MB' },
    { id: '3', filename: 'spine_t2w_sag.dcm', type: 'MRI', date: '2026-02-18', size: '62.1 MB' },
    { id: '4', filename: 'standing_ap_xray.dcm', type: 'X-Ray', date: '2026-01-10', size: '12.4 MB' },
    { id: '5', filename: 'standing_lateral_xray.dcm', type: 'X-Ray', date: '2026-01-10', size: '11.8 MB' },
  ]);

  const handleFilesAdded = (files: File[]) => {
    const newFiles: ImageFile[] = files.map((file, index) => ({
      id: `new-${Date.now()}-${index}`,
      filename: file.name,
      type: inferImportedImageType(file),
      date: new Date().toISOString().split('T')[0],
      size: `${(file.size / (1024 * 1024)).toFixed(1)} MB`,
      url: URL.createObjectURL(file)
    }));

    setImageFiles(prev => [...newFiles, ...prev]);
  };

  const getTypeBadgeColor = (type: string) => {
    switch (type) {
      case 'CT': return 'bg-red-500/20 text-red-400 border-red-500/40';
      case 'MRI': return 'bg-blue-500/20 text-blue-400 border-blue-500/40';
      case 'X-Ray': return 'bg-orange-500/20 text-orange-400 border-orange-500/40';
      default: return 'bg-white/10 text-white/60';
    }
  };

  // Drag and drop handlers
  const handleDragStart = (file: ImageFile) => {
    setDraggedFile(file);
  };

  const handleDragEnd = () => {
    setDraggedFile(null);
  };

  const handleDrop = (viewport: 'ap' | 'frontal' | 'ct') => {
    if (draggedFile) {
      const imageData = { file: draggedFile, url: draggedFile.url };
      
      switch (viewport) {
        case 'ap':
          setApView(imageData);
          setSelectedViewport('ap');
          break;
        case 'frontal':
          setFrontalView(imageData);
          setSelectedViewport('frontal');
          break;
        case 'ct':
          setCtView(imageData);
          setSelectedViewport('ct');
          break;
      }
      
      setDraggedFile(null);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleViewportWheel = (viewport: ViewportKey, e: React.WheelEvent<HTMLDivElement>) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      setSelectedViewport(viewport);
      setZoom((prev) => {
        const delta = e.deltaY < 0 ? 10 : -10;
        return Math.min(400, Math.max(50, prev + delta));
      });
      return;
    }

    const container = e.currentTarget;
    const canScrollVertically = container.scrollHeight > container.clientHeight;
    const canScrollHorizontally = container.scrollWidth > container.clientWidth;

    if (!canScrollVertically && !canScrollHorizontally) {
      return;
    }

    e.preventDefault();
    setSelectedViewport(viewport);

    const horizontalDelta = e.shiftKey && e.deltaX === 0 ? e.deltaY : e.deltaX;
    container.scrollTop += e.deltaY;
    container.scrollLeft += horizontalDelta;
  };

  // Get the currently selected image for the inspector
  const getCurrentImage = (): ViewportImage => {
    switch (selectedViewport) {
      case 'ap': return apView;
      case 'frontal': return frontalView;
      case 'ct': return ctView;
      default: return null;
    }
  };

  const currentImage = getCurrentImage();
  const windowTitle = patient ? `SpineLab · ${patient.name}` : 'SpineLab · Case Browser';

  return (
    <TooltipProvider>
      <DesktopPage title={windowTitle} subtitle="Case intake, image review, and analysis staging">
        <div className="flex h-full overflow-hidden">
        <div className="app-content-surface flex-1 flex flex-col">
          <ResizablePanelGroup direction="horizontal" className="flex-1">
            {/* Left Panel */}
            {isLeftPanelOpen && (
              <>
                <ResizablePanel defaultSize={leftPanelSize || 22} minSize={15} maxSize={30} onResize={updateLeftPanel}>
                  <div className="app-sidebar-acrylic h-full border-r border-white/10 flex flex-col p-3">
                    {/* Patient Browser */}
                    {showPatientBrowser && (
                      <div className="app-panel-acrylic border border-white/10 rounded-xl mb-3">
                        <div className="px-3 py-2.5 flex items-center justify-between">
                          <h3 className="font-['SF_Pro',sans-serif] font-[590] text-[11px] leading-[14px] text-white/85 uppercase" style={{ fontVariationSettings: "'wdth' 100" }}>Patients</h3>
                          <DisclosureButton isOpen={showPatientBrowser} onClick={() => setShowPatientBrowser(!showPatientBrowser)} direction="down" />
                        </div>
                        <div className="px-3 pb-3 space-y-2">
                          <div className="relative">
                            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-white/35" />
                            <input
                              type="text"
                              placeholder="Search patients..."
                              value={searchQuery}
                              onChange={(e) => setSearchQuery(e.target.value)}
                              className="w-full rounded-lg border border-white/10 bg-[#1b1b1b] py-2 pl-9 pr-3 font-['SF_Pro',sans-serif] text-[12px] leading-[15px] text-white/85 placeholder:text-white/25 focus:border-white/20 focus:outline-none"
                              style={{ fontVariationSettings: "'wdth' 100" }}
                            />
                          </div>

                          <TooltipSimple content="Create a new patient case" side="bottom">
                            <button
                              onClick={handleCreateCase}
                              className="flex w-full items-center justify-center gap-2 rounded-lg border border-white/10 bg-[#1b1b1b] px-3 py-2 font-['SF_Pro',sans-serif] font-[590] text-[12px] leading-[15px] text-white/80 transition-colors hover:bg-[#222222] hover:text-white"
                              style={{ fontVariationSettings: "'wdth' 100" }}
                            >
                              <Plus className="h-4 w-4" />
                              New Case
                            </button>
                          </TooltipSimple>
                        </div>
                        <div className="mx-3 h-px bg-white/8" />
                        <div className="px-2 py-2 max-h-[200px] overflow-y-auto">
                          {filteredPatients.map((pat) => (
                            <FolderTreeItem
                              key={pat.id}
                              patient={pat}
                              isSelected={patient?.id === pat.id}
                              onClick={() => {
                                setSelectedPatient(pat);
                                if (patientId) navigate(`/case/${pat.id}`);
                              }}
                              onDoubleClick={() => navigate(`/case/${pat.id}`)}
                            />
                          ))}
                        </div>
                      </div>
                    )}
                    {!showPatientBrowser && (
                      <div className="app-panel-acrylic px-3 py-2.5 flex items-center justify-between border border-white/10 rounded-xl mb-3">
                        <h3 className="font-['SF_Pro',sans-serif] font-[590] text-[11px] leading-[14px] text-white/85 uppercase" style={{ fontVariationSettings: "'wdth' 100" }}>Patients</h3>
                        <DisclosureButton isOpen={showPatientBrowser} onClick={() => setShowPatientBrowser(!showPatientBrowser)} direction="down" />
                      </div>
                    )}

                    {/* Patient Information */}
                    {patient && (
                      <>
                        {showPatientInfo && (
                          <div className="app-panel-acrylic border border-white/10 rounded-xl mb-3">
                            <div className="px-3 py-2.5 flex items-center justify-between">
                              <h3 className="font-['SF_Pro',sans-serif] font-[590] text-[11px] leading-[14px] text-white/85 uppercase" style={{ fontVariationSettings: "'wdth' 100" }}>Patient Info</h3>
                              <DisclosureButton isOpen={showPatientInfo} onClick={() => setShowPatientInfo(!showPatientInfo)} direction="down" />
                            </div>
                            <div className="px-3 pb-3 space-y-2">
                              <div className="flex items-start gap-2">
                                <User className="w-3.5 h-3.5 text-white/40 mt-0.5" />
                                <div className="flex-1">
                                  <div className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55" style={{ fontVariationSettings: "'wdth' 100" }}>Name</div>
                                  <div className="font-['SF_Pro',sans-serif] font-[590] text-[12px] leading-[15px] text-white/85" style={{ fontVariationSettings: "'wdth' 100" }}>{patient.name}</div>
                                </div>
                              </div>
                              
                              <div className="flex items-start gap-2">
                                <Calendar className="w-3.5 h-3.5 text-white/40 mt-0.5" />
                                <div className="flex-1">
                                  <div className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55" style={{ fontVariationSettings: "'wdth' 100" }}>Age / Sex</div>
                                  <div className="font-['SF_Pro',sans-serif] font-[590] text-[12px] leading-[15px] text-white/85" style={{ fontVariationSettings: "'wdth' 100" }}>{patient.age} years / {patient.sex}</div>
                                </div>
                              </div>
                              
                              <div className="flex items-start gap-2">
                                <FileText className="w-3.5 h-3.5 text-white/40 mt-0.5" />
                                <div className="flex-1">
                                  <div className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55" style={{ fontVariationSettings: "'wdth' 100" }}>Patient ID</div>
                                  <div className="font-['SF_Pro',sans-serif] font-[590] text-[12px] leading-[15px] text-white/85" style={{ fontVariationSettings: "'wdth' 100" }}>{patient.id}</div>
                                </div>
                              </div>

                              <div className="flex items-start gap-2">
                                <FileText className="w-3.5 h-3.5 text-white/40 mt-0.5" />
                                <div className="flex-1">
                                  <div className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55" style={{ fontVariationSettings: "'wdth' 100" }}>Diagnosis</div>
                                  <div className="font-['SF_Pro',sans-serif] font-[590] text-[12px] leading-[15px] text-white/85" style={{ fontVariationSettings: "'wdth' 100" }}>{patient.diagnosis}</div>
                                </div>
                              </div>

                              {patient.cobbAngle && (
                                <div className="flex items-start gap-2">
                                  <FileText className="w-3.5 h-3.5 text-white/40 mt-0.5" />
                                  <div className="flex-1">
                                    <div className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55" style={{ fontVariationSettings: "'wdth' 100" }}>Cobb Angle</div>
                                    <div className="font-['SF_Pro',sans-serif] font-[590] text-[12px] leading-[15px] text-white/85" style={{ fontVariationSettings: "'wdth' 100" }}>{patient.cobbAngle}°</div>
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                        {!showPatientInfo && (
                          <div className="app-panel-acrylic px-3 py-2.5 flex items-center justify-between border border-white/10 rounded-xl mb-3">
                            <h3 className="font-['SF_Pro',sans-serif] font-[590] text-[11px] leading-[14px] text-white/85 uppercase" style={{ fontVariationSettings: "'wdth' 100" }}>Patient Info</h3>
                            <DisclosureButton isOpen={showPatientInfo} onClick={() => setShowPatientInfo(!showPatientInfo)} direction="down" />
                          </div>
                        )}

                        {/* Procedure History */}
                        {showProcedureHistory && (
                          <div className="app-panel-acrylic border border-white/10 rounded-xl mb-3">
                            <div className="px-3 py-2.5 flex items-center justify-between">
                              <h3 className="font-['SF_Pro',sans-serif] font-[590] text-[11px] leading-[14px] text-white/85 uppercase" style={{ fontVariationSettings: "'wdth' 100" }}>Procedure History</h3>
                              <DisclosureButton isOpen={showProcedureHistory} onClick={() => setShowProcedureHistory(!showProcedureHistory)} direction="down" />
                            </div>
                            <div className="px-3 pb-3 space-y-2">
                              {procedureHistory.map((proc) => (
                                <div key={proc.id} className="bg-[#2d2d2d] rounded-lg border border-white/10 overflow-hidden">
                                  <div 
                                    onClick={() => setExpandedProcedureId(expandedProcedureId === proc.id ? null : proc.id)}
                                    className="w-full px-3 py-2 flex items-center justify-between hover:bg-white/5 transition-colors cursor-pointer"
                                  >
                                    <div className="font-['SF_Pro',sans-serif] font-[590] text-[11px] leading-[14px] text-white/85" style={{ fontVariationSettings: "'wdth' 100" }}>{proc.type}</div>
                                    <DisclosureButton 
                                      isOpen={expandedProcedureId === proc.id} 
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        setExpandedProcedureId(expandedProcedureId === proc.id ? null : proc.id);
                                      }}
                                      direction="down" 
                                    />
                                  </div>
                                  
                                  {expandedProcedureId === proc.id && (
                                    <div className="px-3 pb-3 pt-1 space-y-2 border-t border-white/5 bg-black/10">
                                      <div>
                                        <div className="text-[9px] uppercase tracking-wider text-white/30 font-bold mb-0.5">Surgeon</div>
                                        <div className="text-[11px] text-white/70 font-medium">{proc.surgeon}</div>
                                      </div>
                                      <div>
                                        <div className="text-[9px] uppercase tracking-wider text-white/30 font-bold mb-0.5">Facility</div>
                                        <div className="text-[11px] text-white/70 font-medium">{proc.facility}</div>
                                      </div>
                                      <div>
                                        <div className="text-[9px] uppercase tracking-wider text-white/30 font-bold mb-0.5">Date</div>
                                        <div className="text-[11px] text-white/70 font-medium">{proc.date}</div>
                                      </div>
                                      <div>
                                        <div className="text-[9px] uppercase tracking-wider text-white/30 font-bold mb-0.5">Clinical Notes</div>
                                        <div className="text-[11px] text-white/60 leading-relaxed italic">{proc.notes}</div>
                                      </div>
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {!showProcedureHistory && (
                          <div className="app-panel-acrylic px-3 py-2.5 flex items-center justify-between border border-white/10 rounded-xl mb-3">
                            <h3 className="font-['SF_Pro',sans-serif] font-[590] text-[11px] leading-[14px] text-white/85 uppercase" style={{ fontVariationSettings: "'wdth' 100" }}>Procedure History</h3>
                            <DisclosureButton isOpen={showProcedureHistory} onClick={() => setShowProcedureHistory(!showProcedureHistory)} direction="down" />
                          </div>
                        )}

                        {/* Import Images */}
                        {showImportImages && (
                          <div className="app-panel-acrylic border border-white/10 rounded-xl mb-3">
                            <div className="px-3 py-2.5 flex items-center justify-between">
                              <h3 className="font-['SF_Pro',sans-serif] font-[590] text-[11px] leading-[14px] text-white/85 uppercase" style={{ fontVariationSettings: "'wdth' 100" }}>Import Images</h3>
                              <DisclosureButton isOpen={showImportImages} onClick={() => setShowImportImages(!showImportImages)} direction="down" />
                            </div>
                            <div className="px-3 pb-3">
                              <DropZone onFilesAdded={handleFilesAdded} />
                            </div>
                          </div>
                        )}
                        {!showImportImages && (
                          <div className="app-panel-acrylic px-3 py-2.5 flex items-center justify-between border border-white/10 rounded-xl mb-3">
                            <h3 className="font-['SF_Pro',sans-serif] font-[590] text-[11px] leading-[14px] text-white/85 uppercase" style={{ fontVariationSettings: "'wdth' 100" }}>Import Images</h3>
                            <DisclosureButton isOpen={showImportImages} onClick={() => setShowImportImages(!showImportImages)} direction="down" />
                          </div>
                        )}

                        {/* Images List */}
                        {showImagesList && (
                          <div className="app-panel-acrylic flex-1 overflow-y-auto border border-white/10 rounded-xl">
                            <div className="px-3 py-2.5 flex items-center justify-between border-b border-white/10">
                              <h3 className="font-['SF_Pro',sans-serif] font-[590] text-[11px] leading-[14px] text-white/85 uppercase" style={{ fontVariationSettings: "'wdth' 100" }}>Images ({imageFiles.length})</h3>
                              <DisclosureButton isOpen={showImagesList} onClick={() => setShowImagesList(!showImagesList)} direction="down" />
                            </div>
                            <div className="px-3 py-3 space-y-2">
                              {imageFiles.map((file) => (
                                <div
                                  key={file.id}
                                  draggable
                                  onDragStart={() => handleDragStart(file)}
                                  onDragEnd={handleDragEnd}
                                  className="group p-2 bg-[#2d2d2d] hover:bg-[#353535] rounded-lg border border-white/10 hover:border-white/20 transition-all cursor-grab active:cursor-grabbing"
                                >
                                  <div className="flex items-center gap-2">
                                    <div className="w-8 h-8 bg-black/30 rounded-md flex items-center justify-center shrink-0 overflow-hidden border border-white/10">
                                      {file.url ? (
                                        <ImageWithFallback 
                                          src={file.url} 
                                          className="w-full h-full object-cover" 
                                          alt={file.filename}
                                        />
                                      ) : (
                                        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" className="text-white/40">
                                          <path d="M9 1H3.5C2.67 1 2 1.67 2 2.5V13.5C2 14.33 2.67 15 3.5 15H12.5C13.33 15 14 14.33 14 13.5V6L9 1Z" stroke="currentColor" strokeWidth="1.5" fill="none"/>
                                          <path d="M9 1V6H14" stroke="currentColor" strokeWidth="1.5" fill="none"/>
                                        </svg>
                                      )}
                                    </div>

                                    <div className="flex-1 min-w-0">
                                      <div className="font-['SF_Pro',sans-serif] font-normal text-[10px] leading-[13px] text-white/85 truncate mb-0.5" style={{ fontVariationSettings: "'wdth' 100" }}>
                                        {file.filename}
                                      </div>
                                      <div className="flex items-center gap-1.5 flex-wrap">
                                        <span className={`font-['SF_Pro',sans-serif] font-[510] text-[10px] leading-[13px] px-1.5 py-0.5 rounded border whitespace-nowrap ${getTypeBadgeColor(file.type)}`} style={{ fontVariationSettings: "'wdth' 100" }}>
                                          {file.type}
                                        </span>
                                        <span className="font-['SF_Pro',sans-serif] font-normal text-[10px] leading-[13px] text-white/25 whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>{file.date}</span>
                                      </div>
                                    </div>

                                    <TooltipSimple content="Remove Image" side="left">
                                      <button className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-white/10 transition-opacity">
                                        <Trash2 className="w-3.5 h-3.5 text-white/40 hover:text-red-400" />
                                      </button>
                                    </TooltipSimple>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {!showImagesList && (
                          <div className="app-panel-acrylic px-3 py-2.5 flex items-center justify-between border border-white/10 rounded-xl">
                            <h3 className="font-['SF_Pro',sans-serif] font-[590] text-[11px] leading-[14px] text-white/85 uppercase" style={{ fontVariationSettings: "'wdth' 100" }}>Images ({imageFiles.length})</h3>
                            <DisclosureButton isOpen={showImagesList} onClick={() => setShowImagesList(!showImagesList)} direction="down" />
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </ResizablePanel>
                <ResizableHandle withHandle />
              </>
            )}

            {/* Center Panel - Image Viewport */}
            <ResizablePanel defaultSize={isLeftPanelOpen && isRightPanelOpen ? 100 - (leftPanelSize || 22) - (rightPanelSize || 22) : isLeftPanelOpen ? 100 - (leftPanelSize || 22) : isRightPanelOpen ? 100 - (rightPanelSize || 22) : 100} minSize={40}>
              <div className="h-full flex flex-col">
                {/* Disclosure Button for Left Panel */}
                {!isLeftPanelOpen && (
                  <div className="absolute left-0 top-1/2 -translate-y-1/2 z-10 pl-2">
                    <DisclosureButton isOpen={isLeftPanelOpen} onClick={() => setIsLeftPanelOpen(true)} direction="right" />
                  </div>
                )}

                {/* Toolbar */}
                <div className="app-topbar-acrylic px-3 py-2.5 border-b border-white/10 flex items-center justify-between relative">
                  <div className="flex items-center gap-4">
                    <TooltipSimple content={isLeftPanelOpen ? "Hide Sidebar" : "Show Sidebar"} side="bottom">
                      <button
                        onClick={() => setIsLeftPanelOpen(!isLeftPanelOpen)}
                        className="p-1.5 rounded-md hover:bg-white/10 text-white/55 hover:text-white/85 transition-colors font-['SF_Pro',sans-serif] text-[18px] leading-none"
                      >
                        􀱤
                      </button>
                    </TooltipSimple>
                    
                    <div className="flex items-center gap-2">
                      <TooltipSimple content="Zoom Out" side="bottom">
                        <button
                          onClick={handleZoomOut}
                          className="p-1.5 rounded-md bg-white/5 hover:bg-white/10 text-white/55 hover:text-white/85 transition-colors"
                        >
                          <ZoomOut className="w-3.5 h-3.5" />
                        </button>
                      </TooltipSimple>

                      <span className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55 min-w-[50px] text-center" style={{ fontVariationSettings: "'wdth' 100" }}>{zoom}%</span>
                      
                      <TooltipSimple content="Zoom In" side="bottom">
                        <button
                          onClick={handleZoomIn}
                          className="p-1.5 rounded-md bg-white/5 hover:bg-white/10 text-white/55 hover:text-white/85 transition-colors"
                        >
                          <ZoomIn className="w-3.5 h-3.5" />
                        </button>
                      </TooltipSimple>
                      
                      <div className="w-px h-5 bg-white/10 mx-1" />
                      
                      <TooltipSimple content="Rotate View" side="bottom">
                        <button
                          onClick={handleRotate}
                          className="p-1.5 rounded-md bg-white/5 hover:bg-white/10 text-white/55 hover:text-white/85 transition-colors"
                        >
                          <RotateCw className="w-3.5 h-3.5" />
                        </button>
                      </TooltipSimple>
                      
                      <TooltipSimple content="Fullscreen" side="bottom">
                        <button
                          className="p-1.5 rounded-md bg-white/5 hover:bg-white/10 text-white/55 hover:text-white/85 transition-colors"
                        >
                          <Maximize2 className="w-3.5 h-3.5" />
                        </button>
                      </TooltipSimple>
                    </div>
                  </div>

                </div>

                {/* Image Viewport - 3 Block Layout */}
                <div className="flex-1 bg-black/40 p-3 relative">
                  {/* Floating Toggle Buttons when sidebar is hidden */}
                  {!isLeftPanelOpen && (
                    <div className="absolute left-4 top-4 z-50 flex flex-col gap-2">
                      <TooltipSimple content="Show Sidebar" side="right">
                        <button
                          onClick={() => setIsLeftPanelOpen(true)}
                          className="p-1.5 rounded-md bg-[#2d2d2d]/80 backdrop-blur border border-white/10 text-white/55 hover:text-white/85 transition-colors font-['SF_Pro',sans-serif] text-[18px] leading-none shadow-lg"
                        >
                          􀱤
                        </button>
                      </TooltipSimple>
                    </div>
                  )}

                  {patient ? (
                    <ResizablePanelGroup direction="horizontal" className="h-full">
                      {/* Left Side - AP and Frontal X-rays */}
                      <ResizablePanel defaultSize={50} minSize={30}>
                        <div className="h-full pr-1.5">
                          <ResizablePanelGroup direction="vertical">
                            {/* AP X-Ray */}
                            <ResizablePanel defaultSize={50} minSize={25}>
                              <div className="h-full pb-1.5 flex flex-col">
                                <MediaViewport
                                  item={apView}
                                  label="AP"
                                  viewport="ap"
                                  rotation={rotation}
                                  zoom={zoom}
                                  isSelected={selectedViewport === 'ap'}
                                  onSelect={setSelectedViewport}
                                  onDrop={handleDrop}
                                  onDragOver={handleDragOver}
                                  onWheel={handleViewportWheel}
                                  getTypeBadgeColor={getTypeBadgeColor}
                                />
                              </div>
                            </ResizablePanel>

                            <ResizableHandle withHandle />

                            {/* Frontal X-Ray */}
                            <ResizablePanel defaultSize={50} minSize={25}>
                              <div className="h-full pt-1.5 flex flex-col">
                                <MediaViewport
                                  item={frontalView}
                                  label="Frontal"
                                  viewport="frontal"
                                  rotation={rotation}
                                  zoom={zoom}
                                  isSelected={selectedViewport === 'frontal'}
                                  onSelect={setSelectedViewport}
                                  onDrop={handleDrop}
                                  onDragOver={handleDragOver}
                                  onWheel={handleViewportWheel}
                                  getTypeBadgeColor={getTypeBadgeColor}
                                />
                              </div>
                            </ResizablePanel>
                          </ResizablePanelGroup>
                        </div>
                      </ResizablePanel>

                      <ResizableHandle withHandle />

                      {/* Right Side - CT Scan */}
                      <ResizablePanel defaultSize={50} minSize={30}>
                        <div className="h-full pl-1.5 flex flex-col">
                          <MediaViewport
                            item={ctView}
                            label="CT"
                            viewport="ct"
                            rotation={rotation}
                            zoom={zoom}
                            isSelected={selectedViewport === 'ct'}
                            onSelect={setSelectedViewport}
                            onDrop={handleDrop}
                            onDragOver={handleDragOver}
                            onWheel={handleViewportWheel}
                            getTypeBadgeColor={getTypeBadgeColor}
                          />
                        </div>
                      </ResizablePanel>
                    </ResizablePanelGroup>
                  ) : (
                    <div className="h-full flex items-center justify-center">
                      <div className="text-center">
                        <div className="font-['SF_Pro',sans-serif] font-[590] text-[15px] leading-[19px] text-white/85 mb-2" style={{ fontVariationSettings: "'wdth' 100" }}>Select a patient to view images</div>
                        <div className="font-['SF_Pro',sans-serif] font-normal text-[12px] leading-[15px] text-white/55" style={{ fontVariationSettings: "'wdth' 100" }}>Choose from the patient browser or create a new case</div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </ResizablePanel>

            {/* Right Panel - Image Inspector */}
            {isRightPanelOpen && (
              <>
                <ResizableHandle withHandle />
                <ResizablePanel defaultSize={rightPanelSize || 22} minSize={15} maxSize={30} onResize={updateRightPanel}>
                  <div className="app-sidebar-acrylic h-full border-l border-white/10 flex flex-col p-3">
                    {/* Image Inspector */}
                    {showImageInspector && (
                      <div className="app-panel-acrylic flex-1 overflow-y-auto border border-white/10 rounded-xl mb-3">
                        <div className="px-3 py-2.5 flex items-center justify-between border-b border-white/10">
                          <h3 className="font-['SF_Pro',sans-serif] font-[590] text-[11px] leading-[14px] text-white/85 uppercase" style={{ fontVariationSettings: "'wdth' 100" }}>Image Inspector</h3>
                          <DisclosureButton isOpen={showImageInspector} onClick={() => setShowImageInspector(!showImageInspector)} direction="down" />
                        </div>
                        
                        {currentImage ? (
                          <div className="px-3 pb-3 pt-3 space-y-3">
                            {/* Image Preview */}
                            {currentImage.url && (
                              <div className="w-full aspect-square bg-black/30 rounded-lg overflow-hidden border border-white/10">
                                <ImageWithFallback 
                                  src={currentImage.url} 
                                  className="w-full h-full object-cover" 
                                  alt={currentImage.file.filename}
                                />
                              </div>
                            )}

                            {/* Viewport Info */}
                            <div className="pb-2 border-b border-white/10">
                              <div className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55 mb-1" style={{ fontVariationSettings: "'wdth' 100" }}>Viewport</div>
                              <div className="font-['SF_Pro',sans-serif] font-[590] text-[12px] leading-[15px] text-white/85 uppercase" style={{ fontVariationSettings: "'wdth' 100" }}>
                                {selectedViewport === 'ap' ? 'AP' : selectedViewport === 'frontal' ? 'Frontal' : 'CT'}
                              </div>
                            </div>

                            {/* Filename */}
                            <div className="flex items-start gap-2">
                              <FileText className="w-3.5 h-3.5 text-white/40 mt-0.5" />
                              <div className="flex-1">
                                <div className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55" style={{ fontVariationSettings: "'wdth' 100" }}>Filename</div>
                                <div className="font-['SF_Pro',sans-serif] font-[590] text-[12px] leading-[15px] text-white/85 break-all" style={{ fontVariationSettings: "'wdth' 100" }}>{currentImage.file.filename}</div>
                              </div>
                            </div>

                            {/* Modality */}
                            <div className="flex items-start gap-2">
                              <ImageIcon className="w-3.5 h-3.5 text-white/40 mt-0.5" />
                              <div className="flex-1">
                                <div className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55" style={{ fontVariationSettings: "'wdth' 100" }}>Modality</div>
                                <span className={`font-['SF_Pro',sans-serif] font-[510] text-[11px] leading-[14px] px-2 py-0.5 rounded border inline-block mt-1 ${getTypeBadgeColor(currentImage.file.type)}`} style={{ fontVariationSettings: "'wdth' 100" }}>
                                  {currentImage.file.type}
                                </span>
                              </div>
                            </div>

                            {/* Date */}
                            <div className="flex items-start gap-2">
                              <Calendar className="w-3.5 h-3.5 text-white/40 mt-0.5" />
                              <div className="flex-1">
                                <div className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55" style={{ fontVariationSettings: "'wdth' 100" }}>Acquisition Date</div>
                                <div className="font-['SF_Pro',sans-serif] font-[590] text-[12px] leading-[15px] text-white/85" style={{ fontVariationSettings: "'wdth' 100" }}>{currentImage.file.date}</div>
                              </div>
                            </div>

                            {/* File Size */}
                            <div className="flex items-start gap-2">
                              <Info className="w-3.5 h-3.5 text-white/40 mt-0.5" />
                              <div className="flex-1">
                                <div className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55" style={{ fontVariationSettings: "'wdth' 100" }}>File Size</div>
                                <div className="font-['SF_Pro',sans-serif] font-[590] text-[12px] leading-[15px] text-white/85" style={{ fontVariationSettings: "'wdth' 100" }}>{currentImage.file.size}</div>
                              </div>
                            </div>

                            {/* Format */}
                            <div className="flex items-start gap-2">
                              <FileText className="w-3.5 h-3.5 text-white/40 mt-0.5" />
                              <div className="flex-1">
                                <div className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55" style={{ fontVariationSettings: "'wdth' 100" }}>Format</div>
                                <div className="font-['SF_Pro',sans-serif] font-[590] text-[12px] leading-[15px] text-white/85" style={{ fontVariationSettings: "'wdth' 100" }}>DICOM</div>
                              </div>
                            </div>

                            {/* Resolution */}
                            <div className="flex items-start gap-2">
                              <Maximize2 className="w-3.5 h-3.5 text-white/40 mt-0.5" />
                              <div className="flex-1">
                                <div className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55" style={{ fontVariationSettings: "'wdth' 100" }}>Resolution</div>
                                <div className="font-['SF_Pro',sans-serif] font-[590] text-[12px] leading-[15px] text-white/85" style={{ fontVariationSettings: "'wdth' 100" }}>1024 × 1024</div>
                              </div>
                            </div>

                            {/* Scale */}
                            <div className="flex items-start gap-2">
                              <ZoomIn className="w-3.5 h-3.5 text-white/40 mt-0.5" />
                              <div className="flex-1">
                                <div className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/55" style={{ fontVariationSettings: "'wdth' 100" }}>Scale</div>
                                <div className="font-['SF_Pro',sans-serif] font-[590] text-[12px] leading-[15px] text-white/85" style={{ fontVariationSettings: "'wdth' 100" }}>1:1</div>
                              </div>
                            </div>
                          </div>
                        ) : (
                          <div className="px-3 py-8 text-center">
                            <ImageIcon className="w-8 h-8 text-white/20 mx-auto mb-2" />
                            <div className="font-['SF_Pro',sans-serif] font-normal text-[11px] leading-[14px] text-white/40" style={{ fontVariationSettings: "'wdth' 100" }}>
                              Select an image to view details
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                    {!showImageInspector && (
                      <div className="app-panel-acrylic px-3 py-2.5 flex items-center justify-between border border-white/10 rounded-xl mb-3">
                        <h3 className="font-['SF_Pro',sans-serif] font-[590] text-[11px] leading-[14px] text-white/85 uppercase" style={{ fontVariationSettings: "'wdth' 100" }}>Image Inspector</h3>
                        <DisclosureButton isOpen={showImageInspector} onClick={() => setShowImageInspector(!showImageInspector)} direction="down" />
                      </div>
                    )}

                    {/* Analysis Controls */}
                    {patient && (
                      <div className="app-panel-acrylic border border-white/10 rounded-xl p-3">
                        <AnalysisControls patientId={patient.id} />
                      </div>
                    )}
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
