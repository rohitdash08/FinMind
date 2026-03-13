import { useEffect, useState } from "react";
import { FinancialCard, FinancialCardContent, FinancialCardDescription, FinancialCardHeader, FinancialCardTitle } from "@/components/ui/financial-card";
import { Button } from "@/components/ui/button";
import { getGoals, Goal, createGoal } from "@/api/goals";

export function Goals() {
    const [goals, setGoals] = useState<Goal[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        getGoals().then((data) => {
            setGoals(data);
            setLoading(false);
        }).catch(err => {
            console.error(err);
            setLoading(false);
        });
    }, []);

    const handleCreate = async () => {
        const name = prompt("Goal name:");
        if (!name) return;
        const target = parseFloat(prompt("Target amount:") || "0");
        if (target <= 0) return;
        
        await createGoal({ name, target_amount: target, current_amount: 0 });
        const updated = await getGoals();
        setGoals(updated);
    };

    if (loading) return <div>Loading...</div>;

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <h1 className="text-3xl font-bold">Goals & Milestones</h1>
                <Button onClick={handleCreate}>New Goal</Button>
            </div>
            
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {goals.map((g) => (
                    <FinancialCard key={g.id}>
                        <FinancialCardHeader>
                            <FinancialCardTitle>{g.name}</FinancialCardTitle>
                            <FinancialCardDescription>
                                {g.current_amount} / {g.target_amount} {g.currency}
                            </FinancialCardDescription>
                        </FinancialCardHeader>
                        <FinancialCardContent>
                            <div className="w-full bg-secondary rounded-full h-2.5">
                                <div 
                                    className="bg-primary h-2.5 rounded-full" 
                                    style={{ width: `${Math.min((g.current_amount / g.target_amount) * 100, 100)}%` }}
                                ></div>
                            </div>
                        </FinancialCardContent>
                    </FinancialCard>
                ))}
            </div>
            {goals.length === 0 && <p className="text-muted-foreground">No goals set yet.</p>}
        </div>
    );
}
