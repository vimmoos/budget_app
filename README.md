# 💰 Finance OS - Personal Finance PWA

An offline-first personal finance application that runs entirely in your browser.
Built with Python (Streamlit), deployed as a Progressive Web App (PWA).

## ✨ Features

- **Mobile PWA:** Installs on Android/iOS like a native app.
- **Privacy First:** Your data (`finance.db`) lives **only** on your device. No cloud uploads.
- **Multi-Account:** Manage Bank Accounts, Revolut, Cash, etc.
- **Budget Planning:** Set monthly budgets and track progress.
- **Auto-Categorization:** Smart keyword rules to sort your imports.
- **Reconciliation Advisor:** Finds "who owes whom" between your accounts.
- **Import/Export:** Full backup and sync capability across devices.

## 🚀 How to Run

### Option 1: The Easy Way (Web)
1. Go to the hosted URL (e.g., `https://falzari.dev/budget_app/`).
2. Wait 20 seconds for Python to load.
3. Tap **"Add to Home Screen"** on your phone to install.

### Option 2: Run Locally (PC)
If you want to develop or run it on your computer:


```bash

# 1. Clone the repo
git clone [https://github.com/vimmoos/budget_app.git](https://github.com/vimmoos/budget_app.git)
cd budget_app

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install requirements
pip install -r requirements.txt

# 4. Run the app
streamlit run Home.py
```

## 📂 Project Structure

* `Home.py`: Main dashboard.
* `pages/`: Individual features (Import, Budget, Transactions, etc.).
* `src/`: Core logic (Database models, Analytics, Helpers).
* `data/`: Where `finance.db` is stored (Ignored by Git for privacy).
* `index.html` & `sw.js`: The magic files that turn Python into a PWA.

## ⚠️ Important Note on Data

Because this is a serverless PWA, **if you clear your browser cache, you lose your data.**

* **Best Practice:** Go to **Settings -> Backup Data** regularly and save the `.db` file to your phone/computer.
* **Syncing:** To move data to a new phone, download the backup from the old phone and use **Settings -> Merge Database** on the new one.

---

*Built with [Stlite](https://github.com/whitphx/stlite).*

```
