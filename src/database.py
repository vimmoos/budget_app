from sqlmodel import SQLModel, create_engine, Session, select, text
from src.models import Category, Account, Note
import os

# Create data directory if not exists
if not os.path.exists("data"):
    os.makedirs("data")

sqlite_file_name = "data/finance.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

# check_same_thread=False is needed for Streamlit
engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})


def get_session():
    return Session(engine)


def init_db():

    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:

        results = session.exec(select(Category)).first()
        if not results:
            defaults = [
                Category(name="Salary", group="Income", type="Income"),
                Category(name="Rent", group="Needs", type="Expense"),
                Category(name="Groceries", group="Needs", type="Expense"),
                Category(name="Utilities", group="Needs", type="Expense"),
                Category(name="Dining Out", group="Wants", type="Expense"),
                Category(name="Fun", group="Wants", type="Expense"),
                Category(name="Investments", group="Savings", type="Expense"),
                Category(name="Uncategorized", group="Discretionary", type="Expense"),
            ]
            session.add_all(defaults)
            session.commit()

        transfer_cat = session.exec(
            select(Category).where(Category.name == "Transfer")
        ).first()
        if not transfer_cat:
            session.add(Category(name="Transfer", group="Transfers", type="Expense"))
            session.commit()

        first_note = session.exec(select(Note)).first()
        if not first_note:
            session.add(Note(content="My Finance Notes..."))
