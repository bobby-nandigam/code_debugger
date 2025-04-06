import streamlit as st
import psycopg2
from psycopg2 import Error
import requests
import time
import re
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
    "connect_timeout": 10  # Added timeout
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
                        optimized_code TEXT NOT NULL,
                        debug_info TEXT NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
                logger.info("Database initialized successfully.")
    except Exception as e:
        st.error(f"Failed to initialize database: {e}")

def save_to_db(original_code, optimized_code, debug_info):
    """Save code analysis to PostgreSQL."""
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO code_logs (original_code, optimized_code, debug_info) VALUES (%s, %s, %s)",
                    (original_code, optimized_code, debug_info)
                )
                conn.commit()
                logger.info("Code analysis saved to database.")
    except Exception as e:
        st.error(f"Failed to save to database: {e}")

# AI and Rule-Based Optimization Functions
def call_gemini(code):
    """Call Gemini API for code analysis."""
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    payload = {
        "contents": [{
            "parts": [{
                "text": f"""
                    Analyze this Python code for bugs and optimize it for space/time complexity. Return in this format:
                    Optimized Code:
                    [your optimized code here]
                    Debug Information:
                    [bugs found, optimizations applied, performance notes]
                    Code:
                    {code}
                """
            }]
        }],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1500}
    }
    try:
        response = requests.post(API_ENDPOINT, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        if "candidates" not in data or not data["candidates"]:
            raise ValueError("No valid response from Gemini API.")
        result = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        if "Debug Information:" not in result:
            raise ValueError("Invalid response format from Gemini API.")
        opt_code, debug_info = result.split("Debug Information:", 1)
        optimized_code = opt_code.replace("Optimized Code:", "").strip()
        if not optimized_code or not debug_info.strip():
            raise ValueError("Empty optimized code or debug info.")
        return optimized_code, debug_info.strip()
    except (requests.RequestException, ValueError) as e:
        logger.warning(f"Gemini API failed: {e}")
        return None, None

def rule_based_optimize(code):
    """Rule-based fallback optimization."""
    optimized_code = code.strip()
    debug_info = []

    # Optimization 1: Replace for loops with list comprehensions (improved pattern)
    loop_pattern = r"for\s+(\w+)\s+in\s+range\((\d+)\):\s*\n\s+(\w+)\.append\(([^)]+)\)"
    if re.search(loop_pattern, optimized_code, re.MULTILINE):
        optimized_code = re.sub(
            loop_pattern,
            lambda m: f"{m.group(3)} = [{m.group(4)} for {m.group(1)} in range({m.group(2)})]",
            optimized_code,
            flags=re.MULTILINE
        )
        debug_info.append("Replaced for loop with list comprehension for better time efficiency.")

    # Optimization 2: Remove redundant variables (improved logic)
    lines = optimized_code.split("\n")
    assignments = set()
    used_vars = set()
    for line in lines:
        assign_match = re.match(r"^\s*(\w+)\s*=\s*.+$", line.strip())
        if assign_match:
            assignments.add(assign_match.group(1))
        used_matches = re.findall(r"\b(\w+)\b", line)
        used_vars.update(used_matches)
    redundant = assignments - used_vars - {"print"}
    if redundant:
        optimized_code = "\n".join(line for line in lines if not any(re.match(rf"^\s*{r}\s*=\s*.+$", line.strip()) for r in redundant))
        debug_info.append(f"Removed redundant variables: {', '.join(redundant)}.")

    # Execution time and safety check
    start = time.time()
    try:
        # Validate syntax before execution
        compile(optimized_code, "<string>", "exec")
        exec(optimized_code, {"__builtins__": {}})  # Restricted environment
        exec_time = time.time() - start
        debug_info.append(f"Execution Time: {exec_time:.6f}s")
    except SyntaxError as e:
        debug_info.append(f"Syntax Error: {e}")
    except Exception as e:
        debug_info.append(f"Runtime Error: {e}")

    return optimized_code, "\n".join(debug_info) if debug_info else "No optimizations applied."

def optimize_and_debug(code):
    """Main function to optimize and debug code."""
    if not code.strip():
        return "", "Error: No code provided."
    if len(code.splitlines()) > 1000:
        return code, "Error: Code exceeds 1000 lines."

    # Try Gemini API first
    opt_code, debug_info = call_gemini(code)
    if opt_code and debug_info:
        return opt_code, debug_info

    # Fallback to rule-based
    logger.info("Falling back to rule-based optimization.")
    return rule_based_optimize(code)

# Streamlit Frontend
def main():
    st.set_page_config(page_title="CodeSynapse", layout="wide")
    st.title("CodeSynapse: AI Code Debugger & Enhancer")
    st.markdown("Optimize and debug Python code with AI-powered analysis using Gemini API. Supports up to 1000 lines.")

    # Initialize database
    init_db()

    # Input area
    code_input = st.text_area("Enter Python Code:", height=400, max_chars=100000, placeholder="Paste your code here...")
    col1, col2 = st.columns([2, 1])

    with col1:
        if st.button("Optimize & Debug", key="run"):
            if not code_input.strip():
                st.error("Please enter some code.")
            else:
                with st.spinner("Analyzing code with Gemini AI..."):
                    try:
                        optimized_code, debug_info = optimize_and_debug(code_input)
                        st.session_state["result"] = (optimized_code, debug_info)
                        save_to_db(code_input, optimized_code, debug_info)
                        st.success("Analysis saved to database!")
                    except Exception as e:
                        st.error(f"Analysis failed: {e}")

    # Display results
    if "result" in st.session_state:
        opt_code, debug = st.session_state["result"]
        st.subheader("Enhanced Code")
        st.code(opt_code, language="python")
        st.subheader("Debug Information")
        st.text(debug)

    with col2:
        st.markdown("### About")
        st.write("CodeSynapse leverages Google's Gemini API for intelligent code enhancement, with a rule-based fallback for reliability.")

if __name__ == "__main__":
    main()
