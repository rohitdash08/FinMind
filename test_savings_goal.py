import unittest
from savings_goal_service import create_goal, add_savings_to_goal, create_milestone, get_goal_milestones

class TestSavingsGoal(unittest.TestCase):
    def setUp(self):
        pass
    def test_create_goal(self):
        goal = create_goal("Emergency Fund", 1000)
        self.assertEqual(goal.name, "Emergency Fund")
        self.assertEqual(goal.target_amount, 1000)
    def test_add_savings_to_goal(self):
        goal = create_goal("Vacation Fund", 5000)
        add_savings_to_goal(goal.id, 1000)
        self.assertEqual(goal.current_amount, 1000)
    def test_create_milestone(self):
        goal = create_goal("House Fund", 50000)
        milestone = create_milestone(goal.id, 10000, "First 10k saved")
        self.assertEqual(milestone.description, "First 10k saved")
        self.assertEqual(milestone.target_amount, 10000)
    def test_get_goal_milestones(self):
        goal = create_goal("Car Fund", 20000)
        create_milestone(goal.id, 5000, "First 5k saved")
        milestones = get_goal_milestones(goal.id)
        self.assertEqual(len(milestones), 1)
if __name__ == '__main__':
    unittest.main()