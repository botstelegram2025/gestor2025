import os
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base

# Database URL must be set in the environment variable DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/dbname")

Base = declarative_base()

# Exemplo de modelo de tabela, pode ser ajustado conforme necessidade
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    full_name = Column(String)

class DatabaseManager:
    def __init__(self, database_url=DATABASE_URL):
        self.engine = create_engine(database_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        # Cria as tabelas se não existirem
        Base.metadata.create_all(bind=self.engine)

    def get_session(self):
        return self.SessionLocal()

    # Métodos de exemplo para manipulação de usuários
    def add_user(self, username, full_name):
        session = self.get_session()
        try:
            user = User(username=username, full_name=full_name)
            session.add(user)
            session.commit()
            return user
        except Exception as e:
            session.rollback()
            print(f"Error adding user: {e}")
            return None
        finally:
            session.close()

    def get_user(self, username):
        session = self.get_session()
        try:
            return session.query(User).filter_by(username=username).first()
        finally:
            session.close()
