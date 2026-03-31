import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Copy, Minus, X } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router';
import {
  Menubar,
  MenubarContent,
  MenubarItem,
  MenubarMenu,
  MenubarSeparator,
  MenubarShortcut,
  MenubarTrigger,
} from './ui/menubar';
import { SpineLabMark } from './SpineLabMark';

type DesktopWindowState = {
  isDesktop: boolean;
  isMaximized: boolean;
  platform: string;
};

interface WindowsTitleBarProps {
  title: string;
  subtitle?: string;
  onClose?: () => void;
  onMinimize?: () => void;
  onMaximize?: () => void;
}

const defaultState: DesktopWindowState = {
  isDesktop: false,
  isMaximized: false,
  platform: 'web',
};

function WindowControlButton({
  ariaLabel,
  onClick,
  disabled,
  variant = 'default',
  children,
}: {
  ariaLabel: string;
  onClick: () => void;
  disabled?: boolean;
  variant?: 'default' | 'close';
  children: ReactNode;
}) {
  return (
    <button
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={onClick}
      className={`app-no-drag flex h-10 w-[46px] items-center justify-center border-l border-white/5 text-slate-300/85 transition-colors ${
        variant === 'close'
          ? 'hover:bg-[#c42b1c] hover:text-white'
          : 'hover:bg-white/8 hover:text-white'
      } ${disabled ? 'cursor-default opacity-45' : ''}`}
      type="button"
    >
      {children}
    </button>
  );
}

