import pandas as pd
import numpy as np
from typing import List, Tuple

class BudgetSuggestion:
    def __init__(self, spending_data: pd.DataFrame, months: int = 6):
        self.spending_data = spending_data
        self.months = months
        self.suggestions = []

    def analyze_spending(self) -> pd.DataFrame:
        # Calculate average spending and confidence interval
        recent_data = self.spending_data.tail(self.months)
        avg_spending = recent_data.mean(axis=0)
        std_dev = recent_data.std(axis=0)
        confidence_interval = 1.96 * std_dev / np.sqrt(self.months)
        return avg_spending, confidence_interval

    def generate_suggestion(self) -> List[Tuple[str, float, float]]:
        avg_spending, confidence_interval = self.analyze_spending()
        for category in avg_spending.index:
            lower_bound = avg_spending[category] - confidence_interval[category]
            upper_bound = avg_spending[category] + confidence_interval[category]
            self.suggestions.append((category, lower_bound, upper_bound))
        return self.suggestions

    def get_suggestions(self) -> List[Tuple[str, float, float]]:
        if not self.suggestions:
            self.generate_suggestion()
        return self.suggestions

# Example Usage
if __name__ == '__main__':
    # Example spending data for the last 6 months
    data = {'Food': [200, 220, 250, 230, 240, 210],
            'Transport': [100, 120, 110, 130, 140, 125],
            'Entertainment': [50, 60, 55, 65, 70, 60]}
    df = pd.DataFrame(data)

    budget = BudgetSuggestion(df)
    suggestions = budget.get_suggestions()
    for suggestion in suggestions:
        print(f'Category: {suggestion[0]}, Suggested Budget: ${suggestion[1]:.2f} - ${suggestion[2]:.2f}')