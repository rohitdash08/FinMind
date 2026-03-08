import unittest
import pandas as pd
import numpy as np
from weekly_summary import generate_weekly_summary

class TestWeeklySummary(unittest.TestCase):
    def setUp(self):
        self.data = pd.DataFrame({
            'date': pd.date_range('2026-02-01', periods=30, freq='D'),
            'value': np.random.random(30) * 1000
        })
    def test_generate_weekly_summary(self):
        summary = generate_weekly_summary(self.data)
        self.assertIn('start_date', summary)
        self.assertIn('end_date', summary)
        self.assertIn('total_value', summary)
        self.assertIn('average_value', summary)
        self.assertIn('trend', summary)
        self.assertIn('insights', summary)
        self.assertIsInstance(summary['start_date'], str)
        self.assertIsInstance(summary['end_date'], str)
        self.assertIsInstance(summary['total_value'], (int, float))
        self.assertIsInstance(summary['average_value'], (int, float))
        self.assertIsInstance(summary['trend'], str)

if __name__ == '__main__':
    unittest.main()