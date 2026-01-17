import streamlit as st
import pandas as pd
import re
import hashlib
from datetime import datetime
from src.database import get_session
from src.models import Transaction, Category, Account  # <--- Imported Account
from sqlmodel import select
import altair as alt

st.title("📝 Transaction Manager")

session = get_session()

# Load Categories & Accounts
cats = session.exec(select(Category)).all()
accounts = session.exec(select(Account)).all()  # <--- Fetch Accounts

cat_names = {c.id: c.name for c in cats}
cat_lookup = {c.name: c.id for c in cats}

# Create Account Lookup
acc_names = {a.id: a.name for a in accounts}  # <--- ID to Name
acc_lookup = {a.name: a.id for a in accounts}  # <--- Name to ID
cat_options = ["All"] + [c.name for c in cats]


# Helper to generate unique ID for manual entries
def generate_hash(date, desc, amount):
    raw = f"{date}{desc}{amount}virtual"
    return hashlib.md5(raw.encode()).hexdigest()


# ==========================================
# ➕ MANUAL TRANSACTION CREATOR
# ==========================================
with st.expander("➕ Add Manual Transaction", expanded=False):
    st.caption(
        "Use this for expenses that don't have a bank transaction yet (e.g., monthly tax allocation)."
    )

    with st.form("manual_tx_form"):
        col_d, col_desc = st.columns([1, 2])
        m_date = col_d.date_input("Date", value=datetime.now())
        m_desc = col_desc.text_input(
            "Description", placeholder="e.g. Monthly Tax Allocation"
        )

        col_amt, col_cat, col_acc = st.columns(3)
        m_amount = col_amt.number_input(
            "Amount",
            step=1.0,
            format="%.2f",
            help="Negative for expense (-50), Positive for income (50)",
        )
        m_cat_name = col_cat.selectbox("Category", [c.name for c in cats])
        m_acc_name = col_acc.selectbox("Account", list(acc_lookup.keys()))

        if st.form_submit_button("Add Transaction"):
            if m_amount != 0 and m_desc:
                tx_hash = generate_hash(str(m_date), m_desc, m_amount)
                existing = session.exec(
                    select(Transaction).where(Transaction.unique_hash == tx_hash)
                ).first()
                if existing:
                    st.error("Transaction already exists!")
                else:
                    new_tx = Transaction(
                        date=str(m_date),
                        description=m_desc,
                        amount=m_amount,
                        category_id=cat_lookup[m_cat_name],
                        account_id=acc_lookup[m_acc_name],
                        unique_hash=tx_hash,
                    )
                    session.add(new_tx)
                    session.commit()
                    st.success("Transaction Added!")
                    st.rerun()
            else:
                st.error("Please enter an amount and description.")

