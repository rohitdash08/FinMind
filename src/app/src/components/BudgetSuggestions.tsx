import React, { useState } from 'react';
import axios from 'axios';

const BudgetSuggestions: React.FC = () => {
    const [suggestions, setSuggestions] = useState<any[]>([]);
    const [error, setError] = useState<string>('');

    const fetchBudgetSuggestions = async () => {
        try {
            const response = await axios.post('/api/suggestions', {
                spending_data: {
                    Food: [200, 220, 250, 230, 240, 210],
                    Transport: [100, 120, 110, 130, 140, 125],
                    Entertainment: [50, 60, 55, 65, 70, 60]
                },
                months: 6
            });
            setSuggestions(response.data.suggestions);
        } catch (err) {
            setError('Failed to fetch suggestions');
        }
    };

    return (
        <div>
            <button onClick={fetchBudgetSuggestions}>Get Budget Suggestions</button>
            {error && <div>{error}</div>}
            <ul>
                {suggestions.map((suggestion, index) => (
                    <li key={index}>{suggestion.category}: ${suggestion.lower_bound.toFixed(2)} - ${suggestion.upper_bound.toFixed(2)}</li>
                ))}
            </ul>
        </div>
    );
};

export default BudgetSuggestions;