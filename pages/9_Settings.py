import streamlit as st
import sqlite3
import shutil
import os
import uuid
from datetime import datetime
from src.database import get_session, engine
from src.models import Transaction, Category, Budget, Account, CategoryRule, Note
from sqlmodel import select

st.set_page_config(page_title="Settings", page_icon="⚙️")

st.title("⚙️ Data Management")

DB_PATH = "data/finance.db"

# --- SECTION 1: BACKUP ---
st.header("1. Backup Data")
st.markdown("Download your database to share it with another device or keep a backup.")

if os.path.exists(DB_PATH):
    with open(DB_PATH, "rb") as f:
        st.download_button(
            label="📥 Download Database (finance.db)",
            data=f,
            file_name=f"finance_backup_{datetime.now().strftime('%Y%m%d')}.db",
            mime="application/x-sqlite3",
        )
else:
    st.warning("No database found to download.")

st.divider()

# --- SECTION 2: MERGE ---
st.header("2. Merge Database")
st.markdown(
    """
Upload a `finance.db` from another device.
**Logic:** Syncs Accounts, Categories (with linked Accounts), Rules, Transactions, Budgets, and **Notes**.
"""
)

uploaded_db = st.file_uploader("Upload finance.db to merge", type=["db", "sqlite"])

if uploaded_db:
    # Save uploaded file to a temporary path
    temp_path = "data/temp_merge.db"
    with open(temp_path, "wb") as f:
        f.write(uploaded_db.getbuffer())

    if st.button("🚀 Start Merge", type="primary"):
        try:
            session = get_session()

            # Connect to Uploaded DB
            con_new = sqlite3.connect(temp_path)
            con_new.row_factory = sqlite3.Row
            cur_new = con_new.cursor()

            stats = {"acc": 0, "cat": 0, "rules": 0, "tx": 0, "bd": 0, "note": 0}

            # ==========================================
            # A. SYNC ACCOUNTS
            # ==========================================
            st.write("Syncing Accounts...")
            existing_accts = session.exec(select(Account)).all()
            acct_map_name_obj = {a.name: a for a in existing_accts}

            cur_new.execute("SELECT * FROM account")
            rows_acct = cur_new.fetchall()

            # Map: Old ID -> Name (Crucial for linking Categories/Transactions)
            upload_acct_id_to_name = {}

            for r in rows_acct:
                r_dict = dict(r)
                name = r_dict["name"]
                upload_acct_id_to_name[r_dict["id"]] = name

                if name in acct_map_name_obj:
                    # Update balance if imported one has data
                    target_acct = acct_map_name_obj[name]
                    if (
                        target_acct.initial_balance == 0.0
                        and r_dict.get("initial_balance", 0.0) != 0.0
                    ):
                        target_acct.initial_balance = r_dict.get("initial_balance", 0.0)
                        session.add(target_acct)
                else:
                    new_acct = Account(
                        name=name,
                        initial_balance=r_dict.get("initial_balance", 0.0),
                        import_config=r_dict.get("import_config"),
                    )
                    session.add(new_acct)
                    stats["acc"] += 1

            session.commit()

            # Refresh Map: Name -> New ID
            all_accts = session.exec(select(Account)).all()
            acct_name_to_new_id = {a.name: a.id for a in all_accts}

            # ==========================================
            # B. SYNC CATEGORIES (AND LINKED ACCOUNTS)
            # ==========================================
            st.write("Syncing Categories...")
            existing_cats = session.exec(select(Category)).all()
            existing_cat_map = {c.name: c for c in existing_cats}

            cur_new.execute("SELECT * FROM category")
            rows_cat = cur_new.fetchall()

            # Map: Old ID -> Name
            upload_cat_id_to_name = {}

            for r in rows_cat:
                r_dict = dict(r)
                name = r_dict["name"]
                upload_cat_id_to_name[r_dict["id"]] = name

                # Resolve Account Link
                linked_acct_id = None
                if r_dict.get("default_account_id"):
                    old_acct_name = upload_acct_id_to_name.get(
                        r_dict["default_account_id"]
                    )
                    if old_acct_name:
                        linked_acct_id = acct_name_to_new_id.get(old_acct_name)

                if name in existing_cat_map:
                    # Update existing category link if missing locally but present in import
                    cat = existing_cat_map[name]
                    if not cat.default_account_id and linked_acct_id:
                        cat.default_account_id = linked_acct_id
                        session.add(cat)
                else:
                    new_c = Category(
                        name=name,
                        type=r_dict["type"],
                        group=r_dict["group"],
                        default_account_id=linked_acct_id,
                    )
                    session.add(new_c)
                    stats["cat"] += 1

            session.commit()

            # Refresh Map
            all_cats = session.exec(select(Category)).all()
            cat_name_to_new_id = {c.name: c.id for c in all_cats}

            # ==========================================
            # C. SYNC RULES
            # ==========================================
            try:
                cur_new.execute("SELECT * FROM categoryrule")
                rows_rules = cur_new.fetchall()
                existing_rules = session.exec(select(CategoryRule)).all()
                existing_rule_sigs = {
                    (rule.keyword, rule.category_id) for rule in existing_rules
                }

                for r in rows_rules:
                    r_dict = dict(r)
                    cat_name = upload_cat_id_to_name.get(r_dict["category_id"])
                    new_cat_id = cat_name_to_new_id.get(cat_name)

                    if new_cat_id:
                        sig = (r_dict["keyword"], new_cat_id)
                        if sig not in existing_rule_sigs:
                            session.add(
                                CategoryRule(
                                    keyword=r_dict["keyword"], category_id=new_cat_id
                                )
                            )
                            existing_rule_sigs.add(sig)
                            stats["rules"] += 1
            except:
                pass

            # ==========================================
            # D. SYNC TRANSACTIONS
            # ==========================================
            st.write("Merging Transactions...")
            existing_txs = session.exec(select(Transaction)).all()
            existing_sigs = {
                (t.date, t.amount, t.description, t.category_id) for t in existing_txs
            }
            existing_hashes = {t.unique_hash for t in existing_txs if t.unique_hash}

            cur_new.execute("SELECT * FROM 'transaction'")
            rows_tx = cur_new.fetchall()

            for r in rows_tx:
                r_dict = dict(r)
                cat_name = upload_cat_id_to_name.get(r_dict["category_id"])
                new_cat_id = cat_name_to_new_id.get(cat_name)

                # Resolve Account
                old_acct_name = upload_acct_id_to_name.get(r_dict.get("account_id"))
                new_acct_id = acct_name_to_new_id.get(old_acct_name, 1)

                if new_cat_id:
                    sig = (
                        r_dict["date"],
                        r_dict["amount"],
                        r_dict["description"],
                        new_cat_id,
                    )
                    u_hash = r_dict.get("unique_hash")

                    if sig not in existing_sigs and (
                        not u_hash or u_hash not in existing_hashes
                    ):
                        if not u_hash:
                            u_hash = uuid.uuid4().hex

                        new_t = Transaction(
                            date=r_dict["date"],
                            amount=r_dict["amount"],
                            category_id=new_cat_id,
                            description=r_dict["description"],
                            account_id=new_acct_id,
                            unique_hash=u_hash,
                            is_virtual=r_dict.get("is_virtual", False),
                            is_settled=r_dict.get("is_settled", False),
                        )
                        session.add(new_t)
                        existing_sigs.add(sig)
                        existing_hashes.add(u_hash)
                        stats["tx"] += 1

            # ==========================================
            # E. SYNC NOTES
            # ==========================================
            st.write("Syncing Notes...")
            try:
                cur_new.execute("SELECT * FROM note")
                rows_notes = cur_new.fetchall()
                if rows_notes:
                    # Get local note
                    local_note = session.exec(select(Note)).first()
                    if not local_note:
                        local_note = Note(content="")
                        session.add(local_note)

                    imported_content = rows_notes[0][
                        "content"
                    ]  # Assuming single note row for now

                    # If content is different, append it
                    if imported_content and imported_content not in local_note.content:
                        separator = "\n\n--- Imported Note ---\n"
                        local_note.content += separator + imported_content
                        session.add(local_note)
                        stats["note"] += 1
            except:
                pass

            # ==========================================
            # FINALIZE
            # ==========================================
            session.commit()
            con_new.close()
            os.remove(temp_path)

            st.success(
                f"""
            **Merge Complete!**
            - 🏦 Accounts & Links Updated
            - 📂 {stats['cat']} New Categories
            - 📝 {stats['note']} Notes Synced
            - 💳 {stats['tx']} New Transactions
            - 📏 {stats['rules']} New Rules
            """
            )
            st.balloons()

        except Exception as e:
            st.error(f"Error during merge: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