# ==========================================
# 🔄 TRANSFER MATCHING WIZARD
# ==========================================
with st.expander("🔄 Detect & Link Internal Transfers", expanded=False):
    transfer_cat_id = cat_lookup.get("Transfer")
    if not transfer_cat_id:
        st.error("Category 'Transfer' not found. Please reload app or check database.")
    else:
        tab_auto, tab_manual = st.tabs(["🤖 Auto-Detect", "🔗 Manual Link"])

        # --- TAB 1: AUTO DETECT ---
        with tab_auto:
            st.write("Automatically finds matching amounts (within 3 days).")
            all_tx = session.exec(select(Transaction)).all()

            candidates_pos = [
                t for t in all_tx if t.amount > 0 and t.category_id != transfer_cat_id
            ]
            candidates_neg = [
                t for t in all_tx if t.amount < 0 and t.category_id != transfer_cat_id
            ]

            matches = []
            used_ids = set()

            for pos in candidates_pos:
                if pos.id in used_ids:
                    continue
                for neg in candidates_neg:
                    if neg.id in used_ids:
                        continue
                    if abs(pos.amount) == abs(neg.amount):
                        try:
                            d1 = pd.to_datetime(pos.date)
                            d2 = pd.to_datetime(neg.date)
                            delta = abs((d1 - d2).days)
                            if delta <= 3:
                                matches.append((pos, neg, delta))
                                used_ids.add(pos.id)
                                used_ids.add(neg.id)
                                break
                        except:
                            pass

            if matches:
                st.info(f"Found {len(matches)} pairs.")
                match_data = []
                for p, n, d in matches:
                    match_data.append(
                        {
                            "Select": True,
                            "Date": p.date,
                            "In ($)": p.amount,
                            "Desc 1": p.description,
                            "Out ($)": n.amount,
                            "Desc 2": n.description,
                            "id_pos": p.id,
                            "id_neg": n.id,
                        }
                    )
                df_matches = pd.DataFrame(match_data)
                edited_matches = st.data_editor(
                    df_matches,
                    column_config={
                        "Select": st.column_config.CheckboxColumn(default=True),
                        "id_pos": None,
                        "id_neg": None,
                    },
                    hide_index=True,
                    use_container_width=True,
                )
                if st.button("Mark Auto-Matches as Transfer"):
                    count = 0
                    for index, row in edited_matches.iterrows():
                        if row["Select"]:
                            id_pos = int(row["id_pos"])
                            id_neg = int(row["id_neg"])
                            t1 = session.get(Transaction, id_pos)
                            t2 = session.get(Transaction, id_neg)
                            if t1 and t2:
                                t1.category_id = transfer_cat_id
                                t2.category_id = transfer_cat_id
                                session.add(t1)
                                session.add(t2)
                                count += 2
                    session.commit()
                    st.success(f"Updated {count} transactions!")
                    st.rerun()
            else:
                st.write("No auto-matches found.")

        # --- TAB 2: MANUAL LINK ---
        with tab_manual:
            st.write("Select two transactions to force-link as a Transfer.")
            col_search1, col_search2 = st.columns(2)

            def fmt_tx(t):
                return f"[{t.date}] {t.amount} - {t.description[:30]}"

            with col_search1:
                search_txt_1 = st.text_input(
                    "Search A", placeholder="Type...", key="s1"
                )
                tx_list_1 = session.exec(
                    select(Transaction).where(
                        Transaction.category_id != transfer_cat_id
                    )
                ).all()
                if search_txt_1:
                    tx_list_1 = [
                        t
                        for t in tx_list_1
                        if search_txt_1.lower() in t.description.lower()
                        or str(t.amount) in search_txt_1
                    ]
                tx_list_1.sort(key=lambda x: x.date, reverse=True)
                sel_tx_1 = st.selectbox(
                    "Transaction 1",
                    options=tx_list_1[:50],
                    format_func=fmt_tx,
                    key="k1",
                )

            with col_search2:
                search_txt_2 = st.text_input(
                    "Search B", placeholder="Type...", key="s2"
                )
                tx_list_2 = session.exec(
                    select(Transaction).where(
                        Transaction.category_id != transfer_cat_id
                    )
                ).all()
                if search_txt_2:
                    tx_list_2 = [
                        t
                        for t in tx_list_2
                        if search_txt_2.lower() in t.description.lower()
                        or str(t.amount) in search_txt_2
                    ]
                tx_list_2.sort(key=lambda x: x.date, reverse=True)
                sel_tx_2 = st.selectbox(
                    "Transaction 2",
                    options=tx_list_2[:50],
                    format_func=fmt_tx,
                    key="k2",
                )

            st.divider()
            if st.button("🔗 Link as Transfer"):
                if sel_tx_1 and sel_tx_2 and sel_tx_1.id != sel_tx_2.id:
                    t1 = session.get(Transaction, sel_tx_1.id)
                    t2 = session.get(Transaction, sel_tx_2.id)
                    if t1 and t2:
                        t1.category_id = transfer_cat_id
                        t2.category_id = transfer_cat_id
                        session.add(t1)
                        session.add(t2)
                        session.commit()
                        st.success("Linked successfully!")
                        st.rerun()
                else:
                    st.error("Please select two different transactions.")

