import streamlit as st
from src.database import get_session
from src.models import Category, CategoryRule, Transaction
from sqlmodel import select
import pandas as pd
import re

st.set_page_config(page_title="Settings", layout="wide")
st.title("⚙️ System Settings")

session = get_session()
tab1, tab2 = st.tabs(["🗂️ Categories", "🤖 Automation Rules"])


# --- HELPER FUNCTION ---
def clean_val(value):
    if isinstance(value, list):
        return str(value[0]) if len(value) > 0 else None
    if pd.isna(value):
        return None
    return str(value)


# --- TAB 1: CATEGORIES ---
with tab1:
    st.subheader("Manage Categories")
    categories = session.exec(select(Category)).all()
    cat_data = [c.model_dump() for c in categories]
    df_cat = pd.DataFrame(cat_data)

    if df_cat.empty:
        df_cat = pd.DataFrame(columns=["name", "group", "type"])

    edited_cat = st.data_editor(
        df_cat,
        num_rows="dynamic",
        column_config={
            "id": None,
            "name": "Category Name",
            "group": st.column_config.SelectboxColumn(
                "Group", options=["Needs", "Wants", "Savings", "Income"], required=True
            ),
            "type": st.column_config.SelectboxColumn(
                "Type", options=["Expense", "Income"], required=True
            ),
        },
        use_container_width=True,
        key="cat_editor",
    )

    if st.button("Save Categories", type="primary"):
        current_ids = [
            row["id"] for i, row in edited_cat.iterrows() if pd.notna(row.get("id"))
        ]
        for c in categories:
            if c.id not in current_ids:
                session.delete(c)
        for i, row in edited_cat.iterrows():
            if pd.isna(row.get("id")):
                session.add(
                    Category(name=row["name"], group=row["group"], type=row["type"])
                )
            else:
                existing = session.get(Category, int(row["id"]))
                if existing:
                    existing.name = row["name"]
                    existing.group = row["group"]
                    existing.type = row["type"]
                    session.add(existing)
        session.commit()
        st.success("Categories Saved!")
        st.rerun()

    # --- CSV IMPORT SECTION ---
    st.divider()
    with st.expander("📥 Import Categories from CSV"):
        st.write("Upload a CSV with headers: `name`, `group`, `type`")
        cat_file = st.file_uploader("Upload CSV", type=["csv"], key="cat_imp")

        if cat_file and st.button("Load Categories"):
            try:
                import_df = pd.read_csv(cat_file)

                # Check headers (case insensitive)
                import_df.columns = [c.lower().strip() for c in import_df.columns]
                required = {"name", "group", "type"}

                if not required.issubset(import_df.columns):
                    st.error(f"CSV missing columns. Required: {required}")
                else:
                    count = 0
                    existing_names = {c.name.lower() for c in categories}

                    for index, row in import_df.iterrows():
                        c_name = str(row["name"]).strip()
                        c_group = str(row["group"]).strip()
                        c_type = str(row["type"]).strip()

                        # Only add if name is valid and doesn't exist
                        if c_name and c_name.lower() not in existing_names:
                            session.add(
                                Category(name=c_name, group=c_group, type=c_type)
                            )
                            existing_names.add(c_name.lower())
                            count += 1

                    session.commit()
                    if count > 0:
                        st.success(f"Successfully imported {count} new categories!")
                        st.rerun()
                    else:
                        st.info("No new categories found (all names already exist).")
            except Exception as e:
                st.error(f"Error importing file: {e}")


# --- TAB 2: REGEX RULES ---
with tab2:
    st.subheader("Regex Automation")
    st.info(
        """
    💡 **Power User Mode:** Rules now use Regular Expressions.
    - **Exact Match:** `^Amazon$` (Matches "Amazon" but NOT "Amazon Mktplace")
    - **Start With:** `^Uber` (Matches "Uber Eats", "Uber Trip")
    - **Contains (Standard):** `Netflix` (Matches "Netflix.com", "Paypal *Netflix")
    - **Case Insensitive:** Logic is case-insensitive by default.
    """
    )

    rules = session.exec(select(CategoryRule)).all()
    rule_data = [r.model_dump() for r in rules]
    df_rules = pd.DataFrame(rule_data)

    cat_map = {c.name: c.id for c in categories}
    cat_names = list(cat_map.keys())

    if df_rules.empty:
        df_rules = pd.DataFrame(columns=["keyword", "category_id"])

    id_to_name = {v: k for k, v in cat_map.items()}
    if "category_id" in df_rules.columns and not df_rules.empty:
        df_rules["category_name"] = df_rules["category_id"].map(id_to_name)
    else:
        df_rules["category_name"] = None

    edited_rules = st.data_editor(
        df_rules,
        num_rows="dynamic",
        column_config={
            "id": None,
            "category_id": None,
            "keyword": st.column_config.TextColumn("Regex Pattern", required=True),
            "category_name": st.column_config.SelectboxColumn(
                "Assign To", options=cat_names, required=True
            ),
        },
        use_container_width=True,
        key="rule_editor",
    )

    col_a, col_b = st.columns(2)

    with col_a:
        if st.button("Save Rules"):
            for r in rules:
                session.delete(r)

            for i, row in edited_rules.iterrows():
                cat_val = clean_val(row.get("category_name"))
                keyword = clean_val(row.get("keyword"))

                if keyword and cat_val and cat_val in cat_map:
                    # Validate Regex before saving
                    try:
                        re.compile(keyword)
                        session.add(
                            CategoryRule(keyword=keyword, category_id=cat_map[cat_val])
                        )
                    except re.error:
                        st.error(f"❌ Invalid Regex skipped: {keyword}")

            session.commit()
            st.success("Rules Saved!")
            st.rerun()

    with col_b:
        if st.button("⚡ Apply Rules to Existing Transactions"):
            all_rules = session.exec(select(CategoryRule)).all()
            all_tx = session.exec(select(Transaction)).all()
            count = 0

            for tx in all_tx:
                for rule in all_rules:
                    if rule.keyword:
                        try:
                            # REGEX MATCHING
                            if re.search(rule.keyword, tx.description, re.IGNORECASE):
                                if tx.category_id != rule.category_id:
                                    tx.category_id = rule.category_id
                                    session.add(tx)
                                    count += 1
                                break
                        except re.error:
                            pass  # Skip bad rules
            session.commit()
            st.success(f"Scanned history: Updated {count} transactions!")

    st.divider()
    with st.expander("📥 Import Rules from CSV"):
        rule_file = st.file_uploader(
            "Upload rules.csv (Headers: keyword, category_name)", type=["csv"]
        )
        if rule_file and st.button("Load from CSV"):
            try:
                import_df = pd.read_csv(rule_file)
                added = 0
                for idx, r_row in import_df.iterrows():
                    kw = str(r_row["keyword"]).strip()
                    c_name = str(r_row["category_name"]).strip()

                    if c_name in cat_map:
                        exists = False
                        for r in rules:
                            if r.keyword == kw:
                                exists = True
                        if not exists:
                            session.add(
                                CategoryRule(keyword=kw, category_id=cat_map[c_name])
                            )
                            added += 1
                session.commit()
                st.success(f"Imported {added} rules!")
                st.rerun()
            except Exception as e:
                st.error(f"Import failed: {e}")
