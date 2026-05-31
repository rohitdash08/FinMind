import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type WidgetType = 'spending' | 'savings' | 'trends' | 'budget' | 'summary' | 'categories';

export type Widget = {
  id: string;
  type: WidgetType;
  title: string;
  visible: boolean;
  order: number;
  cols: 1 | 2 | 3 | 4;
};

type WidgetState = {
  widgets: Widget[];
  editMode: boolean;
  addWidget: (type: WidgetType, title: string) => void;
  removeWidget: (id: string) => void;
  toggleVisibility: (id: string) => void;
  setEditMode: (mode: boolean) => void;
  reorder: (ids: string[]) => void;
  resizeWidget: (id: string, cols: 1 | 2 | 3 | 4) => void;
  resetDefaults: () => void;
};

const DEFAULT_WIDGETS: Widget[] = [
  { id: 'w-summary', type: 'summary', title: 'Summary Metrics', visible: true, order: 0, cols: 4 },
  { id: 'w-spending', type: 'spending', title: 'Spending Overview', visible: true, order: 1, cols: 2 },
  { id: 'w-budget', type: 'budget', title: 'Budget Status', visible: true, order: 2, cols: 2 },
  { id: 'w-savings', type: 'savings', title: 'Savings Progress', visible: true, order: 3, cols: 2 },
  { id: 'w-trends', type: 'trends', title: 'Trends', visible: true, order: 4, cols: 2 },
  { id: 'w-categories', type: 'categories', title: 'Category Breakdown', visible: true, order: 5, cols: 2 },
];

export const useWidgets = create<WidgetState>()(
  persist(
    (set) => ({
      widgets: DEFAULT_WIDGETS,
      editMode: false,

      addWidget: (type, title) =>
        set((state) => ({
          widgets: [
            ...state.widgets,
            {
              id: `w-${type}-${Date.now()}`,
              type,
              title,
              visible: true,
              order: state.widgets.length,
              cols: 2,
            },
          ],
        })),

      removeWidget: (id) =>
        set((state) => ({
          widgets: state.widgets.filter((w) => w.id !== id),
        })),

      toggleVisibility: (id) =>
        set((state) => ({
          widgets: state.widgets.map((w) =>
            w.id === id ? { ...w, visible: !w.visible } : w,
          ),
        })),

      setEditMode: (mode) => set({ editMode: mode }),

      reorder: (ids) =>
        set((state) => {
          const reordered = ids
            .map((id, idx) => {
              const w = state.widgets.find((x) => x.id === id);
              return w ? { ...w, order: idx } : null;
            })
            .filter(Boolean) as Widget[];
          const notListed = state.widgets.filter((w) => !ids.includes(w.id));
          return {
            widgets: [...reordered, ...notListed].map((w, i) => ({
              ...w,
              order: i,
            })),
          };
        }),

      resizeWidget: (id, cols) =>
        set((state) => ({
          widgets: state.widgets.map((w) =>
            w.id === id ? { ...w, cols } : w,
          ),
        })),

      resetDefaults: () => set({ widgets: DEFAULT_WIDGETS }),
    }),
    { name: 'finmind-widgets' },
  ),
);
