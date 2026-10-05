# Pastor Niyi Adetiloye — Sermon Study Assistant

An intelligent, scripture-grounded conversational assistant built on the teachings, sermons, and ministry philosophy of **Pastor Niyi Adetiloye** (*The Designate Church - TDCI*).

---

## Key Features & Design

1. **Faithful Pastoral Representation (~90% Pastor Niyi)**
   - Indexed across **760 sermons** and **67,697 transcript chunks**.
   - Dynamically excludes 101 guest minister sermons (e.g. Pastor Raphael Onilenla, Busayo Oluwadunsin, Jide Olawoyin, Henry Edebatu) at query time via `exclude_titles.json`.
   - Retains 673 confirmed Pastor Niyi messages + 99 ministry series.

2. **10-Point Pastoral Guidance & Response Architecture**
   - **Concise Direct Answers**: 1–3 clear paragraphs initially.
   - **Progressive Depth**: Offers deeper scriptural layers (*"For further understanding...", "Let's examine what Scripture teaches..."*).
   - **Scripture-Centered & Practical**: Contextualized to everyday life, leadership, and personal spiritual growth.
   - **Structured Discipleship Answers**: Formatted with *Key Truth*, *Biblical Foundation*, *Explanation*, *Practical Application*, and optional *Prayer Point*.
   - **Inline Sermon Citations**: Direct source attribution `[x] Sermon: "Title" (timestamp)`.

3. **Self-Contained Vector Database**
   - ChromaDB embeddings indexed with `all-MiniLM-L6-v2`.
   - Packaged in `db_chunks/` (under GitHub's 50MB file size threshold) and automatically assembled on first launch.

---

## Local Setup & Running

### 1. Requirements
Ensure Python 3.10+ is installed:
```bash
pip install -r requirements.txt
```

### 2. Configure API Key
Create or edit `.streamlit/secrets.toml`:
```toml
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
```
*(Or enter your key directly into the secure sidebar input on the web interface).*

### 3. Launch the Application
```bash
streamlit run app.py
```

---

## Deploying 24/7 to Streamlit Community Cloud (Free)

1. **Push to GitHub**:
   ```bash
   git add .
   git commit -m "Initial release of Pastor Niyi Sermon Study Assistant"
   git remote add origin https://github.com/<YOUR_USERNAME>/pastor-niyi-ai.git
   git branch -M main
   git push -u origin main
   ```

2. **Deploy on Streamlit**:
   - Go to [share.streamlit.io](https://share.streamlit.io).
   - Click **New app**, select your repository, set Main file path to `app.py`.
   - Under **Advanced Settings** -> **Secrets**, add:
     ```toml
     GEMINI_API_KEY = "your_actual_gemini_key_here"
     ```
   - Click **Deploy**!
