# Goal-based Savings Tracking & Milestones

Track savings goals with contributions, automatic milestone progression, and portfolio summaries.

## API Endpoints

### Create Goal
```
POST /goals
{ "name": "Vacation Fund", "target_amount": 5000, "currency": "INR",
  "target_date": "2025-06-01", "icon": "plane", "color": "#10B981" }
```
Response `201`: Returns goal with auto-created milestones (25%, 50%, 75%, 100%).

### List Goals
```
GET /goals?status=ACTIVE
```

### Get Goal Detail
```
GET /goals/<id>
```
Returns goal with full contributions history and milestone status.

### Update Goal
```
PUT /goals/<id>
{ "name": "New name", "target_amount": 10000, "status": "PAUSED" }
```

### Delete Goal
```
DELETE /goals/<id>
```

### Add Contribution
```
POST /goals/<id>/contribute
{ "amount": 500, "notes": "Monthly savings" }
```
Returns updated goal balance, progress percentage, and any newly reached milestones.

### List Milestones
```
GET /goals/<id>/milestones
```

### Goals Summary
```
GET /goals/summary
```
Returns aggregate metrics: total/active/completed goals, total saved, overall progress.

## Milestone System

Default milestones are auto-created for each goal:
| Percentage | Title |
|-----------|-------|
| 25% | Quarter way there! |
| 50% | Halfway to your goal! |
| 75% | Three quarters done! |
| 100% | Goal achieved! |

Milestones are automatically marked as reached when a contribution pushes the goal past their threshold. Goals auto-complete (status → COMPLETED) when 100% is reached.

## Database Tables

- `savings_goals` – Goal metadata (name, target, current amount, status, dates, styling)
- `goal_contributions` – Individual deposits toward a goal
- `goal_milestones` – Percentage thresholds with reach timestamps

## Testing

```bash
cd packages/backend
.venv/bin/python -m pytest tests/test_goals.py -v
# 19 passed
```

## Files

| File | Description |
|------|-------------|
| `app/models.py` | SavingsGoal, GoalContribution, GoalMilestone models |
| `app/routes/goals.py` | 9 REST endpoints |
| `app/db/005_goal_savings.sql` | Migration |
| `tests/test_goals.py` | 19 tests |
| `docs/goal-savings-tracking.md` | This documentation |