export function WindowsTitleBar({
  title,
  subtitle,
  onClose,
  onMinimize,
  onMaximize,
}: WindowsTitleBarProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const [windowState, setWindowState] = useState<DesktopWindowState>(defaultState);

  useEffect(() => {
    let dispose = () => {};

    window.desktop?.window
      .getState()
      .then(setWindowState)
      .catch(() => undefined);

    if (window.desktop?.window) {
      dispose = window.desktop.window.onStateChange((state) => {
        setWindowState(state);
      });
    }

    return () => dispose();
  }, []);

  const pathSegments = useMemo(() => location.pathname.split('/').filter(Boolean), [location.pathname]);
  const currentWorkspace = pathSegments[0] ?? 'case';
  const currentPatientId = pathSegments[1];

  const resolveWorkspacePath = (workspace: 'case' | 'measurement' | 'report') => {
    if (workspace === 'case') {
      return currentPatientId ? `/case/${currentPatientId}` : '/case';
    }

    if (!currentPatientId) {
      return null;
    }

    return `/${workspace}/${currentPatientId}`;
  };

  const navigateTo = (path: string) => {
    navigate(path);
  };

  const minimizeWindow = () => {
    if (onMinimize) {
      onMinimize();
      return;
    }

    window.desktop?.window.minimize();
  };

  const maximizeWindow = () => {
    if (onMaximize) {
      onMaximize();
      return;
    }

    window.desktop?.window.toggleMaximize();
  };

  const closeWindow = () => {
    if (onClose) {
      onClose();
      return;
    }

    window.desktop?.window.close();
  };

  const controlsDisabled = !window.desktop && !onClose && !onMinimize && !onMaximize;
  const menuTriggerClass =
    'rounded-md px-2.5 py-1 text-[12px] font-medium text-white/70 outline-none transition-colors hover:bg-white/8 hover:text-white focus:bg-white/8 data-[state=open]:bg-white/10 data-[state=open]:text-white';
  const menuContentClass =
    'min-w-[190px] rounded-xl border border-white/10 bg-[#202020] p-1.5 text-white shadow-[0_18px_48px_rgba(0,0,0,0.45)] backdrop-blur-xl';
  const menuItemClass =
    'rounded-lg px-2.5 py-2 text-[12px] font-medium text-white/80 focus:bg-white/8 focus:text-white data-[highlighted]:bg-white/8 data-[highlighted]:text-white';
  const workspaceTabs = [
    { id: 'case', label: 'Import', path: resolveWorkspacePath('case') },
    { id: 'measurement', label: 'Measurement', path: resolveWorkspacePath('measurement') },
    { id: 'report', label: 'Report', path: resolveWorkspacePath('report') },
  ] as const;

  return (
    <div
      className="app-drag-region app-topbar-acrylic relative flex h-12 shrink-0 items-center justify-between border-b border-white/10 pl-1.5"
      onDoubleClick={maximizeWindow}
    >
      <div className="flex min-w-0 items-center gap-2 pr-4">
        <div className="app-no-drag flex h-8 w-8 items-center justify-center text-zinc-100">
          <SpineLabMark />
        </div>

        <div className="app-no-drag">
          <Menubar className="h-auto gap-0 border-0 bg-transparent p-0 shadow-none">
            <MenubarMenu>
              <MenubarTrigger className={menuTriggerClass}>File</MenubarTrigger>
              <MenubarContent className={menuContentClass}>
                <MenubarItem className={menuItemClass} onSelect={() => navigateTo('/case')}>
                  New Case
                  <MenubarShortcut>Ctrl+N</MenubarShortcut>
                </MenubarItem>
                <MenubarItem className={menuItemClass} onSelect={() => window.location.reload()}>
                  Reload UI
                  <MenubarShortcut>Ctrl+R</MenubarShortcut>
                </MenubarItem>
                <MenubarSeparator className="my-1 bg-white/10" />
                <MenubarItem className={menuItemClass} onSelect={closeWindow}>
                  Close Window
                  <MenubarShortcut>Alt+F4</MenubarShortcut>
                </MenubarItem>
              </MenubarContent>
            </MenubarMenu>

            <MenubarMenu>
              <MenubarTrigger className={menuTriggerClass}>Edit</MenubarTrigger>
              <MenubarContent className={menuContentClass}>
                <MenubarItem className={menuItemClass} disabled>
                  Undo
                  <MenubarShortcut>Ctrl+Z</MenubarShortcut>
                </MenubarItem>
                <MenubarItem className={menuItemClass} disabled>
                  Redo
                  <MenubarShortcut>Ctrl+Y</MenubarShortcut>
                </MenubarItem>
              </MenubarContent>
            </MenubarMenu>

            <MenubarMenu>
              <MenubarTrigger className={menuTriggerClass}>View</MenubarTrigger>
              <MenubarContent className={menuContentClass}>
                <MenubarItem className={menuItemClass} onSelect={() => navigateTo(resolveWorkspacePath('case') ?? '/case')}>
                  Import Workspace
                </MenubarItem>
                <MenubarItem
                  className={menuItemClass}
                  disabled={!currentPatientId}
                  onSelect={() => {
                    const path = resolveWorkspacePath('measurement');
                    if (path) {
                      navigateTo(path);
                    }
                  }}
                >
                  Measurement Workspace
                </MenubarItem>
                <MenubarItem
                  className={menuItemClass}
                  disabled={!currentPatientId}
                  onSelect={() => {
                    const path = resolveWorkspacePath('report');
                    if (path) {
                      navigateTo(path);
                    }
                  }}
                >
                  Report Workspace
                </MenubarItem>
                <MenubarItem className={menuItemClass} onSelect={maximizeWindow}>
                  {windowState.isMaximized ? 'Restore Window' : 'Maximize Window'}
                </MenubarItem>
              </MenubarContent>
            </MenubarMenu>

            <MenubarMenu>
              <MenubarTrigger className={menuTriggerClass}>Window</MenubarTrigger>
              <MenubarContent className={menuContentClass}>
                <MenubarItem className={menuItemClass} onSelect={minimizeWindow}>
                  Minimize
                </MenubarItem>
                <MenubarItem className={menuItemClass} onSelect={maximizeWindow}>
                  {windowState.isMaximized ? 'Restore' : 'Maximize'}
                </MenubarItem>
              </MenubarContent>
            </MenubarMenu>

            <MenubarMenu>
              <MenubarTrigger className={menuTriggerClass}>Help</MenubarTrigger>
              <MenubarContent className={menuContentClass}>
                <MenubarItem className={menuItemClass} disabled>
                  SpineLab Desktop
                  <MenubarShortcut>{subtitle ?? 'Preview'}</MenubarShortcut>
                </MenubarItem>
                <MenubarSeparator className="my-1 bg-white/10" />
                <MenubarItem className={menuItemClass} disabled>
                  Python backend hook ready
                </MenubarItem>
              </MenubarContent>
            </MenubarMenu>
          </Menubar>
        </div>

        <div className="app-no-drag ml-2 flex items-center gap-1 rounded-xl bg-black/10 p-1">
          {workspaceTabs.map((tab) => {
            const isActive = currentWorkspace === tab.id;
            const isDisabled = !tab.path;

            return (
              <button
                key={tab.id}
                type="button"
                disabled={isDisabled}
                onClick={() => {
                  if (tab.path) {
                    navigateTo(tab.path);
                  }
                }}
                className={`rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors ${
                  isActive
                    ? 'bg-[#343434] text-white'
                    : isDisabled
                      ? 'cursor-default text-white/25'
                      : 'text-white/58 hover:bg-white/8 hover:text-white/85'
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="pointer-events-none absolute left-1/2 top-1/2 hidden min-w-0 max-w-[36rem] -translate-x-1/2 -translate-y-1/2 truncate text-[12px] font-medium tracking-[0.01em] text-zinc-300/70 lg:block">
        {title}
      </div>

      <div className="flex h-full items-stretch">
        <WindowControlButton ariaLabel="Minimize window" disabled={controlsDisabled} onClick={minimizeWindow}>
          <Minus className="h-4 w-4" strokeWidth={1.8} />
        </WindowControlButton>
        <WindowControlButton ariaLabel="Maximize window" disabled={controlsDisabled} onClick={maximizeWindow}>
          {windowState.isMaximized ? (
            <Copy className="h-3.5 w-3.5" strokeWidth={1.8} />
          ) : (
            <div className="h-3.5 w-3.5 border border-current" />
          )}
        </WindowControlButton>
        <WindowControlButton
          ariaLabel="Close window"
          disabled={controlsDisabled}
          onClick={closeWindow}
          variant="close"
        >
          <X className="h-4 w-4" strokeWidth={1.8} />
        </WindowControlButton>
      </div>
    </div>
  );
}
