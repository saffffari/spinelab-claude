import { ChevronRight } from 'lucide-react';

interface DisclosureButtonProps {
  isOpen: boolean;
  onClick: (e?: React.MouseEvent) => void;
  direction?: 'left' | 'right' | 'up' | 'down';
}

export function DisclosureButton({ isOpen, onClick, direction = 'left' }: DisclosureButtonProps) {
  // Use a base chevron and rotate it based on direction and isOpen state
  const getRotation = () => {
    switch (direction) {
      case 'left':
        return isOpen ? 'rotate-180' : 'rotate-0';
      case 'right':
        return isOpen ? 'rotate-180' : 'rotate-0';
      case 'up':
        return isOpen ? '-rotate-90' : 'rotate-0';
      case 'down':
        // Standard macOS disclosure: Right (0) -> Down (90)
        return isOpen ? 'rotate-90' : 'rotate-0';
      default:
        return 'rotate-0';
    }
  };

  return (
    <button
      onClick={onClick}
      className="content-stretch relative flex size-4 flex-col items-center justify-center overflow-clip rounded-full bg-white/10 transition-colors hover:bg-white/15"
      data-name="Disclosure Button"
    >
      <ChevronRight className={`h-3 w-3 text-white/85 transition-transform duration-200 ${getRotation()}`} />
    </button>
  );
}
