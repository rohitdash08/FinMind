import { type ReactNode, useState } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { GripVertical, Eye, EyeOff, Trash2, Maximize2, Minimize2 } from 'lucide-react';
import { type Widget, useWidgets } from '@/hooks/use-widgets';

type WidgetCardProps = {
  widget: Widget;
  children: ReactNode;
  className?: string;
};

export function WidgetCard({ widget, children, className = '' }: WidgetCardProps) {
  const { editMode, toggleVisibility, removeWidget, resizeWidget } = useWidgets();
  const [collapsed, setCollapsed] = useState(false);

  if (!widget.visible && !editMode) return null;

  return (
    <FinancialCard
      className={`relative group transition-all duration-200 ${
        editMode ? 'ring-2 ring-primary/30 ring-dashed' : ''
      } ${!widget.visible ? 'opacity-40' : ''} ${className}`}
    >
      <FinancialCardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {editMode && (
              <GripVertical className="w-4 h-4 text-muted-foreground cursor-grab" />
            )}
            <FinancialCardTitle className="text-sm font-semibold">
              {widget.title}
            </FinancialCardTitle>
          </div>
          <div className="flex items-center gap-1">
            {editMode && (
              <>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={() => setCollapsed((v) => !v)}
                >
                  {collapsed ? (
                    <Maximize2 className="w-3.5 h-3.5" />
                  ) : (
                    <Minimize2 className="w-3.5 h-3.5" />
                  )}
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={() => resizeWidget(widget.id, widget.cols === 2 ? 1 : 2)}
                >
                  {widget.cols === 2 ? (
                    <Minimize2 className="w-3.5 h-3.5" />
                  ) : (
                    <Maximize2 className="w-3.5 h-3.5" />
                  )}
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={() => toggleVisibility(widget.id)}
                >
                  {widget.visible ? (
                    <EyeOff className="w-3.5 h-3.5" />
                  ) : (
                    <Eye className="w-3.5 h-3.5" />
                  )}
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 text-destructive hover:text-destructive"
                  onClick={() => removeWidget(widget.id)}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              </>
            )}
          </div>
        </div>
      </FinancialCardHeader>
      {!collapsed && <FinancialCardContent>{children}</FinancialCardContent>}
    </FinancialCard>
  );
}
