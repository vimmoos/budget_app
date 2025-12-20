import streamlit as st
import pandas as pd
from sqlmodel import select
from src.database import get_session
from src.models import Transaction, Category, Account

st.set_page_config(page_title="Reconciliation", page_icon="⚖️")

st.title("⚖️ Reconciliation Advisor")
st.markdown(
    """
This tool shows **misaligned transactions** (paid by the wrong account).
Each section represents a debt from one account to another based on real spending.
"""
)


# --- 1. FETCH DATA ---
def get_unsettled_data():
    with get_session() as session:
        # Get Unsettled Transactions that are NOT transfers
        # and where the Category has a designated Default Account

        # Explicit JOINs to avoid SQLAlchemy ambiguity error
        query = (
            select(Transaction, Category, Account)
            .join(Category, Transaction.category_id == Category.id)
            .join(Account, Transaction.account_id == Account.id)
            .where(Transaction.is_settled == False)
            .where(Category.group != "Transfers")  # Ignore explicit transfers
            .where(
                Category.default_account_id != None
            )  # Only categories with a "home" account
            .where(
                Transaction.account_id != Category.default_account_id
            )  # The mismatch
        )
        results = session.exec(query).all()

        # Map Default Account IDs to Names
        all_accounts = session.exec(select(Account)).all()
        acct_map = {a.id: a.name for a in all_accounts}

        data = []
        for t, cat, payer_acct in results:
            intended_acct_name = acct_map.get(cat.default_account_id, "Unknown")

            # Logic:
            # "Payer" paid for it. "Intended" SHOULD have paid.
            # "Intended" OWES "Payer".

            data.append(
                {
                    "tx_id": t.id,
                    "date": t.date,
                    "description": t.description,
                    "amount": t.amount,
                    "category": cat.name,
                    "payer_acct": payer_acct.name,  # The one who actually paid
                    "intended_acct": intended_acct_name,  # The one who owes money
                    "group_key": (
                        intended_acct_name,
                        payer_acct.name,
                    ),  # (Debtor, Creditor)
                }
            )

    return pd.DataFrame(data)


df = get_unsettled_data()

if df.empty:
    st.success("🎉 Everything is reconciled! No misaligned transactions found.")
    st.stop()

# --- 2. GROUPING LOGIC (Simple Sums) ---
# Group by (Debtor, Creditor)
groups = df.groupby("group_key")

# --- 3. DISPLAY LOOP ---
st.divider()

for (debtor, creditor), group_df in groups:
    # Calculate Total for this specific pair
    total_amount = group_df["amount"].sum()

    # Header
    st.markdown(f"### 💸 **{debtor}** owes **{creditor}**: `€{total_amount:,.2f}`")

    # Layout: Button on top, Table below
    c1, c2 = st.columns([1, 4])

    with c1:
        # Action Button
        if st.button("Mark Settled ✅", key=f"btn_{debtor}_{creditor}"):
            tx_ids_to_settle = group_df["tx_id"].tolist()

            with get_session() as session:
                statement = select(Transaction).where(
                    Transaction.id.in_(tx_ids_to_settle)
                )
                txs = session.exec(statement).all()
                for t in txs:
                    t.is_settled = True
                    session.add(t)
                session.commit()

            st.toast(f"Settled {len(tx_ids_to_settle)} transactions!")
            st.rerun()

    with c2:
        st.caption("Clicking the button will mark the transactions below as resolved.")

    # Data Table
    display_cols = ["date", "description", "category", "amount"]
    st.dataframe(group_df[display_cols], use_container_width=True, hide_index=True)

    st.divider()
