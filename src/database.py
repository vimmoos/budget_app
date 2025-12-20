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


def run_migrations():
    """Adds new columns to existing tables if they don't exist."""
    with engine.connect() as conn:
        # 1. Add initial_balance to Account
        try:
            conn.execute(
                text("ALTER TABLE account ADD COLUMN initial_balance FLOAT DEFAULT 0.0")
            )
            print("Migrated: Added initial_balance to Account")
        except Exception:
            pass  # Column likely exists

        # 2. Add is_virtual to Transaction
        try:
            conn.execute(
                text(
                    "ALTER TABLE 'transaction' ADD COLUMN is_virtual BOOLEAN DEFAULT 0"
                )
            )
            print("Migrated: Added is_virtual to Transaction")
        except Exception:
            pass

        # 3. Add is_settled to Transaction
        try:
            conn.execute(
                text(
                    "ALTER TABLE 'transaction' ADD COLUMN is_settled BOOLEAN DEFAULT 0"
                )
            )
            print("Migrated: Added is_settled to Transaction")
        except Exception:
            pass

        conn.commit()


def init_db():
    # Run schema updates first
    run_migrations()

    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        # 1. Ensure Default Accounts exist
        my_banks = ["Revolut", "Poste", "ASN", "Trading 212"]
        for bank_name in my_banks:
            existing = session.exec(
                select(Account).where(Account.name == bank_name)
            ).first()
            if not existing:
                session.add(Account(name=bank_name))

        # 2. Seed Default Categories if DB is empty
        results = session.exec(select(Category)).first()
        if not results:
            defaults = [
                Category(name="Salary", group="Income", type="Income"),
                Category(name="Si mom", group="Income", type="Income"),
                Category(name="Tax Money", group="Needs", type="Expense"),
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

        # 3. Ensure "Transfer" category exists
        transfer_cat = session.exec(
            select(Category).where(Category.name == "Transfer")
        ).first()
        if not transfer_cat:
            session.add(Category(name="Transfer", group="Transfers", type="Expense"))
            session.commit()

        first_note = session.exec(select(Note)).first()
        if not first_note:
            session.add(Note(content="My Finance Notes..."))
