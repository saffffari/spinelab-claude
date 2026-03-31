import { useCallback, useState } from 'react';
import { Upload } from 'lucide-react';

interface DropZoneProps {
  onFilesAdded: (files: File[]) => void;
  accept?: string;
  title?: string;
  subtitle?: string;
}

export function DropZone({
  onFilesAdded,
  accept = 'image/*,.dcm',
  title = 'Drop medical images',
  subtitle = 'or click to browse',
}: DropZoneProps) {
  const [isDragging, setIsDragging] = useState(false);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDragIn = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDragging(true);
    }
  }, []);

  const handleDragOut = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = Array.from(e.dataTransfer.files);
    if (files && files.length > 0) {
      onFilesAdded(files);
    }
  }, [onFilesAdded]);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) {
      onFilesAdded(files);
    }
  }, [onFilesAdded]);

  return (
    <div
      onDrag={handleDrag}
      onDragEnter={handleDragIn}
      onDragLeave={handleDragOut}
      onDragOver={handleDrag}
      onDrop={handleDrop}
      className={`
        relative border-2 border-dashed rounded-lg p-2 text-center transition-all
        ${isDragging 
          ? 'border-white/30 bg-white/10' 
          : 'border-white/20 bg-white/5 hover:border-white/30 hover:bg-white/10'
        }
      `}
    >
      <input
        type="file"
        id="file-input"
        multiple
        accept={accept}
        onChange={handleFileInput}
        className="hidden"
      />
      
      <label htmlFor="file-input" className="cursor-pointer block">
        <Upload className={`w-6 h-6 mx-auto mb-1 ${isDragging ? 'text-white/65' : 'text-white/40'}`} />
        <p className="font-['SF_Pro',sans-serif] font-[590] text-[11px] leading-[14px] text-white/85 mb-0.5" style={{ fontVariationSettings: "'wdth' 100" }}>
          {isDragging ? 'Drop files here' : title}
        </p>
        <p className="font-['SF_Pro',sans-serif] font-normal text-[10px] leading-[13px] text-white/55" style={{ fontVariationSettings: "'wdth' 100" }}>
          {subtitle}
        </p>
      </label>
    </div>
  );
}
