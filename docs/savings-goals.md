# Goal-Based Savings Tracking

This feature allows users to create savings goals, track progress, and define milestones along the way.

## Data Models

### SavingsGoal

| Field | Type | Description |
|---|---|---|
| `id` | integer | Primary key |
| `user_id` | integer | Owner of the goal |
| `name` | string | Goal name |
| `description` | string\|null | Optional description |
| `target_amount` | decimal | Amount to save |
| `current_amount` | decimal | Amount saved so far |
| `currency` | string | ISO 4217 currency code (default `USD`) |
| `status` | enum | `active` \| `completed` \| `cancelled` |
| `deadline` | datetime\|null | Optional target date |
| `created_at` | datetime | Creation timestamp |
| `updated_at` | datetime | Last update timestamp |

### SavingsMilestone

| Field | Type | Description |
|---|---|---|
| `id` | integer | Primary key |
| `goal_id` | integer | Parent goal |
| `name` | string | Milestone name |
| `target_amount` | decimal | Amount at which this milestone is reached |
| `reached_at` | datetime\|null | When this milestone was reached |
| `created_at` | datetime | Creation timestamp |

## API Endpoints

All endpoints accept a `user_id` query parameter for ownership scoping.

### Goals

```
POST   /savings/goals                  Create a new goal
GET    /savings/goals                  List all goals for a user
GET    /savings/goals/{goal_id}        Get a specific goal
PATCH  /savings/goals/{goal_id}        Update a goal
DELETE /savings/goals/{goal_id}        Delete a goal
```

### Milestones

```
POST   /savings/goals/{goal_id}/milestones                        Create a milestone
GET    /savings/goals/{goal_id}/milestones                        List milestones for a goal
PATCH  /savings/goals/{goal_id}/milestones/{milestone_id}         Update a milestone
DELETE /savings/goals/{goal_id}/milestones/{milestone_id}         Delete a milestone
```

## Frontend API Client

All functions are exported from `app/src/api/savings.ts`.

```ts
import {
  createGoal,
  listGoals,
  getGoal,
  updateGoal,
  deleteGoal,
  createMilestone,
  listMilestones,
  updateMilestone,
  deleteMilestone,
} from "@/api/savings";

// Create a goal
const goal = await createGoal(userId, { name: "Vacation", target_amount: "2000.00" });

// Add a milestone
const milestone = await createMilestone(userId, goal.id, {
  name: "Halfway there",
  target_amount: "1000.00",
});

// Mark milestone as reached
await updateMilestone(userId, goal.id, milestone.id, {
  reached_at: new Date().toISOString(),
});

// Mark goal as completed
await updateGoal(userId, goal.id, { status: "completed" });
```

## Running Tests

```bash
cd backend
pytest tests/test_savings.py -v
```
