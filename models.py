from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.orm import relationship
from base import Base

class SavingsGoal(Base):
    __tablename__ = 'savings_goals'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    target_amount = Column(Float, nullable=False)
    current_amount = Column(Float, default=0.0)
    milestones = relationship('Milestone', back_populates='goal')
    def add_savings(self, amount):
        self.current_amount += amount
        return self.current_amount
    def add_milestone(self, milestone):
        self.milestones.append(milestone)
    def check_milestones(self):
        reached = []
        for milestone in self.milestones:
            if self.current_amount >= milestone.target_amount:
                reached.append(milestone)
        return reached

class Milestone(Base):
    __tablename__ = 'milestones'
    id = Column(Integer, primary_key=True)
    target_amount = Column(Float, nullable=False)
    description = Column(String, nullable=False)
    goal_id = Column(Integer, ForeignKey('savings_goals.id'))
    goal = relationship('SavingsGoal', back_populates='milestones')