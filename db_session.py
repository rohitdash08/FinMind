from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine('sqlite:///finmind.db')
SessionFactory = sessionmaker(bind=engine)
session = SessionFactory()

def init_db():
    from models import Base
    Base.metadata.create_all(engine)