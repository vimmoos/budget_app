import streamlit as st
import pandas as pd
from src.models import Transaction, Category, CategoryRule, Account
from src.database import get_session
from sqlmodel import select
import hashlib
import re
import json

st.set_page_config(page_title="Import Data", layout="wide")
st.title("📤 Import Bank Statement")

session = get_session()

# --- 1. SELECT BANK ---
accounts = session.exec(select(Account)).all()
if not accounts:
    st.error("No accounts found. Please restart the app or go to Manage Banks.")
    st.stop()

selected_account_name = st.selectbox(
    "Select Account for this Statement:", [a.name for a in accounts]
)
selected_account = next(a for a in accounts if a.name == selected_account_name)

# --- LOAD SAVED CONFIG ---
saved_config = {}
if selected_account.import_config:
    try:
        saved_config = json.loads(selected_account.import_config)
    except:
        pass

uploaded_file = st.file_uploader("Upload Statement", type=["csv", "xlsx", "xls"])


def generate_hash(date, desc, amount):
    raw = f"{date}{desc}{amount}"
    return hashlib.md5(raw.encode()).hexdigest()


def find_header_row(df):
    keywords = [
        "date",
        "data",
        "description",
        "descrizione",
        "amount",
        "importo",
        "addebiti",
        "accrediti",
    ]
    for idx, row in df.head(20).iterrows():
        row_str = " ".join(row.astype(str)).lower()
        matches = sum(1 for k in keywords if k in row_str)
        if matches >= 2:
            return idx
    return 0


# --- SMART DATE PARSER ---
def parse_date(date_val, fmt_mode="Auto"):
    """
    Parses dates based on user selection.
    """
    s_val = str(date_val).strip()
    try:
        if fmt_mode == "Day-Month-Year (DD/MM/YYYY)":
            # Force Day First (European)
            return pd.to_datetime(s_val, dayfirst=True).strftime("%Y-%m-%d")

        elif fmt_mode == "Month-Day-Year (MM/DD/YYYY)":
            # Force Month First (US)
            return pd.to_datetime(s_val, dayfirst=False).strftime("%Y-%m-%d")

        elif fmt_mode == "Year-Month-Day (YYYY-MM-DD)":
            # Force Year First (ISO)
            return pd.to_datetime(s_val, yearfirst=True).strftime("%Y-%m-%d")

        else:
            # Auto Mode (Heuristic)
            if re.match(r"^\d{4}", s_val):
                return pd.to_datetime(s_val, yearfirst=True).strftime("%Y-%m-%d")
            else:
                return pd.to_datetime(s_val, dayfirst=True).strftime("%Y-%m-%d")
    except Exception:
        return str(date_val)  # Parsing failed, keep original


