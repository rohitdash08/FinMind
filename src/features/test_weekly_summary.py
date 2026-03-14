import unittest
from datetime import datetime
from src.features.weekly_summary import WeeklySummary

class TestWeeklySummary(unittest.TestCase):
    def setUp(self):
        # Sample data for testing
        self.data = [
            {'date': datetime(2026, 3, 8), 'amount': 50},
            {'date': datetime(2026, 3, 9), 'amount': 30},
            {'date': datetime(2026, 3, 10), 'amount': 70},
            {'date': datetime(2026, 3, 12), 'amount': 20},
            {'date': datetime(2026, 3, 14), 'amount': 40},
        ]
        self.weekly_summary = WeeklySummary(self.data)

    def test_calculate_week_range(self):
        self.weekly_summary.calculate_week_range('2026-03-09')
        self.assertEqual(self.weekly_summary.start_date.strftime('%Y-%m-%d'), '2026-03-07')
        self.assertEqual(self.weekly_summary.end_date.strftime('%Y-%m-%d'), '2026-03-13')

    def test_generate_summary_report(self):
        self.weekly_summary.calculate_week_range('2026-03-09')
        report = self.weekly_summary.generate_summary_report()
        self.assertEqual(report['week_start'], '2026-03-07')
        self.assertEqual(report['week_end'], '2026-03-13')
        self.assertEqual(report['entries_count'], 5)
        self.assertEqual(report['total_spent'], 210)
        self.assertEqual(report['average_spent'], 42.0)

if __name__ == '__main__':
    unittest.main()