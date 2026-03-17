# 🏦 AI Financial Auditor (Web Edition)

Transform your boring bank statements into a brutal, AI-powered financial audit. Now featuring a full **Streamlit Web Interface**, multi-bank support, and interactive data visualizations.

## 🚀 Key Features
- **Modern Web UI**: Drag-and-drop your PDFs directly in your browser.
- **Smart Routing 2.0**: Automatic detection and extraction for **HSBC** and **Santander** statements.
- **Context-Aware AI**: The engine remembers your categories via `memory.json` to keep audits consistent across months.
- **Interactive Visuals**: View your spending through dynamic bar charts and expandable category breakdowns.
- **The Roast**: A brutally honest, sarcastic financial assessment powered by Gemini 2.5 Flash.

## 📂 Project Structure
- `app.py`: The Streamlit frontend (run this to start the app).
- `extractor.py`: The engine that parses PDFs (formerly `conv.py`).
- `analyzer.py`: The logic for AI categorization and roasting (formerly `banker.py`).
- `memory.json`: Local cache for shop-to-category mapping (auto-generated).

## 🛠️ Setup & Installation

1. **Clone the Repo**:
   ```bash
   git clone [https://github.com/Mkrm12/Banker.git](https://github.com/Mkrm12/Banker.git)
   cd Banker