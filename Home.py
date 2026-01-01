import streamlit as st
from sqlmodel import select
import pandas as pd
from src.database import init_db, get_session
from src.models import Transaction, Category, Budget
from src.analytics import create_sankey, create_bullet_chart
from datetime import datetime
import altair as alt

st.set_page_config(page_title="Personal Finance OS", layout="wide")

# st.markdown(
#     """
#     <link rel="manifest" href="manifest.json">
#     <meta name="mobile-web-app-capable" content="yes">
#     <meta name="apple-mobile-web-app-capable" content="yes">
#     <meta name="theme-color" content="#ffffff">
# """,
#     unsafe_allow_html=True,
# )

# Initialize DB
init_db()

st.title("💰 Financial App")

# Sidebar Filters
st.sidebar.header("Time Period")
selected_year = st.sidebar.number_input(
    "Year", min_value=2020, max_value=2030, value=datetime.now().year
)
selected_month = st.sidebar.selectbox(
    "Month", range(1, 13), index=datetime.now().month - 1
)


def get_data(month, year):
    with get_session() as session:
        # Fetch Transactions (Monthly)
        query_tx = (
            select(
                Transaction,
                Category.name.label("category_name"),
                Category.group,
                Category.type,
            )
            .join(Category)
            .where(Transaction.date.contains(f"{year}-{month:02d}"))
        )
        tx_results = session.exec(query_tx).all()

        # Fetch Budgets (Global - No Date Filter)
        query_bd = select(Budget, Category.name.label("category_name")).join(Category)
        bd_results = session.exec(query_bd).all()

    return tx_results, bd_results


tx_data, bd_data = get_data(selected_month, selected_year)

# Convert to DataFrames
if tx_data:
    clean_data = []
    for t, cat_name, cat_group, cat_type in tx_data:
        row = t.model_dump()
        row["category_name"] = cat_name
        row["group"] = cat_group
        row["type"] = "Income" if t.amount > 0 else "Expense"
        clean_data.append(row)
    df_tx = pd.DataFrame(clean_data)
else:
    df_tx = pd.DataFrame(columns=["amount", "type", "category_name", "group"])

if bd_data:
    clean_bd = []
    for b, cat_name in bd_data:
        row = b.model_dump()
        row["category_name"] = cat_name
        clean_bd.append(row)
    df_bd = pd.DataFrame(clean_bd)
else:
    df_bd = pd.DataFrame(columns=["category_name", "amount"])

# --- KPI Metrics ---
col1, col2, col3 = st.columns(3)

# Filter exclusions
excluded_cats = ["Transfer"]
mask_real = ~df_tx["category_name"].isin(excluded_cats + ["Investments"])
df_real = df_tx[mask_real]

total_income = df_real[df_real["amount"] > 0]["amount"].sum()
total_spend_actual = df_real[df_real["amount"] < 0]["amount"].sum()
savings_rate = (
    ((total_income + total_spend_actual) / total_income * 100)
    if total_income > 0
    else 0
)

col1.metric("Total Income", f"${total_income:,.2f}")
col2.metric(
    "Total Spend", f"${total_spend_actual:,.2f}", delta=f"{total_spend_actual:,.2f}"
)
col3.metric("Savings Rate", f"{savings_rate:.1f}%")

st.divider()

df_real_with_inv = df_tx[~df_tx["category_name"].isin(excluded_cats)]
df_real = df_real_with_inv
# --- 📊 ANALYSIS SECTION ---
if not df_real.empty and total_spend_actual < 0:
    st.subheader("📊 Analysis by Group & Category")
    spend_df = df_real[df_real["amount"] < 0].copy()
    spend_df["amount"] = spend_df["amount"].abs()

    # Group Breakdown
    grp_stats = spend_df.groupby("group")["amount"].sum()
    groups_found = grp_stats.index.tolist()
    if groups_found:
        cols_grp = st.columns(len(groups_found))
        for idx, grp_name in enumerate(groups_found):
            val = grp_stats[grp_name]
            pct = (val / total_income * 100) if total_income > 0 else 0
            cols_grp[idx].metric(
                f"{grp_name} (%)", f"{pct:.1f}%", help=f"Total: ${val:,.2f}"
            )

    st.divider()

    # Category Breakdown
    cat_stats = spend_df.groupby("category_name")["amount"].sum().reset_index()
    total_abs_spend = spend_df["amount"].sum()
    cat_stats["share"] = (cat_stats["amount"] / total_abs_spend) * 100
    cat_stats = cat_stats.sort_values(by="share", ascending=False).head(10)

    st.dataframe(
        cat_stats,
        column_config={
            "category_name": "Category",
            "amount": st.column_config.NumberColumn("Amount", format="$%.2f"),
            "share": st.column_config.ProgressColumn(
                "% of Expenses", format="%.1f%%", min_value=0, max_value=100
            ),
        },
        hide_index=True,
        use_container_width=True,
    )

st.divider()

# --- 1. SPENDING FLOW (Sankey) ---
st.subheader("Spending Flow")
expenses_df = df_real[df_real["amount"] < 0].copy()
if not expenses_df.empty:
    expenses_df["amount"] = expenses_df["amount"].abs()
    fig_sankey = create_sankey(expenses_df)
    st.plotly_chart(fig_sankey, use_container_width=True)
else:
    st.info("No expense data found.")

st.divider()

# --- 2. BUDGET VS REALITY (Grid Layout) ---
c_head, c_toggle = st.columns([3, 1])
with c_head:
    st.subheader("Budget vs. Reality")
with c_toggle:
    hide_exact = st.toggle("Hide Exact Matches", value=True)

if not df_real_with_inv.empty:
    actuals = (
        df_real_with_inv[df_real_with_inv["amount"] < 0]
        .groupby("category_name")["amount"]
        .sum()
        .reset_index()
    )
    actuals["amount"] = actuals["amount"].abs()
else:
    actuals = pd.DataFrame(columns=["category_name", "amount"])

if not df_bd.empty:
    df_bd_clean = df_bd[["category_name", "amount"]].rename(
        columns={"amount": "budget"}
    )
else:
    df_bd_clean = pd.DataFrame(columns=["category_name", "budget"])

merged = pd.merge(actuals, df_bd_clean, on="category_name", how="outer").fillna(0)

if not merged.empty:
    # 1. Filter rows first
    rows_to_display = []
    for index, row in merged.iterrows():
        # Toggle Logic
        if hide_exact and abs(row["amount"] - row["budget"]) < 0.01:
            continue
        # Show if there is budget OR spending
        if row["budget"] > 0 or row["amount"] > 0:
            rows_to_display.append(row)

    # 2. Display in 2-Column Grid
    if rows_to_display:
        cols = st.columns(2)  # Define the grid
        for i, row in enumerate(rows_to_display):
            # i % 2 alternates between 0 (left) and 1 (right)
            with cols[i % 2]:
                fig = create_bullet_chart(
                    row["category_name"], row["amount"], row["budget"]
                )
                st.plotly_chart(fig, use_container_width=True, key=f"bullet_{i}")
    else:
        st.info("All categories match their budget perfectly!")
else:
    st.info("No budget or spending data available.")
