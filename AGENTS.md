# Finance OS - Agent Development Guide

> **WARNING**: This app was mostly built by LLM. The codebase may contain inconsistencies or unconventional patterns.

## Project Overview

**Finance OS** is an offline-first personal finance Progressive Web App (PWA) that runs entirely in the browser. It is built with Python using Streamlit and deployed via [Stlite](https://github.com/whitphx/stlite) - a tool that runs Python directly in the browser using WebAssembly.

### Key Characteristics

- **Privacy-First**: All data (`finance.db`) lives only on the user's device. No cloud uploads.
- **Serverless Architecture**: Python code executes client-side via Pyodide/WebAssembly.
- **PWA Capabilities**: Can be installed on mobile devices (Android/iOS) like a native app.
- **Data Persistence**: Uses IndexedDB via Stlite's `idbfsMountpoints` to persist the SQLite database.

## Technology Stack

| Component | Technology |
|-----------|------------|
| Frontend Framework | Streamlit (Python) |
| Browser Runtime | Stlite (@stlite/browser@0.85.1) |
| Database | SQLite (via SQLModel) |
| Data Processing | Pandas |
| Visualization | Plotly, Altair |
| File Parsing | openpyxl, xlrd (Excel), pandas (CSV) |
| PWA | Service Worker, Web Manifest |

### Dependencies (requirements.txt)

```
streamlit>=1.30.0
pandas>=2.0.0
plotly>=5.18.0
sqlmodel>=0.0.14
openpyxl>=3.1.0
xlrd>=2.0.1
```

## Project Structure

```
.
├── Home.py                     # Main entry point, dashboard with KPIs
├── index.html                  # PWA entry, Stlite configuration
├── manifest.json               # PWA manifest
├── sw.js                       # Service Worker for offline caching
├── requirements.txt            # Python dependencies
├── data/                       # SQLite database (gitignored)
│   └── finance.db
├── src/                        # Core business logic
│   ├── __init__.py
│   ├── models.py               # SQLModel database models
│   ├── database.py             # DB engine, session management, init
│   └── analytics.py            # Plotly/Altair chart generation
└── pages/                      # Streamlit multi-page app pages
    ├── 1_Import_Data.py        # CSV/Excel bank statement import
    ├── 2_Budget_Planner.py     # Monthly budget targets
    ├── 3_Transaction_Manager.py # View, edit, delete transactions
    ├── 4_Manage_Categories.py  # Category & regex rule management
    ├── 5_Manage_Banks.py       # Account management
    ├── 6_Reconciliation_Advisor.py # Inter-account debt tracking
    ├── 7_Funds_&_Balances.py   # Virtual funds & balance tracking
    ├── 8_Notes.py              # Persistent notes
    └── 9_Settings.py           # Backup, merge, restore data
```

## Database Models

All models use SQLModel and are defined in `src/models.py`:

### Account
```python
- id: int (PK)
- name: str (unique)
- initial_balance: float
- import_config: str (JSON, per-account import settings)
```

### Category
```python
- id: int (PK)
- name: str (unique)
- group: str (Needs, Wants, Savings, Income, Transfers, Discretionary)
- type: str (Expense, Income)
- default_account_id: int (FK, optional - for reconciliation)
```

### CategoryRule
```python
- id: int (PK)
- keyword: str (regex pattern)
- category_id: int (FK)
```

### Budget
```python
- id: int (PK)
- category_id: int (FK)
- amount: float (monthly target)
```

### Transaction
```python
- id: int (PK)
- date: str (YYYY-MM-DD format)
- description: str
- amount: float (negative for expense, positive for income)
- category_id: int (FK, optional)
- account_id: int (FK, optional)
- unique_hash: str (MD5 hash for deduplication)
- is_virtual: bool (True for reserved funds, doesn't affect bank balance)
- is_settled: bool (True for reconciled transactions)
```

### Note
```python
- id: int (PK)
- content: str
- updated_at: str (ISO timestamp)
```

## Running the Application

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run locally
streamlit run Home.py
```

### Web Deployment (Production)

The app is deployed as static files:
1. Serve `index.html`, `manifest.json`, `sw.js`, and all `.py` files via any static web server
2. Stlite loads Python and runs it in the browser
3. Database is persisted to IndexedDB

## Key Code Patterns

### Database Session Management

Always use the `get_session()` context manager:

```python
from src.database import get_session
from src.models import Transaction
from sqlmodel import select

with get_session() as session:
    results = session.exec(select(Transaction)).all()
```

### Streamlit Page Configuration

Every page must set page config at the top:

```python
import streamlit as st

st.set_page_config(page_title="Page Name", layout="wide")
```

### Hash Generation for Deduplication

Transactions use MD5 hashes for deduplication:

```python
import hashlib

def generate_hash(date, desc, amount):
    raw = f"{date}{desc}{amount}"
    return hashlib.md5(raw.encode()).hexdigest()
```

### Virtual vs Real Transactions

- **Real Transactions**: `is_virtual=False` - Actual bank transactions affecting account balance
- **Virtual Transactions**: `is_virtual=True` - Reserved funds, counted in spending but not in bank balance

## Development Conventions

### Code Style

- No strict linter configuration present
- Use descriptive variable names
- Follow existing patterns in similar files
- Comment sections with `# --- SECTION NAME ---` format

### UI Conventions

- Use emojis in page titles and section headers
- Use `st.expander()` for secondary features
- Use `st.divider()` to separate sections
- Use `st.info()`, `st.warning()`, `st.success()` for user feedback
- Primary action buttons use `type="primary"`

### Numbered Page Files

Pages use numbered prefixes for sidebar ordering:
- `1_Import_Data.py`
- `2_Budget_Planner.py`
- etc.

### Error Handling

- Use try/except blocks for file parsing and data import
- Silent failures are common pattern (e.g., `except: pass`)
- User-facing errors use `st.error()`

## Testing

No formal test suite is present. Testing is manual:

1. Run the app locally with `streamlit run Home.py`
2. Test import functionality with sample CSV files
3. Verify charts render correctly
4. Test PWA functionality in browser DevTools

## Data Import Format

The app supports CSV and Excel bank statements with configurable column mapping:

- **Date Column**: Auto-detected, supports multiple formats (DD/MM/YYYY, MM/DD/YYYY, ISO)
- **Description Column(s)**: Can combine multiple columns
- **Amount Format**: Single column (signed) or separate Debit/Credit columns

Import configurations are saved per-account in `Account.import_config` as JSON.

## Security Considerations

1. **No Server-Side Code**: Everything runs client-side; there is no backend to secure.
2. **Data Privacy**: User data never leaves their device (unless they manually download a backup).
3. **No Authentication**: The app has no user authentication mechanism.
4. **Regex Injection**: Category rules use regex; invalid patterns are caught and skipped.

## Common Tasks

### Adding a New Page

1. Create file in `pages/` with numbered prefix (e.g., `10_New_Feature.py`)
2. Add page to `index.html` in the `files` section
3. Add page to `sw.js` in `ASSETS_TO_CACHE`
4. Follow existing page structure with `st.set_page_config()` at top

### Modifying Database Schema

1. Update model in `src/models.py`
2. SQLModel's `extend_existing=True` allows table redefinition
3. For breaking changes, users need to migrate their local database

### Adding a New Chart

1. Add chart function to `src/analytics.py`
2. Import and use in relevant page
3. Use Plotly for interactive charts, Altair for simpler visualizations

## Important Notes

- **Data Loss Risk**: If user clears browser cache, all data is lost. Emphasize backup.
- **Stlite Limitations**: Some Python packages may not work in Pyodide/WebAssembly environment.
- **Service Worker**: The `sw.js` caches assets for offline use. Increment `CACHE_NAME` version when deploying updates.
- **Missing Comma Bug**: Line 16 in `sw.js` is missing a comma after the string - this is a known issue in the codebase.
