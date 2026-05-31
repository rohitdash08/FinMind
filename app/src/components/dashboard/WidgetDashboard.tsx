import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { useWidgets, type WidgetType } from '@/hooks/use-widgets';
import { WidgetCard } from './WidgetCard';
import { SpendingWidget } from './SpendingWidget';
import { BudgetWidget } from './BudgetWidget';
import { SavingsWidget } from './SavingsWidget';
import { TrendsWidget } from './TrendsWidget';
import {
  getDashboardSummary,
  type DashboardSummary,
} from '@/api/dashboard';
import {
  Settings,
  Eye,
  EyeOff,
  Plus,
  RotateCcw,
  Check,
  GripVertical,
} from 'lucide-react';

const WIDGET_NAMES: { value: WidgetType; label: string }[] = [
  { value: 'summary', label: 'Summary Metrics' },
  { value: 'spending', label: 'Spending Overview' },
  { value: 'budget', label: 'Budget Status' },
  { value: 'savings', label: 'Savings Progress' },
  { value: 'trends', label: 'Trends' },
  { value: 'categories', label: 'Category Breakdown' },
];

export function WidgetDashboard() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  const {
    widgets,
    editMode,
    setEditMode,
    toggleVisibility,
    removeWidget,
    addWidget,
    reorder,
    resetDefaults,
  } = useWidgets();

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const res = await getDashboardSummary(month);
        setData(res);
      } catch {
        setData(null);
      } finally {
        setLoading(false);
      }
    })();
  }, [month]);

  const visibleWidgets = widgets.filter((w) => w.visible || editMode).sort((a, b) => a.order - b.order);

  function renderWidgetContent(type: WidgetType) {
    switch (type) {
      case 'spending':
      case 'summary':
        return <SpendingWidget data={data} loading={loading} />;
      case 'budget':
        return <BudgetWidget data={data} loading={loading} />;
      case 'savings':
        return <SavingsWidget data={data} loading={loading} />;
      case 'trends':
      case 'categories':
        return <TrendsWidget data={data} loading={loading} />;
      default:
        return <div className="text-sm text-muted-foreground">Widget placeholder</div>;
    }
  }

  function handleDragStart(index: number) {
    setDragIndex(index);
  }

  function handleDragOver(e: React.DragEvent, index: number) {
    e.preventDefault();
    if (dragIndex === null || dragIndex === index) return;
    const items = [...visibleWidgets];
    const dragged = items[dragIndex];
    items.splice(dragIndex, 1);
    items.splice(index, 0, dragged);
    reorder(items.map((w) => w.id));
    setDragIndex(index);
  }

  function handleDragEnd() {
    setDragIndex(null);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <label className="sr-only" htmlFor="wd-month">Month</label>
          <input
            id="wd-month"
            type="month"
            className="input h-9 w-[160px]"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-2">
          {editMode ? (
            <>
              <Button variant="outline" size="sm" onClick={resetDefaults}>
                <RotateCcw className="w-4 h-4 mr-1" />
                Reset
              </Button>
              <Button variant="hero" size="sm" onClick={() => setEditMode(false)}>
                <Check className="w-4 h-4 mr-1" />
                Done
              </Button>
            </>
          ) : (
            <Button variant="outline" size="sm" onClick={() => setEditMode(true)}>
              <Settings className="w-4 h-4 mr-1" />
              Customize Widgets
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {visibleWidgets.map((widget, index) => (
          <div
            key={widget.id}
            className={
              widget.cols === 2
                ? 'md:col-span-2'
                : widget.cols === 3
                  ? 'md:col-span-3'
                  : widget.cols === 4
                    ? 'md:col-span-4'
                    : ''
            }
            draggable={editMode}
            onDragStart={() => handleDragStart(index)}
            onDragOver={(e) => handleDragOver(e, index)}
            onDragEnd={handleDragEnd}
          >
            <WidgetCard widget={widget}>{renderWidgetContent(widget.type)}</WidgetCard>
          </div>
        ))}
      </div>

      {editMode && (
        <div className="card p-4">
          <h3 className="text-sm font-semibold mb-3">Add Widget</h3>
          <div className="flex flex-wrap gap-2">
            {WIDGET_NAMES.map((w) => {
              const alreadyAdded = widgets.some((x) => x.type === w.value);
              return (
                <Button
                  key={w.value}
                  variant="outline"
                  size="sm"
                  disabled={alreadyAdded}
                  onClick={() => addWidget(w.value, w.label)}
                >
                  <Plus className="w-3.5 h-3.5 mr-1" />
                  {w.label}
                </Button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
