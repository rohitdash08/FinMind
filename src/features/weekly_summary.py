import datetime

class WeeklySummary:
    def __init__(self, data: list):
        self.data = data
        self.start_date = None
        self.end_date = None

    def calculate_week_range(self, date: str):
        # Parse the date and calculate the week range
        parsed_date = datetime.datetime.strptime(date, '%Y-%m-%d')
        self.start_date = parsed_date - datetime.timedelta(days=parsed_date.weekday())
        self.end_date = self.start_date + datetime.timedelta(days=6)

    def get_weekly_summary(self):
        # Filter data for the calculated week range
        filtered_data = [entry for entry in self.data if self.start_date <= entry['date'] <= self.end_date]
        return filtered_data

    def generate_summary_report(self):
        # Generate weekly summary report
        summary = self.get_weekly_summary()
        report = {
            'week_start': self.start_date.strftime('%Y-%m-%d'),
            'week_end': self.end_date.strftime('%Y-%m-%d'),
            'entries_count': len(summary),
            'total_spent': sum(entry['amount'] for entry in summary),
            'average_spent': sum(entry['amount'] for entry in summary) / len(summary) if summary else 0,
        }
        return report