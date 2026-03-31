import { ReactNode, useEffect } from 'react';
import { MacOSWindow } from './MacOSWindow';

interface DesktopPageProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
}

export function DesktopPage({ title, subtitle, children }: DesktopPageProps) {
  useEffect(() => {
    document.title = title;
  }, [title]);

  return (
    <div className="h-screen w-screen overflow-hidden bg-[var(--app-shell-bg)]">
      <div className="h-full w-full">
        <MacOSWindow title={title} subtitle={subtitle}>
          {children}
        </MacOSWindow>
      </div>
    </div>
  );
}
