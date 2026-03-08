import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

def generate_weekly_summary(data: pd.DataFrame):
    data['date'] = pd.to_datetime(data['date'])
    end_date = data['date'].max()
    start_date = end_date - timedelta(days=7)
    weekly_data = data[(data['date'] >= start_date) & (data['date'] <= end_date)]
    total_value = weekly_data['value'].sum()
    average_value = weekly_data['value'].mean()
    trend = 'upward' if weekly_data['value'].iloc[-1] > weekly_data['value'].iloc[0] else 'downward'
    summary = {
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'total_value': total_value,
        'average_value': average_value,
        'trend': trend,
        'insights': f'The total value for the past week is {total_value:.2f}, with an average of {average_value:.2f}. The trend is {trend}.'
    }
    return summary
if __name__ == '__main__':
    data = pd.DataFrame({
        'date': pd.date_range(datetime.now() - timedelta(days=30), periods=30, freq='D'),
        'value': np.random.random(30) * 1000
    })
    summary = generate_weekly_summary(data)
    print(json.dumps(summary, indent=4))