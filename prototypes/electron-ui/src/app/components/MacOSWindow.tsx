import { ReactNode } from 'react';
import { WindowsTitleBar } from './WindowsTitleBar';

interface MacOSWindowProps {
  title: string;
  children: ReactNode;
  subtitle?: string;
  onClose?: () => void;
  onMinimize?: () => void;
  onMaximize?: () => void;
}

export function MacOSWindow({
  title,
  subtitle,
  children,
  onClose,
  onMinimize,
  onMaximize,
}: MacOSWindowProps) {
  return (
    <div className="app-window-root relative flex h-full flex-col overflow-hidden border border-[var(--app-shell-border)]">
      <div className="pointer-events-none absolute inset-0 border border-[var(--app-shell-border-soft)]" />

      <WindowsTitleBar
        title={title}
        subtitle={subtitle}
        onClose={onClose}
        onMinimize={onMinimize}
        onMaximize={onMaximize}
      />

      <div className="app-window-content relative flex-1 overflow-hidden">
        {children}
      </div>
    </div>
  );
}
