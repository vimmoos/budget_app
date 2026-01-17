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
**Logic:** This will smartly import **Accounts, Balances, Categories, Rules, Transactions, Budgets, and Notes**.
*Existing data will be updated to match the file.*
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
                    # Always update balance to match source file
                    target_acct = acct_map_name_obj[name]
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
                    # Update existing category link
                    cat = existing_cat_map[name]
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
            # E. MERGE BUDGETS (FIXED: Upsert Logic)
            # ==========================================
            st.write("Syncing Budgets...")

            # Fetch existing budgets: {category_id: BudgetObject}
            existing_budgets = session.exec(select(Budget)).all()
            budget_map = {b.category_id: b for b in existing_budgets}

            try:
                cur_new.execute("SELECT * FROM budget")
                rows_bd = cur_new.fetchall()

                for r in rows_bd:
                    r_dict = dict(r)
                    cat_name = upload_cat_id_to_name.get(r_dict["category_id"])
                    new_cat_id = cat_name_to_new_id.get(cat_name)

                    if new_cat_id:
                        new_amount = r_dict["amount"]

                        if new_cat_id in budget_map:
                            # Update existing budget if different
                            existing_b = budget_map[new_cat_id]
                            if existing_b.amount != new_amount:
                                existing_b.amount = new_amount
                                session.add(existing_b)
                                stats["bd"] += 1  # Count updates too
                        else:
                            # Create new budget
                            new_b = Budget(category_id=new_cat_id, amount=new_amount)
                            session.add(new_b)
                            # Add to map so we don't duplicate if file has dupes
                            budget_map[new_cat_id] = new_b
                            stats["bd"] += 1
            except sqlite3.OperationalError:
                pass

            # ==========================================
            # F. SYNC NOTES
            # ==========================================
            st.write("Syncing Notes...")
            try:
                cur_new.execute("SELECT * FROM note")
                rows_notes = cur_new.fetchall()
                if rows_notes:
                    local_note = session.exec(select(Note)).first()
                    if not local_note:
                        local_note = Note(content="")
                        session.add(local_note)

                    imported_content = rows_notes[0]["content"]

                    # Simple append if not present, to avoid data loss
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
            - 🏦 Accounts & Balances Updated
            - 📂 {stats['cat']} Categories Synced
            - 📊 {stats['bd']} Budgets Updated/Added
            - 💳 {stats['tx']} Transactions Added
            - 📝 {stats['note']} Notes Synced
            """
            )
            st.balloons()

        except Exception as e:
            st.error(f"Error during merge: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)

st.divider()

# --- SECTION 3: RESTORE (OVERWRITE) ---
st.header("3. Overwrite Database (Restore)")
st.error(
    "⚠️ **DANGER ZONE**: This will DELETE your current data and replace it with the uploaded file."
)

restore_db = st.file_uploader(
    "Upload finance.db to restore",
    type=["db", "sqlite"],
    key="restore_uploader",
    help="This is useful for restoring a backup.",
)

if restore_db:
    if st.button("🚨 Overwrite Current Database", type="primary"):
        try:
            # 1. Dispose engine to release file locks
            engine.dispose()

            # 2. Backup current DB just in case (renaming it)
            if os.path.exists(DB_PATH):
                shutil.copy(DB_PATH, f"{DB_PATH}.bak")

            # 3. Overwrite the file
            with open(DB_PATH, "wb") as f:
                f.write(restore_db.getbuffer())

            st.success("Database restored successfully! Reloading app...")
            st.rerun()

        except Exception as e:
            st.error(f"Failed to restore database: {e}")
