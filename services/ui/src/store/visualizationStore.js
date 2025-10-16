import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export const useVisualizationStore = create(
  persist(
    (set, get) => ({
      pinnedVisualizations: [],

      pinVisualization: (visualization) => {
        set((state) => ({
          pinnedVisualizations: [...state.pinnedVisualizations, visualization]
        }));
      },

      unpinVisualization: (vizId) => {
        set((state) => ({
          pinnedVisualizations: state.pinnedVisualizations.filter(v => v.id !== vizId)
        }));
      },

      clearAllPinned: () => {
        set({ pinnedVisualizations: [] });
      },

      isPinned: (vizId) => {
        return get().pinnedVisualizations.some(v => v.id === vizId);
      }
    }),
    {
      name: 'visualization-storage',
      version: 1
    }
  )
);
