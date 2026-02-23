"""
Run thumbnail pipeline for one prompt, capture per-attempt images and logs.
Used by the Streamlit batch UI.
"""
import io
import os
import shutil
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

# Reuse app's client setup (import after dotenv)
from app import openai_client, gemini_client
from engine import ThumbnailEngine
from validator import ThumbnailValidator

RETRY_CONSTRAINTS = [
    None,
    "Focus on high-contrast negative space for text.",
    "Solid minimalist background, extreme high contrast.",
]
MAX_RETRIES = 3


def run_one_prompt(prompt: str, output_dir: str):
    """
    Run the full pipeline for one prompt. Copy each attempt's images to output_dir.
    Returns (final_success: bool, attempts: list of dicts).
    Each dict: attempt (1-based), bg_path, thumb_path, log_text, success, reasons.
    """
    os.makedirs(output_dir, exist_ok=True)
    engine = ThumbnailEngine(openai_client, gemini_client)
    validator = ThumbnailValidator()
    attempts_data = []

    for attempt in range(MAX_RETRIES):
        old_stdout = sys.stdout
        sys.stdout = buf = io.StringIO()
        reasons = []
        bg_path = None
        thumb_path = None
        success = False

        try:
            print(f"\n{'='*60}")
            print(f"ATTEMPT {attempt + 1}/{MAX_RETRIES}")
            print(f"{'='*60}")

            print("[Step 1] Decompose prompt (LLM)...")
            plan = engine.decompose_prompt(prompt)
            print(f"  -> title: {plan['title']!r}")
            print(f"  -> image_prompt: {plan['image_prompt']}")
            print(f"  -> mode: {plan['mode']}")

            extra = RETRY_CONSTRAINTS[attempt] if attempt < len(RETRY_CONSTRAINTS) else None
            print(f"[Step 2] Generate background (Gemini){' [constraint: ' + str(extra) + ']' if extra else ''}...")
            bg = engine.generate_background(plan["image_prompt"], extra_constraint=extra)
            print(f"  -> saved to: {bg}")

            print("[Step 3] Overlay text...")
            final_img = engine.overlay_text(bg, plan["title"], plan["mode"])
            print(f"  -> saved to: {final_img}")

            # Copy images for this attempt before they get overwritten
            n = attempt + 1
            bg_path = os.path.join(output_dir, f"attempt_{n}_bg.png")
            thumb_path = os.path.join(output_dir, f"attempt_{n}_thumb.png")
            shutil.copy("temp_bg.png", bg_path)
            shutil.copy(final_img, thumb_path)

            print("[Step 4] Verify text fidelity (OCR on center crop)...")
            is_text_ok = validator.verify_text_fidelity(final_img, plan["title"])
            print(f"  -> match: {is_text_ok}")

            print("[Step 5] Check Mobile readability...")
            is_mobile_readable = validator.verify_mobile_readability(final_img, plan["title"])
            print(f"  -> mobile readable: {is_mobile_readable}")

            print("[Step 6] Check contrast (RMS)...")
            rms, is_contrast_ok = validator.check_contrast(final_img)
            print(f"  -> RMS: {rms:.4f}, pass (> 0.15): {is_contrast_ok}")

            # Step 7: Visual integrity — LLM-only (VLM audit, no Laplacian)
            print("[Step 7] Check visual integrity (LLM audit)...")
            _, is_visual_clean = validator.check_visual_integrity(bg, gemini_client)
            print(f"  -> visual integrity: {is_visual_clean}")

            success = is_text_ok and is_mobile_readable and is_contrast_ok and is_visual_clean
            if success:
                print(f"\n*** SUCCESS (attempt {n}) ***\n")
            else:
                if not is_text_ok:
                    reasons.append("text_fidelity")
                if not is_mobile_readable:
                    reasons.append("mobile_readability")
                if not is_contrast_ok:
                    reasons.append("contrast")
                if not is_visual_clean:
                    reasons.append("visual_integrity")
                print(f"Attempt {n} failed: {', '.join(reasons)}. Retrying...")
        except Exception as e:
            print(f"ERROR: {e}")
            reasons.append(str(e))
        finally:
            log_text = buf.getvalue()
            sys.stdout = old_stdout

        attempts_data.append({
            "attempt": attempt + 1,
            "bg_path": bg_path,
            "thumb_path": thumb_path,
            "log": log_text,
            "success": success,
            "reasons": reasons.copy(),
        })
        if success:
            break

    return success, attempts_data
