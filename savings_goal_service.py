from models import SavingsGoal, Milestone
from db_session import session

def create_goal(name, target_amount):
    goal = SavingsGoal(name=name, target_amount=target_amount)
    session.add(goal)
    session.commit()
    return goal

def add_savings_to_goal(goal_id, amount):
    goal = session.query(SavingsGoal).get(goal_id)
    if goal:
        goal.add_savings(amount)
        session.commit()
        return goal
    return None

def create_milestone(goal_id, target_amount, description):
    goal = session.query(SavingsGoal).get(goal_id)
    if goal:
        milestone = Milestone(target_amount=target_amount, description=description, goal=goal)
        goal.add_milestone(milestone)
        session.commit()
        return milestone
    return None

def get_goal_milestones(goal_id):
    goal = session.query(SavingsGoal).get(goal_id)
    if goal:
        return goal.check_milestones()
    return []