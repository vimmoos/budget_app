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

    # --- CSV IMPORT SECTION ---
    st.divider()
    with st.expander("📥 Import Budget from CSV"):
        st.write("Upload a CSV with headers: `Category`, `Amount`")
        bg_file = st.file_uploader("Upload Budget CSV", type=["csv"])

        if bg_file and st.button("Load Budget from CSV"):
            try:
                import_df = pd.read_csv(bg_file)
                # Normalize headers
                import_df.columns = [c.lower().strip() for c in import_df.columns]

                if (
                    "category" not in import_df.columns
                    or "amount" not in import_df.columns
                ):
                    st.error("CSV must have 'Category' and 'Amount' columns.")
                else:
                    updated_count = 0
                    # Strategy: Upsert (Update if exists, Insert if new)
                    for index, row in import_df.iterrows():
                        c_name = str(row["category"]).strip()
                        try:
                            amt = float(row["amount"])
                        except:
                            continue  # Skip bad amounts

                        # Find Category ID
                        # We try case-insensitive match if exact match fails
                        cat_id = cat_map.get(c_name)
                        if not cat_id:
                            # Try finding case-insensitive
                            for real_name, real_id in cat_map.items():
                                if real_name.lower() == c_name.lower():
                                    cat_id = real_id
                                    break

                        if cat_id:
                            # Check if budget exists
                            existing = session.exec(
                                select(Budget).where(Budget.category_id == cat_id)
                            ).first()
                            if existing:
                                existing.amount = amt
                                session.add(existing)
                            else:
                                session.add(Budget(category_id=cat_id, amount=amt))
                            updated_count += 1

                    session.commit()
                    if updated_count > 0:
                        st.success(f"Imported targets for {updated_count} categories!")
                        st.rerun()
                    else:
                        st.warning("No matching categories found in CSV.")

            except Exception as e:
                st.error(f"Error reading file: {e}")

else:
    st.warning("No Expense Categories found. Please check 'Manage Categories'.")
