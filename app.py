import streamlit as st
import psycopg2
from psycopg2 import Error
import requests
import logging
from contextlib import contextmanager

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configuration
GEMINI_API_KEY = "AIzaSyCfZzpfygluvpTyqGANIgdRpiilug9xur4"
API_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
DB_PARAMS = {
    "dbname": "pgql",
    "user": "pgql",
    "password": "postgres",
    "host": "3.110.135.2",
    "port": "5432",
    "connect_timeout": 10
}

# Database Functions
@contextmanager
def db_connection():
    """Context manager for safe database connections."""
    conn = None
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        yield conn
    except Error as e:
        logger.error(f"Database connection failed: {e}")
        st.error(f"Database connection failed: {e}")
        raise
    finally:
        if conn:
            conn.close()

def init_db():
    """Initialize PostgreSQL database and table."""
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS code_logs (
                        id SERIAL PRIMARY KEY,
                        original_code TEXT NOT NULL,
                        corrected_code TEXT NOT NULL,
                        analysis TEXT NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
                logger.info("Database initialized successfully.")
    except Exception as e:
        st.error(f"Failed to initialize database: {e}")

def save_to_db(original_code, corrected_code, analysis):
    """Save code analysis to PostgreSQL."""
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO code_logs (original_code, corrected_code, analysis) VALUES (%s, %s, %s)",
                    (original_code, corrected_code, analysis)
                )
                conn.commit()
                logger.info("Code analysis saved to database.")
    except Exception as e:
        st.error(f"Failed to save to database: {e}")

# Gemini API Function with Best Prompt
def call_gemini(code):
    """Call Gemini API for code analysis and correction."""
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    payload = {
        "contents": [{
            "parts": [{
                "text": f"""
                    You are an expert Python code analyst. Analyze the following Python code for bugs, syntax errors, and logical issues. 
                    Provide a corrected version of the code that is bug-free and functionally correct. Return the response in this exact format:
                    Corrected Code:
                    [your corrected code here]
                    Analysis:
                    [detailed explanation of bugs found and corrections made]
                    If no bugs are found, state that explicitly in the Analysis section.
                    Do not optimize for performance unless it fixes a bug. Preserve the original functionality unless it’s inherently broken.
                    Code:
                    {code}
                """
            }]
        }],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1500}  # Low temperature for precision
    }
    try:
        response = requests.post(API_ENDPOINT, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        if "candidates" not in data or not data["candidates"]:
            raise ValueError("No valid response from Gemini API.")
        result = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        if "Analysis:" not in result:
            raise ValueError("Invalid response format from Gemini API.")
        corrected_code, analysis = result.split("Analysis:", 1)
        corrected_code = corrected_code.replace("Corrected Code:", "").strip()
        analysis = analysis.strip()
        if not corrected_code or not analysis:
            raise ValueError("Empty corrected code or analysis.")
        # Validate corrected code syntax
        compile(corrected_code, "<string>", "exec")
        return corrected_code, analysis
    except (requests.RequestException, ValueError, SyntaxError) as e:
        logger.warning(f"Gemini API failed or returned invalid code: {e}")
        return code, f"Error: Failed to analyze code due to {e}. Original code returned."

# Main Analysis Function
def analyze_and_correct(code):
    """Analyze and correct the code using Gemini API."""
    if not code.strip():
        return "", "Error: No code provided."
    if len(code.splitlines()) > 1000:
        return code, "Error: Code exceeds 1000 lines."
    
    corrected_code, analysis = call_gemini(code)
    return corrected_code, analysis

# Streamlit Frontend
def main():
    st.set_page_config(page_title="CodeSynapse", layout="wide")
    st.title("CodeSynapse: AI Code Corrector")
    st.markdown("Analyze and correct Python code using Google's Gemini API. Supports up to 1000 lines.")

    # Initialize database
    init_db()

    # Input area
    code_input = st.text_area("Enter Python Code:", height=400, max_chars=100000, placeholder="Paste your code here...")
    col1, col2 = st.columns([2, 1])

    with col1:
        if st.button("Analyze & Correct", key="run"):
            if not code_input.strip():
                st.error("Please enter some code.")
            else:
                with st.spinner("Analyzing code with Gemini AI..."):
                    try:
                        corrected_code, analysis = analyze_and_correct(code_input)
                        st.session_state["result"] = (corrected_code, analysis)
                        save_to_db(code_input, corrected_code, analysis)
                        st.success("Analysis saved to database!")
                    except Exception as e:
                        st.error(f"Analysis failed: {e}")

    # Display results
    if "result" in st.session_state:
        corrected_code, analysis = st.session_state["result"]
        st.subheader("Corrected Code")
        st.code(corrected_code, language="python")
        st.subheader("Analysis")
        st.text(analysis)

    with col2:
        st.markdown("### About")
        st.write("CodeSynapse uses Google's Gemini API to analyze and correct Python code, ensuring bug-free functionality.")

if __name__ == "__main__":
    main()
