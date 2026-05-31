import { WidgetDashboard } from '@/components/dashboard/WidgetDashboard';

export function Dashboard() {
  return (
    <div className="page-wrap">
      <div className="page-header">
        <h1 className="page-title">Financial Dashboard</h1>
        <p className="page-subtitle">Customizable widget-based overview of your finances. Drag, resize, and toggle widgets to suit your needs.</p>
      </div>
      <WidgetDashboard />
    </div>
  );
}