# --- 🔎 FILTERING SECTION ---
st.divider()
with st.expander("🔎 Filter Options", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        filter_cat = st.multiselect("Category", options=[c.name for c in cats])

        date_mode = st.radio("Date Mode", ["Month", "Custom Range"], horizontal=True)
        filter_date_range = []
        filter_month = None
        filter_year = None

        if date_mode == "Custom Range":
            filter_date_range = st.date_input("Select Range", value=[])
        else:
            c_m, c_y = st.columns(2)
            current_month_idx = datetime.now().month - 1
            filter_month = c_m.selectbox("Month", range(1, 13), index=current_month_idx)
            filter_year = c_y.number_input(
                "Year", min_value=2020, max_value=2030, value=datetime.now().year
            )

    with col2:
        col_amt_op, col_amt_val = st.columns([1, 2])
        with col_amt_op:
            amt_operator = st.selectbox("Op", ["Any", ">", "<", "="], index=0)
        with col_amt_val:
            amt_value = st.number_input("Amount", step=1.0)
        filter_desc = st.text_input("Description (Regex)", help="e.g., '^Amazon'")

# --- 📥 DATA LOADING & FILTERING ---
query = select(Transaction)
if filter_cat:
    selected_cat_ids = [cat_lookup[name] for name in filter_cat]
    query = query.where(Transaction.category_id.in_(selected_cat_ids))

transactions = session.exec(query).all()

data = []
for t in transactions:
    # 1. Date Filter Logic
    try:
        t_date_obj = pd.to_datetime(t.date).date()
    except:
        continue

    if date_mode == "Custom Range" and filter_date_range:
        if len(filter_date_range) == 2:
            start_date, end_date = filter_date_range
            if not (start_date <= t_date_obj <= end_date):
                continue
        elif len(filter_date_range) == 1:
            if t_date_obj != filter_date_range[0]:
                continue

    elif date_mode == "Month":
        if t_date_obj.month != filter_month or t_date_obj.year != filter_year:
            continue

    # 2. Amount Filter
    if amt_operator != "Any":
        if amt_operator == ">" and not (t.amount > amt_value):
            continue
        if amt_operator == "<" and not (t.amount < amt_value):
            continue
        if amt_operator == "=" and not (t.amount == amt_value):
            continue

    # 3. Description Filter
    if filter_desc:
        if not re.search(filter_desc, t.description, re.IGNORECASE):
            continue

    data.append(
        {
            "ID": t.id,
            "Date": t.date,
            "Account": acc_names.get(
                t.account_id, "Unknown"
            ),  # <--- Added Account Name
            "Description": t.description,
            "Amount": t.amount,
            "Category": cat_names.get(t.category_id, "Uncategorized"),
            "Delete": False,
        }
    )

df = pd.DataFrame(data)

# --- 📊 VISUALIZATION ---
if not df.empty:
    st.divider()
    st.subheader("📈 Filtered Overview")

    excluded_cats_viz = ["Transfer", "Investments"]
    df_viz = df[~df["Category"].isin(excluded_cats_viz)].copy()

    if not df_viz.empty:
        expenses = df_viz[df_viz["Amount"] < 0].copy()
        expenses["AbsAmount"] = expenses["Amount"].abs()
        income = df_viz[df_viz["Amount"] > 0].copy()

        col1, col2 = st.columns(2)
        with col1:
            st.caption("Spending by Category")
            if not expenses.empty:
                chart_exp = (
                    alt.Chart(expenses)
                    .mark_bar()
                    .encode(
                        x=alt.X("sum(AbsAmount)", title="Total ($)"),
                        y=alt.Y("Category", sort="-x"),
                        color="Category",
                        tooltip=[
                            "Category",
                            alt.Tooltip("sum(AbsAmount)", format="$.2f"),
                        ],
                    )
                    .properties(height=300)
                )
                st.altair_chart(chart_exp, use_container_width=True)
                st.metric("Total Spending", f"${expenses['AbsAmount'].sum():,.2f}")

        with col2:
            st.caption("Income by Category")
            if not income.empty:
                chart_inc = (
                    alt.Chart(income)
                    .mark_bar()
                    .encode(
                        x=alt.X("sum(Amount)", title="Total ($)"),
                        y=alt.Y("Category", sort="-x"),
                        color="Category",
                        tooltip=["Category", alt.Tooltip("sum(Amount)", format="$.2f")],
                    )
                    .properties(height=300)
                )
                st.altair_chart(chart_inc, use_container_width=True)
                st.metric("Total Income", f"${income['Amount'].sum():,.2f}")
    else:
        st.info("No relevant data (only Transfers/Investments) in view.")
    st.divider()

# --- 📝 DATA EDITOR & DELETE ---
if not df.empty:
    st.info(f"Showing {len(df)} transactions.")

    edited_df = st.data_editor(
        df,
        column_config={
            "Category": st.column_config.SelectboxColumn(
                options=list(cat_lookup.keys()), required=True
            ),
            "Delete": st.column_config.CheckboxColumn(default=False),
            "ID": None,
            "Amount": st.column_config.NumberColumn(format="%.2f"),
            "Account": st.column_config.TextColumn(
                "Account", disabled=True
            ),  # <--- Displayed but disabled
        },
        disabled=[
            "Date",
            "Description",
            "Amount",
            "Account",
        ],  # <--- Added Account to disabled list
        hide_index=True,
        use_container_width=True,
    )

    col_save, col_del = st.columns(2)

    with col_save:
        if st.button("Save Changes", type="primary"):
            changes_count = 0
            for index, row in edited_df.iterrows():
                if not row["Delete"]:
                    tx_id = row["ID"]
                    new_cat_name = row["Category"]
                    new_cat_id = cat_lookup.get(new_cat_name)

                    tx = session.get(Transaction, tx_id)
                    if tx and tx.category_id != new_cat_id:
                        tx.category_id = new_cat_id
                        session.add(tx)
                        changes_count += 1
            session.commit()
            if changes_count > 0:
                st.success(f"Updated {changes_count} transactions!")
                st.rerun()
            else:
                st.info("No category changes detected.")

    with col_del:
        if st.button("🗑️ Delete Selected"):
            to_delete = edited_df[edited_df["Delete"] == True]
            if not to_delete.empty:
                count = 0
                for index, row in to_delete.iterrows():
                    tx_id = row["ID"]
                    tx = session.get(Transaction, tx_id)
                    if tx:
                        session.delete(tx)
                        count += 1
                session.commit()
                st.warning(f"Deleted {count} transactions.")
                st.rerun()
            else:
                st.info(
                    "Check the 'Delete' box on rows you want to remove, then click here."
                )
else:
    st.warning("No transactions match your filters.")
