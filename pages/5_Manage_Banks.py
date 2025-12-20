import streamlit as st
from src.database import get_session
from src.models import Account, Category
from sqlmodel import select
import pandas as pd

st.set_page_config(page_title="Bank Manager", layout="wide")
st.title("🏦 Bank & Fund Management")

session = get_session()
tab1, tab2 = st.tabs(["Add Accounts", "Assign Categories"])

# --- TAB 1: CREATE ACCOUNTS ---
with tab1:
    st.subheader("Your Accounts")

    with st.form("add_bank"):
        new_bank_name = st.text_input("New Bank Name (e.g., PayPal)")
        if st.form_submit_button("Add Bank"):
            if new_bank_name:
                session.add(Account(name=new_bank_name))
                session.commit()
                st.success(f"Added {new_bank_name}")
                st.rerun()

    accounts = session.exec(select(Account)).all()
    if accounts:
        for acc in accounts:
            st.write(f"💳 **{acc.name}**")
    else:
        st.warning("No accounts found. Restart app to load defaults.")

# --- TAB 2: ASSIGN CATEGORIES ---
with tab2:
    st.subheader("Default Payment Methods")
    st.info(
        "Assign a default bank to each category. This helps the AI calculate transfers."
    )

    categories = session.exec(select(Category).where(Category.type == "Expense")).all()
    accounts = session.exec(select(Account)).all()

    if not accounts:
        st.error("No accounts available.")
    else:
        acc_map = {a.name: a.id for a in accounts}
        # Reverse map to show current names
        acc_rev_map = {a.id: a.name for a in accounts}

        data = []
        for cat in categories:
            current_acc_name = acc_rev_map.get(cat.default_account_id, "Unassigned")
            data.append(
                {
                    "Category": cat.name,
                    "Group": cat.group,
                    "Default Bank": current_acc_name,
                    "cat_id": cat.id,
                }
            )

        df = pd.DataFrame(data)

        edited_df = st.data_editor(
            df,
            column_config={
                "Default Bank": st.column_config.SelectboxColumn(
                    "Pays From",
                    options=list(acc_map.keys()) + ["Unassigned"],
                    required=True,
                ),
                "cat_id": None,  # Hide ID
            },
            disabled=["Category", "Group"],
            hide_index=True,
            use_container_width=True,
        )

        if st.button("Save Assignments"):
            for index, row in edited_df.iterrows():
                cat = session.get(Category, row["cat_id"])
                selected_acc = row["Default Bank"]

                if selected_acc != "Unassigned":
                    cat.default_account_id = acc_map[selected_acc]
                else:
                    cat.default_account_id = None
                session.add(cat)

            session.commit()
            st.success("Assignments updated!")
