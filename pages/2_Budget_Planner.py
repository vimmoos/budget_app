import streamlit as st
from src.database import get_session
from src.models import Category, Budget
from sqlmodel import select, delete
import pandas as pd

st.set_page_config(page_title="Budget Planner", layout="wide")
st.title("📅 Budget Targets")
st.info("Set your target monthly spending here. These targets apply to every month.")

session = get_session()

# 1. Fetch Categories
categories = session.exec(select(Category).where(Category.type == "Expense")).all()
cat_map = {c.name: c.id for c in categories}  # Name -> ID lookup

# 2. Fetch Existing Global Budgets
existing_budgets = session.exec(select(Budget)).all()
budget_map = {b.category_id: b.amount for b in existing_budgets}

# 3. Prepare Data for Editor
data = []
for cat in categories:
    data.append(
        {
            "Category": cat.name,
            "Group": cat.group,
            "Target ($)": budget_map.get(cat.id, 0.0),
            "cat_id": cat.id,
        }
    )

df = pd.DataFrame(data)

if not df.empty:
    edited_df = st.data_editor(
        df,
        column_config={
            "Target ($)": st.column_config.NumberColumn(format="$%.2f"),
            "cat_id": None,  # Hide ID
        },
        disabled=["Category", "Group"],
        hide_index=True,
        num_rows="fixed",
        use_container_width=True,
    )

    # Calc Total
    total_budgeted = edited_df["Target ($)"].sum()
    st.metric("Total Monthly Budget", f"${total_budgeted:,.2f}")

    if st.button("Save Targets", type="primary"):
        # 1. Wipe ALL existing budget entries (to clean up old/unused)
        session.exec(delete(Budget))

        # 2. Add new Global entries
        count = 0
        for index, row in edited_df.iterrows():
            if row["Target ($)"] > 0:
                new_budget = Budget(
                    category_id=row["cat_id"],
                    amount=row["Target ($)"],
                )
                session.add(new_budget)
                count += 1

        session.commit()
        st.success(f"Successfully saved {count} budget targets!")
        st.rerun()


else:
    st.warning("No Expense Categories found. Please check 'Manage Categories'.")
