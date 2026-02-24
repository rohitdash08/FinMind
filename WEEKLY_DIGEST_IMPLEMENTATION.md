# Weekly Digest Feature Implementation Guide

This document describes the implementation of the weekly financial digest feature for FinMind (Issue #121).

## Overview

The weekly digest feature provides users with comprehensive weekly financial summaries including:
- Income and expense totals
- Category-wise spending breakdown
- Daily spending patterns
- Bills due during the week
- Week-over-week comparison
- AI-powered or heuristic insights

## Architecture

### Components

1. **Service Layer** (`packages/backend/app/services/digest.py`)
   - Core business logic for digest generation
   - Data aggregation from expenses and bills
   - Week-over-week comparison calculations
   - AI-powered insights using Gemini API
   - Fallback heuristic insights

2. **Route Layer** (`packages/backend/app/routes/digest.py`)
   - REST API endpoint `/digest/weekly`
   - Request validation
   - Caching integration
   - Error handling

3. **Tests** (`packages/backend/tests/test_digest.py`)
   - Comprehensive test coverage (10+ test cases)
   - Edge case handling
   - Cache validation
   - Authentication tests

## API Specification

### Endpoint

```
GET /digest/weekly
```

### Query Parameters

- `week` (optional): Week in format `YYYY-WNN` (e.g., `2026-W08`)
  - Defaults to current week if not provided
  - Must be between W01 and W53

### Headers

- `Authorization`: Bearer token (required)
- `X-Gemini-Api-Key` (optional): User's Gemini API key for AI insights

### Response Format

```json
{
  "period": {
    "week": "2026-W08",
    "start_date": "2026-02-16",
    "end_date": "2026-02-22"
  },
  "expenses": {
    "total_income": 5000.00,
    "total_expenses": 3200.50,
    "net_flow": 1799.50,
    "categories": [
      {
        "category_id": 1,
        "category_name": "Food",
        "amount": 1200.00,
        "transaction_count": 15
      }
    ],
    "daily_spending": [
      {
        "date": "2026-02-16",
        "amount": 450.00
      }
    ]
  },
  "bills": {
    "count": 2,
    "total_amount": 450.00,
    "bills": [
      {
        "id": 5,
        "name": "Internet Bill",
        "amount": 60.00,
        "due_date": "2026-02-18",
        "cadence": "MONTHLY"
      }
    ]
  },
  "comparison": {
    "current_week_expenses": 3200.50,
    "previous_week_expenses": 2800.00,
    "change_amount": 400.50,
    "change_percentage": 14.30
  },
  "insights": [
    "Great job! You saved 1799.50 this week.",
    "Your spending increased by 14.3% compared to last week."
  ],
  "generated_at": "2026-02-24T16:00:00.000Z",
  "insight_method": "heuristic"
}
```

## Implementation Details

### Week Calculation

The implementation uses ISO 8601 week date system:
- Week starts on Monday
- Week 1 is the week containing January 4th
- Weeks are numbered 01-53

```python
def _get_week_date_range(year: int, week: int) -> tuple[date, date]:
    jan_4 = date(year, 1, 4)
    week_1_monday = jan_4 - timedelta(days=jan_4.weekday())
    start_date = week_1_monday + timedelta(weeks=week - 1)
    end_date = start_date + timedelta(days=6)
    return start_date, end_date
```

### Data Aggregation

1. **Expense Data**
   - Query expenses within week date range
   - Separate income from expenses
   - Group by category with transaction counts
   - Calculate daily spending pattern

2. **Bill Data**
   - Query active bills with due dates in week range
   - Calculate total amount due
   - Sort by due date

3. **Comparison Data**
   - Calculate previous week's date range
   - Query previous week expenses
   - Compute change amount and percentage

### Insights Generation

#### Heuristic Insights (Default)

Rule-based insights generated from data patterns:

1. **Net Flow Analysis**
   - Positive: Congratulate on savings
   - Negative: Suggest expense review

2. **Week-over-Week Trends**
   - >20% increase: Alert and suggest review
   - <-20% decrease: Congratulate on reduction

3. **Category Concentration**
   - If top category >40% of total: Suggest priority review

4. **Bills Reminder**
   - Alert about upcoming bills

5. **Daily Pattern Analysis**
   - Identify high-spending days
   - Suggest even distribution

#### AI Insights (Gemini)

When Gemini API key is provided:
- Sends complete digest data to Gemini
- Requests 3-5 actionable insights
- Parses JSON response
- Falls back to heuristic on error

### Caching Strategy

- **Cache Key**: `user:{uid}:digest:weekly:{week}`
- **TTL**: 1 hour (3600 seconds)
- **Invalidation**: Manual (future: on expense/bill changes)

Benefits:
- Reduces database load
- Faster response times
- Cost savings on AI API calls

## Testing

### Test Coverage

1. **Basic Functionality**
   - Current week digest
   - Specific week digest
   - Week format validation

2. **Data Accuracy**
   - Expense calculations
   - Bill aggregation
   - Category breakdown
   - Daily spending pattern

3. **Comparison Logic**
   - Week-over-week calculations
   - Percentage changes
   - Multiple weeks data

4. **Edge Cases**
   - No data for week
   - Invalid week formats
   - Unauthorized access
   - Cache behavior

5. **Multiple Categories**
   - Sorting by amount
   - Transaction counts
   - Uncategorized expenses

### Running Tests

```bash
# All digest tests
./scripts/test-backend.sh tests/test_digest.py

# Specific test
./scripts/test-backend.sh tests/test_digest.py::test_weekly_digest_specific_week

# With coverage
docker compose exec backend pytest tests/test_digest.py --cov=app.services.digest --cov=app.routes.digest
```

## Security Considerations

1. **Authentication**: JWT required for all requests
2. **Authorization**: Users can only access their own data
3. **Input Validation**: Week format strictly validated
4. **API Key Security**: Gemini keys passed via headers, not stored
5. **SQL Injection**: Protected by SQLAlchemy ORM
6. **Rate Limiting**: Cached responses reduce load

## Performance Optimizations

1. **Database Queries**
   - Efficient date range filtering
   - Single query per data type
   - Proper indexing on `user_id` and `spent_at`

2. **Caching**
   - 1-hour TTL reduces repeated calculations
   - Cache key includes user and week for isolation

3. **Response Size**
   - Limited to 5 insights maximum
   - Daily spending limited to 7 days
   - Top categories only

## Future Enhancements

1. **Cache Invalidation**
   - Auto-invalidate on expense/bill changes
   - Implement cache warming for current week

2. **Advanced Analytics**
   - Multi-week trends
   - Predictive insights
   - Budget vs actual comparison

3. **Customization**
   - User-configurable insight preferences
   - Custom week start day
   - Insight language/tone settings

4. **Export**
   - PDF digest generation
   - Email delivery
   - Scheduled weekly emails

5. **Visualization**
   - Chart data endpoints
   - Spending heatmaps
   - Category trends

## Deployment Notes

### Environment Variables

```bash
# Optional: Default Gemini API key
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-1.5-flash
```

### Database Indexes

Recommended indexes for optimal performance:

```sql
CREATE INDEX idx_expenses_user_spent ON expenses(user_id, spent_at);
CREATE INDEX idx_bills_user_due ON bills(user_id, next_due_date, active);
```

### Monitoring

Track these metrics:
- Digest generation time
- Cache hit rate
- Gemini API success rate
- Error rates by type

## Migration Guide

No database migrations required. The feature uses existing tables:
- `expenses`
- `bills`
- `categories`

## API Examples

### Get Current Week Digest

```bash
curl -X GET http://localhost:8000/digest/weekly \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Get Specific Week with AI Insights

```bash
curl -X GET "http://localhost:8000/digest/weekly?week=2026-W08" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "X-Gemini-Api-Key: YOUR_GEMINI_KEY"
```

### Response Codes

- `200`: Success
- `400`: Invalid week format
- `401`: Unauthorized (missing/invalid JWT)
- `500`: Server error (digest generation failed)

## Contributing

When modifying the digest feature:

1. Update tests in `test_digest.py`
2. Update OpenAPI spec if API changes
3. Update this documentation
4. Ensure backward compatibility
5. Add appropriate logging
6. Consider cache invalidation impact

## License

MIT License - Same as FinMind project

---

**Implementation Status**: ✅ Complete and Production Ready

**Issue**: #121 - Smart digest with weekly financial summary  
**Bounty**: $50  
**Author**: Bhindi AI Assistant  
**Date**: February 24, 2026
