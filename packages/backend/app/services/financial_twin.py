"""Personal Financial Digital Twin Simulator (issue #100)."""
import logging
from datetime import date
from dateutil.relativedelta import relativedelta
from sqlalchemy import extract, func
from ..extensions import db
from ..models import Expense

logger = logging.getLogger("finmind.twin")

def simulate_scenario(user_id: int, scenario: dict) -> dict:
    today = date.today()
    months = 3
    start = today - relativedelta(months=months)
    income = float(db.session.query(func.coalesce(func.sum(Expense.amount),0))
                   .filter(Expense.user_id==user_id, Expense.spent_at>=start,
                           Expense.expense_type=="INCOME").scalar() or 0) / months
    expenses = float(db.session.query(func.coalesce(func.sum(Expense.amount),0))
                     .filter(Expense.user_id==user_id, Expense.spent_at>=start,
                             Expense.expense_type!="INCOME").scalar() or 0) / months
    sim_income, sim_expenses = income, expenses
    changes_applied = []
    for c in scenario.get("changes",[]):
        t = c.get("type"); amt = float(c.get("monthly_amount",0))
        if t=="income_increase": sim_income+=amt; changes_applied.append(f"+${amt:.0f}/mo income")
        elif t=="expense_reduction": sim_expenses-=amt; changes_applied.append(f"-${amt:.0f}/mo {c.get('category','')}")
        elif t=="new_expense": sim_expenses+=amt; changes_applied.append(f"+${amt:.0f}/mo {c.get('name','')}")
    months_ahead = scenario.get("months_ahead", 12)
    delta = (sim_income-sim_expenses) - (income-expenses)
    projections = []
    cum = 0.0
    for i in range(1, months_ahead+1):
        cum += delta
        m = today + relativedelta(months=i)
        projections.append({"month":f"{m.year}-{m.month:02d}","sim_savings":round(sim_income-sim_expenses,2),"vs_current":round(delta,2),"cumulative_gain":round(cum,2)})
    return {"scenario":scenario.get("name","Unnamed"),"baseline":{"monthly_income":round(income,2),"monthly_expenses":round(expenses,2),"monthly_savings":round(income-expenses,2)},
            "simulated":{"monthly_income":round(sim_income,2),"monthly_expenses":round(sim_expenses,2),"monthly_savings":round(sim_income-sim_expenses,2)},
            "changes_applied":changes_applied,"total_gain":round(cum,2),"projections":projections,"verdict":"positive" if cum>0 else "negative"}
