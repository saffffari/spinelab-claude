import { useState, useEffect } from 'react';

const STORAGE_KEY = 'spinelab-panel-sizes';

interface PanelSizes {
  leftPanel: number;
  rightPanel?: number;
}

const DEFAULT_SIZES: PanelSizes = {
  leftPanel: 10,
  rightPanel: 12,
};

export function usePanelSize() {
  const [sizes, setSizes] = useState<PanelSizes>(() => {
    if (typeof window === 'undefined') return DEFAULT_SIZES;
    
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        return { ...DEFAULT_SIZES, ...JSON.parse(stored) };
      } catch {
        return DEFAULT_SIZES;
      }
    }
    return DEFAULT_SIZES;
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sizes));
  }, [sizes]);

  const updateLeftPanel = (size: number) => {
    setSizes(prev => ({ ...prev, leftPanel: size }));
  };

  const updateRightPanel = (size: number) => {
    setSizes(prev => ({ ...prev, rightPanel: size }));
  };

  return {
    leftPanelSize: sizes.leftPanel,
    rightPanelSize: sizes.rightPanel,
    updateLeftPanel,
    updateRightPanel,
  };
}
