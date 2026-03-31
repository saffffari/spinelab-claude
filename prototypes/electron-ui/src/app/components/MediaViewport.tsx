import { ImageWithFallback } from './figma/ImageWithFallback';

export interface ViewportFileDescriptor {
  filename: string;
  type: string;
  url?: string;
}

export type ViewportItem<T extends ViewportFileDescriptor = ViewportFileDescriptor> = {
  file: T;
  url?: string;
} | null;

interface MediaViewportProps<T extends ViewportFileDescriptor = ViewportFileDescriptor> {
  item: ViewportItem<T>;
  label: string;
  viewport: string;
  rotation: number;
  zoom: number;
  isSelected: boolean;
  onSelect: (viewport: string) => void;
  onDrop: (viewport: string) => void;
  onDragOver: (e: React.DragEvent) => void;
  onWheel: (viewport: string, e: React.WheelEvent<HTMLDivElement>) => void;
  getTypeBadgeColor: (type: string) => string;
}

export function MediaViewport<T extends ViewportFileDescriptor = ViewportFileDescriptor>({
  item,
  label,
  viewport,
  rotation,
  zoom,
  isSelected,
  onSelect,
  onDrop,
  onDragOver,
  onWheel,
  getTypeBadgeColor,
}: MediaViewportProps<T>) {
  const scrollScale = Math.max(zoom, 100);

  return (
    <div
      onClick={() => item && onSelect(viewport)}
      className={`flex-1 bg-black/60 rounded-xl border ${
        isSelected && item
          ? 'border-white/30 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]'
          : 'border-white/10 hover:border-white/30'
      } transition-colors relative overflow-hidden ${item ? 'cursor-pointer' : ''}`}
      onDrop={() => onDrop(viewport)}
      onDragOver={onDragOver}
    >
      <div className="absolute top-3 left-3 z-10 px-2 py-1 bg-black/60 rounded-md text-xs font-medium text-white/60 border border-white/10">
        {label}
      </div>

      {item ? (
        item.url ? (
          <div
            className="h-full w-full overflow-auto p-3"
            onWheel={(e) => onWheel(viewport, e)}
          >
            <div className="flex min-h-full min-w-full items-center justify-center">
              <div
                className="flex items-center justify-center"
                style={{
                  width: `${scrollScale}%`,
                  height: `${scrollScale}%`,
                  minWidth: '100%',
                  minHeight: '100%',
                }}
              >
                <ImageWithFallback
                  src={item.url}
                  className="h-full w-full object-contain"
                  alt={`${label} View`}
                  style={{ transform: `rotate(${rotation}deg)`, transformOrigin: 'center center' }}
                />
              </div>
            </div>
          </div>
        ) : (
          <div className="w-full h-full flex items-center justify-center overflow-hidden p-3">
            <div className="text-center">
              <div className="text-sm text-white/60 mb-1">{item.file.filename}</div>
              <div className={`text-xs px-2 py-0.5 rounded inline-block border ${getTypeBadgeColor(item.file.type)}`}>
                {item.file.type}
              </div>
            </div>
          </div>
        )
      ) : null}
    </div>
  );
}
