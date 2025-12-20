from typing import Optional
from datetime import datetime
from sqlmodel import Field, SQLModel


class Account(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    initial_balance: float = Field(default=0.0)
    import_config: Optional[str] = Field(default=None)


class Category(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    group: str
    type: str
    default_account_id: Optional[int] = Field(default=None, foreign_key="account.id")


class CategoryRule(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    keyword: str
    category_id: int = Field(foreign_key="category.id")


class Budget(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    category_id: int = Field(foreign_key="category.id")
    amount: float


class Transaction(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    date: str
    description: str
    amount: float
    category_id: Optional[int] = Field(default=None, foreign_key="category.id")
    account_id: Optional[int] = Field(default=None, foreign_key="account.id")
    unique_hash: str = Field(unique=True)

    is_virtual: bool = Field(default=False)
    is_settled: bool = Field(default=False)


class Note(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    content: str
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
