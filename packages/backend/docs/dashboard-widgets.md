# Customizable Dashboard Widgets

## Overview

Allows users to show/hide, reorder, and configure dashboard sections. Provides 8 default widgets with per-user customization that persists across sessions.

## Default Widgets

| Position | Key | Name |
|---|---|---|
| 0 | spending_overview | Spending Overview |
| 1 | recent_transactions | Recent Transactions |
| 2 | budget_progress | Budget Progress |
| 3 | upcoming_bills | Upcoming Bills |
| 4 | category_breakdown | Category Breakdown |
| 5 | savings_goals | Savings Goals |
| 6 | recurring_expenses | Recurring Expenses |
| 7 | financial_health | Financial Health Score |

## API Endpoints

All endpoints require JWT authentication.

### Get Layout
```
GET /widgets
Response: [
  { "id": 1, "widget_key": "spending_overview", "display_name": "Spending Overview", "visible": true, "position": 0, "config": {} }
]
```

### Initialize Layout
```
POST /widgets/initialize
```

### Reset Layout
```
POST /widgets/reset
```

### Toggle Widget Visibility
```
PUT /widgets/:widget_key/visibility
Body: { "visible": false }
```

### Bulk Update Visibility
```
PUT /widgets/visibility
Body: { "spending_overview": false, "savings_goals": false }
```

### Reorder Widgets
```
PUT /widgets/reorder
Body: { "order": ["upcoming_bills", "spending_overview", "recent_transactions"] }
```

### Update Widget Config
```
PUT /widgets/:widget_key/config
Body: { "period": "weekly", "showChart": true }
```

### Get Single Widget
```
GET /widgets/:widget_key
```

### Available Widgets
```
GET /widgets/available
Response: [{ "widget_key": "spending_overview", "display_name": "Spending Overview" }]
```

## Testing

```bash
cd packages/backend
.venv/bin/python -m pytest tests/test_dashboard_widgets.py -v
```

25 tests covering layout, visibility, reordering, config, and routes.