if uploaded_file:
    # --- LOAD DATA ---
    try:
        if uploaded_file.name.endswith(".csv"):
            preview_df = pd.read_csv(uploaded_file, header=None, nrows=20)
            header_idx = find_header_row(preview_df)
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, header=header_idx)
        else:
            preview_df = pd.read_excel(uploaded_file, header=None, nrows=20)
            header_idx = find_header_row(preview_df)
            uploaded_file.seek(0)
            df = pd.read_excel(uploaded_file, header=header_idx)

        st.success(f"File loaded for **{selected_account_name}**!")

    except Exception as e:
        st.error(f"Error reading file: {e}")
        st.stop()

    # --- MAP COLUMNS ---
    all_cols = list(df.columns)
    col1, col2 = st.columns(2)

    # Date Col
    date_idx = 0
    if saved_config.get("date_col") in all_cols:
        date_idx = all_cols.index(saved_config["date_col"])
    date_col = col1.selectbox("Date Column", all_cols, index=date_idx)

    # Date Format (New)
    fmt_options = [
        "Auto",
        "Day-Month-Year (DD/MM/YYYY)",
        "Month-Day-Year (MM/DD/YYYY)",
        "Year-Month-Day (YYYY-MM-DD)",
    ]
    fmt_idx = 0
    if saved_config.get("date_fmt") in fmt_options:
        fmt_idx = fmt_options.index(saved_config["date_fmt"])

    date_fmt = col1.selectbox(
        "Date Format",
        fmt_options,
        index=fmt_idx,
        help="Force a specific format if dates are wrong.",
    )

    # Desc Col
    default_desc = []
    if saved_config.get("desc_cols"):
        default_desc = [c for c in saved_config["desc_cols"] if c in all_cols]
    if not default_desc and len(all_cols) > 1:
        default_desc = [all_cols[1]]

    desc_cols = col2.multiselect(
        "Description Column(s)", all_cols, default=default_desc
    )

    st.markdown("### Amount Settings")
    saved_mode = saved_config.get("amount_mode", "Single Column")
    if saved_mode not in ["Single Column", "Separate Debit/Credit"]:
        saved_mode = "Single Column"
    amount_mode = st.radio(
        "Format",
        ["Single Column", "Separate Debit/Credit"],
        horizontal=True,
        index=0 if saved_mode == "Single Column" else 1,
    )

    amt_col, debit_col, credit_col = None, None, None
    if amount_mode == "Single Column":
        amt_idx = 0
        if saved_config.get("amt_col") in all_cols:
            amt_idx = all_cols.index(saved_config["amt_col"])
        elif len(all_cols) > 2:
            amt_idx = 2
        amt_col = st.selectbox("Select Amount Column", all_cols, index=amt_idx)
    else:
        c1, c2 = st.columns(2)
        deb_idx = 0
        if saved_config.get("debit_col") in all_cols:
            deb_idx = all_cols.index(saved_config["debit_col"])
        debit_col = c1.selectbox("Debit Column", all_cols, index=deb_idx)

        cred_idx = 0
        if saved_config.get("credit_col") in all_cols:
            cred_idx = all_cols.index(saved_config["credit_col"])
        credit_col = c2.selectbox("Credit Column", all_cols, index=cred_idx)

    # --- PREVIEW ---
    st.divider()
    st.subheader("3. Verify Data")

    preview_data = []
    for index, row in df.head(5).iterrows():
        try:
            # Apply Selected Date Format
            raw_date = row[date_col]
            clean_date = parse_date(raw_date, date_fmt)

            if desc_cols:
                parts = [str(row[c]).strip() for c in desc_cols if pd.notna(row[c])]
                desc_preview = " ".join(parts)
            else:
                desc_preview = "NO DESC"

            if amount_mode == "Single Column":
                raw = (
                    str(row[amt_col])
                    .replace("€", "")
                    .replace("$", "")
                    .replace(",", ".")
                    .strip()
                )
                amt_preview = float(clean) if (clean := raw) else 0.0
            else:
                c_val = pd.to_numeric(row[credit_col], errors="coerce")
                d_val = pd.to_numeric(row[debit_col], errors="coerce")
                c_val = c_val if pd.notna(c_val) else 0.0
                d_val = d_val if pd.notna(d_val) else 0.0
                amt_preview = c_val - d_val

            preview_data.append(
                {
                    "Original Date": raw_date,
                    "Parsed Date": clean_date,  # Verify this column!
                    "Description": desc_preview,
                    "Amount": amt_preview,
                }
            )
        except Exception as e:
            preview_data.append({"Error": str(e)})

    st.dataframe(pd.DataFrame(preview_data), use_container_width=True)

    # --- PROCESS BUTTON ---
    if st.button("Process & Save Transactions", type="primary"):
        if not desc_cols:
            st.error("Please select at least one Description column.")
            st.stop()

        # Save Config
        new_config = {
            "date_col": date_col,
            "date_fmt": date_fmt,  # <--- Saved here
            "desc_cols": desc_cols,
            "amount_mode": amount_mode,
            "amt_col": amt_col,
            "debit_col": debit_col,
            "credit_col": credit_col,
        }
        selected_account.import_config = json.dumps(new_config)
        session.add(selected_account)
        session.commit()

        uncat = session.exec(
            select(Category).where(Category.name == "Uncategorized")
        ).first()
        if not uncat:
            uncat = Category(
                name="Uncategorized", group="Discretionary", type="Expense"
            )
            session.add(uncat)
            session.commit()
            session.refresh(uncat)

        rules = session.exec(select(CategoryRule)).all()
        count = 0

        for index, row in df.iterrows():
            try:
                # Apply Date Format
                date_val = parse_date(row[date_col], date_fmt)

                parts = [str(row[c]).strip() for c in desc_cols if pd.notna(row[c])]
                desc_val = " ".join(parts)

                if amount_mode == "Single Column":
                    raw = str(row[amt_col]).replace("€", "").replace(",", ".").strip()
                    amount = float(raw) if raw else 0.0
                else:
                    c_val = pd.to_numeric(row[credit_col], errors="coerce")
                    d_val = pd.to_numeric(row[debit_col], errors="coerce")
                    c_val = c_val if pd.notna(c_val) else 0.0
                    d_val = d_val if pd.notna(d_val) else 0.0
                    amount = c_val - d_val

                if amount == 0:
                    continue

                tx_hash = generate_hash(date_val, desc_val, amount)
                existing = session.exec(
                    select(Transaction).where(Transaction.unique_hash == tx_hash)
                ).first()

                if not existing:
                    assigned_cat_id = uncat.id
                    for rule in rules:
                        if rule.keyword:
                            try:
                                if re.search(rule.keyword, desc_val, re.IGNORECASE):
                                    assigned_cat_id = rule.category_id
                                    break
                            except re.error:
                                continue

                    tx = Transaction(
                        date=date_val,
                        description=desc_val,
                        amount=amount,
                        category_id=assigned_cat_id,
                        account_id=selected_account.id,
                        unique_hash=tx_hash,
                    )
                    session.add(tx)
                    count += 1

            except Exception as e:
                pass

        session.commit()
        st.success(f"Imported {count} transactions into {selected_account_name}!")
