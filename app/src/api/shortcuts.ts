export type ShortcutConfig = {
  key: string;
  ctrlKey: boolean;
  description: string;
  action: string;
};

export const DEFAULT_SHORTCUTS: ShortcutConfig[] = [
  { key: 'e', ctrlKey: true, description: 'Go to Expenses', action: 'navigate:/expenses' },
  { key: 'b', ctrlKey: true, description: 'Go to Bills', action: 'navigate:/bills' },
  { key: 'd', ctrlKey: true, description: 'Go to Dashboard', action: 'navigate:/dashboard' },
  { key: 'k', ctrlKey: true, description: 'Open Search', action: 'open:search' },
  { key: 'Escape', ctrlKey: false, description: 'Close current dialog', action: 'close:modal' },
];
