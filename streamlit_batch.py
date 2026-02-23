"""
Streamlit UI for batch testing thumbnails.
Shows all attempts (images + logs) for each prompt; keeps previous attempts in session.
Run from thumbnail_solution: streamlit run streamlit_batch.py
"""
import html
import os
import re
from datetime import datetime

import streamlit as st

# Run from script dir so engine temp files (temp_bg.png, latest_thumbnail.png) and imports resolve
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.getcwd() != _SCRIPT_DIR:
    os.chdir(_SCRIPT_DIR)

from batch_run import run_one_prompt

BATCH_OUTPUT = "batch_output"

# --- Page config & custom theme ---
st.set_page_config(
    page_title="Batch Thumbnail Generator",
    page_icon="🖼️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS: light, warm palette — easy on the eyes
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700&display=swap');

    .stApp {
        background: linear-gradient(180deg, #faf8f5 0%, #f0ede8 100%);
    }
    .stApp .main .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1400px;
    }

    h1 {
        font-family: 'DM Sans', sans-serif !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em !important;
        color: #1c1917 !important;
        margin-bottom: 0.25rem !important;
    }
    .tagline {
        font-family: 'DM Sans', sans-serif;
        color: #57534e;
        font-size: 1rem;
        margin-bottom: 1.5rem;
    }

    [data-testid="stVerticalBlock"] > div:has(textarea) {
        background: #ffffff;
        border: 1px solid #e7e5e4;
        border-radius: 12px;
        padding: 1rem 1.25rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .stTextArea textarea {
        font-family: 'DM Sans', sans-serif !important;
        background: #fafaf9 !important;
        border-radius: 8px !important;
        border: 1px solid #e7e5e4 !important;
    }

    .stButton > button {
        font-family: 'DM Sans', sans-serif !important;
        font-weight: 600 !important;
        background: #0d9488 !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 0.6rem 1.5rem !important;
        transition: background 0.2s ease, box-shadow 0.2s ease !important;
    }
    .stButton > button:hover {
        background: #0f766e !important;
        box-shadow: 0 4px 12px rgba(13, 148, 136, 0.35) !important;
    }

    hr {
        border: none !important;
        height: 1px !important;
        background: #e7e5e4 !important;
        margin: 2rem 0 !important;
    }

    h2, h3 {
        font-family: 'DM Sans', sans-serif !important;
        color: #292524 !important;
        font-weight: 600 !important;
    }

    [data-testid="stExpander"] {
        background: #ffffff;
        border: 1px solid #e7e5e4;
        border-radius: 12px;
        margin-bottom: 0.75rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    [data-testid="stExpander"] summary {
        font-family: 'DM Sans', sans-serif !important;
        font-weight: 500 !important;
        color: #292524 !important;
    }

    .badge {
        display: inline-block;
        font-family: 'DM Sans', sans-serif;
        font-size: 0.75rem;
        font-weight: 600;
        padding: 0.25rem 0.6rem;
        border-radius: 9999px;
        letter-spacing: 0.02em;
    }
    .badge-success {
        background: #ccfbf1;
        color: #0f766e;
        border: 1px solid #5eead4;
    }
    .badge-fail {
        background: #ffedd5;
        color: #c2410c;
        border: 1px solid #fdba74;
    }
    .badge-run {
        background: #e0f2fe;
        color: #0369a1;
        border: 1px solid #7dd3fc;
    }

    .prompt-block {
        background: #fafaf9;
        border: 1px solid #e7e5e4;
        border-left: 4px solid #0d9488;
        border-radius: 0 8px 8px 0;
        padding: 0.75rem 1rem;
        margin: 0.75rem 0;
        font-family: 'DM Sans', sans-serif;
        color: #44403c;
    }
    .prompt-block strong { color: #1c1917; }

    figcaption, .image-caption {
        font-family: 'DM Sans', sans-serif !important;
        color: #57534e !important;
        font-size: 0.8rem !important;
    }

    .stCodeBlock {
        background: #f5f5f4 !important;
        border-radius: 8px !important;
        border: 1px solid #e7e5e4 !important;
    }
    .stCodeBlock code {
        font-size: 0.8rem !important;
        color: #44403c !important;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f5f5f4 0%, #e7e5e4 100%);
        border-right: 1px solid #d6d3d1;
    }
    [data-testid="stSidebar"] .stMarkdown { color: #44403c; }
    [data-testid="stSidebar"] .stCaption { color: #57534e; }
</style>
""", unsafe_allow_html=True)

# --- Header ---
st.markdown("# 🖼️ Thumbnail Batch Tester")
st.markdown('<p class="tagline">One prompt per line. Each run keeps all attempt images and logs in session.</p>', unsafe_allow_html=True)

# Session state: list of runs
if "runs" not in st.session_state:
    st.session_state.runs = []

# --- Sidebar: run summary ---
with st.sidebar:
    st.markdown("### Runs")
    if st.session_state.runs:
        for run in st.session_state.runs[:10]:
            success_count = sum(1 for p in run["prompts"] if p["success"])
            total = len(run["prompts"])
            st.caption(f"**{run['run_id']}** — {success_count}/{total} passed")
        st.markdown("---")
        if st.button("Clear all runs", use_container_width=True):
            st.session_state.runs = []
            st.rerun()
    else:
        st.caption("No runs yet.")

# --- Input section ---
with st.container():
    prompts_text = st.text_area(
        "Prompts (one per line)",
        height=120,
        placeholder="Russia vs Ukraine War and its impact on the world\nAI Wins\nEnd of the World",
        label_visibility="collapsed",
    )
    run_clicked = st.button("Run batch", type="primary", use_container_width=False)

if run_clicked and prompts_text.strip():
    prompts = [p.strip() for p in prompts_text.strip().split("\n") if p.strip()]
    if not prompts:
        st.warning("Enter at least one prompt.")
    else:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_dir = os.path.join(BATCH_OUTPUT, f"run_{run_id}")
        os.makedirs(base_dir, exist_ok=True)
        run_result = {"run_id": run_id, "prompts": []}

        progress = st.progress(0, text="Running...")
        for i, prompt in enumerate(prompts):
            progress.progress((i + 1) / len(prompts), text=f"Running: {prompt[:50]}...")
            slug = re.sub(r"[^\w\-]", "_", prompt)[:40]
            out_dir = os.path.join(base_dir, f"prompt_{i}_{slug}")
            success, attempts = run_one_prompt(prompt, out_dir)
            run_result["prompts"].append({
                "prompt": prompt,
                "success": success,
                "attempts": attempts,
            })
        progress.empty()
        st.session_state.runs.insert(0, run_result)
        st.rerun()

# --- Results section ---
st.markdown("---")
st.markdown("## Results")

if not st.session_state.runs:
    st.info("Run a batch to see results. Each attempt's background and thumbnail are saved and shown below.")
else:
    for run in st.session_state.runs:
        success_count = sum(1 for p in run["prompts"] if p["success"])
        total = len(run["prompts"])
        run_label = f"Run **{run['run_id']}** — {len(run['prompts'])} prompt(s), {success_count}/{total} passed"
        with st.expander(run_label, expanded=True):
            for pr in run["prompts"]:
                prompt_short = (pr["prompt"][:80] + ("..." if len(pr["prompt"]) > 80 else ""))
                prompt_escaped = html.escape(prompt_short)
                status_class = "badge-success" if pr["success"] else "badge-fail"
                status_text = "SUCCESS" if pr["success"] else "FAILED"
                st.markdown(
                    f'<div class="prompt-block">'
                    f'<span class="badge {status_class}">{status_text}</span> '
                    f'<strong>Prompt:</strong> {prompt_escaped}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                for att in pr["attempts"]:
                    att_status = "SUCCESS" if att["success"] else "FAILED"
                    att_badge = "badge-success" if att["success"] else "badge-fail"
                    reasons = ", ".join(att["reasons"]) if att["reasons"] else ""
                    label = f"Attempt {att['attempt']} — {att_status}" + (f" ({reasons})" if reasons else "")
                    with st.expander(label, expanded=not att["success"] or att["attempt"] == 1):
                        col1, col2, col3 = st.columns([1, 1, 1])
                        with col1:
                            if att.get("bg_path") and os.path.exists(att["bg_path"]):
                                st.image(att["bg_path"], caption="Background", use_container_width=True)
                            else:
                                st.caption("(no bg image)")
                        with col2:
                            if att.get("thumb_path") and os.path.exists(att["thumb_path"]):
                                st.image(att["thumb_path"], caption="Thumbnail", use_container_width=True)
                            else:
                                st.caption("(no thumb image)")
                        with col3:
                            st.caption("Log")
                            st.code(att.get("log", ""), language=None)
            st.divider()
