import streamlit as st
import pandas as pd
from datetime import datetime
import hashlib
from src.database import get_session
from src.models import Account, Transaction, Category
from sqlmodel import select
import altair as alt

st.set_page_config(page_title="Funds & Balances", layout="wide")
st.title("🏦 Funds & Balances")

session = get_session()


# Helper
def generate_hash(date, desc, amount):
    raw = f"{date}{desc}{amount}virtual"
    return hashlib.md5(raw.encode()).hexdigest()


tab1, tab2, tab3 = st.tabs(
    ["💰 Account Balances", "📅 Reserve Funds", "⚖️ Reconcile Expenses"]
)

# =======================================================
# TAB 1: ACCOUNT BALANCES
# =======================================================
with tab1:
    st.subheader("Real Bank Balances")
    st.info(
        "Set your starting balance. The app calculates the rest based on REAL transactions (ignoring virtual reservations)."
    )

    accounts = session.exec(select(Account)).all()

    # Input for Initial Balances
    with st.expander("✏️ Edit Starting Balances"):
        with st.form("init_bal_form"):
            updates = {}
            cols = st.columns(3)
            for i, acc in enumerate(accounts):
                with cols[i % 3]:
                    val = st.number_input(
                        f"{acc.name} Start", value=acc.initial_balance, step=100.0
                    )
                    updates[aid := acc.id] = val

            if st.form_submit_button("Save Starting Balances"):
                for aid, val in updates.items():
                    a = session.get(Account, aid)
                    a.initial_balance = val
                    session.add(a)
                session.commit()
                st.success("Updated!")
                st.rerun()

    # Calculate Running Balances
    bal_data = []

    # Get all REAL transactions
    real_txs = session.exec(
        select(Transaction).where(Transaction.is_virtual == False)
    ).all()
    tx_df = pd.DataFrame([t.model_dump() for t in real_txs])

    total_assets = 0

    col_metrics = st.columns(len(accounts))

    for idx, acc in enumerate(accounts):
        start = acc.initial_balance

        # Sum transactions for this account
        if not tx_df.empty:
            acc_tx = tx_df[tx_df["account_id"] == acc.id]
            movement = acc_tx["amount"].sum()
        else:
            movement = 0.0

        final_bal = start + movement
        total_assets += final_bal

        col_metrics[idx].metric(
            label=acc.name,
            value=f"€{final_bal:,.2f}",
            delta=f"From Start: €{movement:,.2f}",
        )

    st.divider()
    st.metric("Total Liquid Assets", f"€{total_assets:,.2f}")

# =======================================================
# TAB 2: RESERVE FUNDS (VIRTUAL SPENDING)
# =======================================================
with tab2:
    st.subheader("Create a Reservation")
    st.markdown(
        """
    Create a **Virtual Expense** now (e.g., "Tax Fund").
    - It **WILL** count as spending in your Home dashboard immediately.
    - It **WILL NOT** reduce the Bank Balance in Tab 1.
    """
    )

    cats = session.exec(select(Category)).all()
    cat_lookup = {c.name: c.id for c in cats}

    with st.form("reserve_form"):
        col1, col2 = st.columns(2)
        r_desc = col1.text_input("Description", placeholder="e.g. Reserved for Car Tax")
        r_amount = col2.number_input(
            "Amount to Reserve (Negative)", step=10.0, max_value=0.0, value=-100.0
        )

        col3, col4 = st.columns(2)
        r_cat = col3.selectbox("Category", [c.name for c in cats])
        r_date = col4.date_input("Reservation Date", value=datetime.now())

        if st.form_submit_button("Reserve Money"):
            # Create Virtual Transaction
            tx_hash = generate_hash(str(r_date), r_desc, r_amount)

            # We assign it to the Default Account of the category, or the first account found
            cat_obj = session.get(Category, cat_lookup[r_cat])
            acc_id = (
                cat_obj.default_account_id
                if cat_obj.default_account_id
                else accounts[0].id
            )

            vt = Transaction(
                date=str(r_date),
                description=f"Reserved: {r_desc}",
                amount=r_amount,
                category_id=cat_lookup[r_cat],
                account_id=acc_id,
                unique_hash=tx_hash,
                is_virtual=True,
                is_settled=False,
            )
            session.add(vt)
            session.commit()
            st.success("Fund Reserved! This now appears as spending in your Dashboard.")

