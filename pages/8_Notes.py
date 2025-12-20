import streamlit as st
from sqlmodel import select
from datetime import datetime
from src.database import get_session
from src.models import Note

st.set_page_config(page_title="Notes", page_icon="📝")

st.title("📝 Persistent Notes")


def load_note():
    with get_session() as session:
        note = session.exec(select(Note)).first()
        if not note:
            note = Note(content="")
            session.add(note)
            session.commit()
            session.refresh(note)
        return note


current_note = load_note()

# Text Area
new_content = st.text_area(
    "Your Scratchpad (Saved in Database)",
    value=current_note.content,
    height=400,
    help="These notes are stored inside finance.db and will be backed up.",
)

# Save on Change
if new_content != current_note.content:
    with get_session() as session:
        # Re-fetch to ensure we are updating the correct row
        db_note = session.exec(select(Note).where(Note.id == current_note.id)).one()
        db_note.content = new_content
        db_note.updated_at = datetime.now().isoformat()
        session.add(db_note)
        session.commit()
    st.toast("Notes saved to Database!", icon="💾")