# =======================================================
# TAB 3: RECONCILE (MANY-TO-MANY)
# =======================================================
with tab3:
    st.subheader("Settle Reservations")
    st.info(
        "Match multiple 'Reserved' items (e.g., 2 monthly savings) with real payments (e.g., 1 bi-monthly bill)."
    )

    # 1. Get Active Reservations (Virtual + Not Settled)
    reservations = session.exec(
        select(Transaction).where(
            Transaction.is_virtual == True, Transaction.is_settled == False
        )
    ).all()

    # 2. Get Uncategorized/Real Expenses (Real + Not Transfer)
    transfer_cat = session.exec(
        select(Category).where(Category.name == "Transfer")
    ).first()
    transfer_id = transfer_cat.id if transfer_cat else -1

    real_expenses = session.exec(
        select(Transaction)
        .where(
            Transaction.is_virtual == False,
            Transaction.amount < 0,
            Transaction.category_id != transfer_id,
        )
        .order_by(Transaction.date.desc())
    ).all()
    st.metric("Total Reserved", f"€{sum([r.amount for r in reservations]):,.2f}")

    col_res, col_real = st.columns(2)

    # --- LEFT COLUMN: RESERVATIONS ---

    with col_res:
        st.markdown("### 1. Select Reservations")

        if not reservations:
            st.info("No active reservations.")
            selected_res_ids = []
        else:
            # Prepare DF for Data Editor
            res_data = [
                {
                    "Select": False,
                    "ID": r.id,
                    "Date": r.date,
                    "Desc": r.description,
                    "Amount": r.amount,
                }
                for r in reservations
            ]
            df_res = pd.DataFrame(res_data)

            edited_res = st.data_editor(
                df_res,
                column_config={
                    "Select": st.column_config.CheckboxColumn(default=False),
                    "ID": None,  # Hide ID
                    "Amount": st.column_config.NumberColumn(format="%.2f"),
                },
                hide_index=True,
                use_container_width=True,
                key="editor_res",
            )
            selected_res_ids = edited_res[edited_res["Select"]]["ID"].tolist()

    # --- RIGHT COLUMN: REAL PAYMENTS ---
    with col_real:
        st.markdown("### 2. Select Real Payments")
        # Search Filter
        search_real = st.text_input(
            "🔍 Filter Real Payments", placeholder="Search description..."
        )

        filtered_real = real_expenses
        if search_real:
            filtered_real = [
                t for t in real_expenses if search_real.lower() in t.description.lower()
            ]

        if not filtered_real:
            st.info("No real expenses found.")
            selected_real_ids = []
        else:
            real_data = [
                {
                    "Select": False,
                    "ID": t.id,
                    "Date": t.date,
                    "Desc": t.description,
                    "Amount": t.amount,
                }
                for t in filtered_real
            ]
            df_real_tx = pd.DataFrame(real_data)

            edited_real = st.data_editor(
                df_real_tx,
                column_config={
                    "Select": st.column_config.CheckboxColumn(default=False),
                    "ID": None,
                    "Amount": st.column_config.NumberColumn(format="%.2f"),
                },
                hide_index=True,
                use_container_width=True,
                key="editor_real",
            )
            selected_real_ids = edited_real[edited_real["Select"]]["ID"].tolist()

    # --- RECONCILIATION LOGIC ---
    st.divider()

    if selected_res_ids or selected_real_ids:
        # Calculate Totals
        # Note: Amounts are negative for expenses

        # Get actual objects
        sel_res_objs = [r for r in reservations if r.id in selected_res_ids]
        sel_real_objs = [t for t in real_expenses if t.id in selected_real_ids]

        total_reserved = sum(r.amount for r in sel_res_objs)
        total_paid = sum(t.amount for t in sel_real_objs)

        # Diff = Paid - Reserved
        # Example: Paid -120, Reserved -100. Diff = -20 (Overspent)
        # Example: Paid -80, Reserved -100. Diff = +20 (Saved)
        diff = total_paid - total_reserved

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Reserved", f"€{total_reserved:,.2f}")
        c2.metric("Total Paid", f"€{total_paid:,.2f}")

        status_color = "off"
        status_msg = "Balanced"
        if diff < -0.01:
            status_color = "inverse"  # Red
            status_msg = "Overspent"
        elif diff > 0.01:
            status_color = "normal"  # Green
            status_msg = "Under Budget (Saved)"

        c3.metric(
            "Difference", f"€{diff:,.2f}", delta=status_msg, delta_color=status_color
        )

        if st.button("🔗 Settle Selected Transactions", type="primary"):
            if not selected_real_ids and not selected_res_ids:
                st.error("Please select at least one transaction.")
            else:
                # 1. Update Real Transactions -> Transfer
                for t in sel_real_objs:
                    if transfer_cat:
                        t.category_id = transfer_cat.id
                    session.add(t)

                # 2. Update Virtual Transactions -> Settled
                for r in sel_res_objs:
                    r.is_settled = True
                    session.add(r)

                # 3. Create Adjustment if needed
                if abs(diff) > 0.01:
                    # Pick a reference category/account from the selections
                    ref_cat_id = (
                        sel_res_objs[0].category_id
                        if sel_res_objs
                        else (sel_real_objs[0].category_id if sel_real_objs else None)
                    )
                    ref_acc_id = (
                        sel_real_objs[0].account_id
                        if sel_real_objs
                        else (sel_res_objs[0].account_id if sel_res_objs else None)
                    )
                    ref_desc = (
                        sel_res_objs[0].description
                        if sel_res_objs
                        else "Manual Adjustment"
                    )

                    adj_hash = generate_hash(
                        str(datetime.now()), f"Adj: {ref_desc}", diff
                    )

                    adj_tx = Transaction(
                        date=datetime.now().strftime("%Y-%m-%d"),
                        description=f"Adjustment: {ref_desc} (Reconciled)",
                        amount=diff,
                        category_id=ref_cat_id,
                        account_id=ref_acc_id,
                        unique_hash=adj_hash,
                        is_virtual=True,  # Counts towards metrics
                        is_settled=True,  # Immediately settled
                    )
                    session.add(adj_tx)

                session.commit()
                st.balloons()
                st.success("Reconciliation Complete! Metrics updated.")
                st.rerun()
