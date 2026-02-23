from fastapi import FastAPI
from engine import ThumbnailEngine
from validator import ThumbnailValidator
import os
from PIL import Image
import openai
from openai import OpenAI
from google import genai
from google.genai.types import HttpOptions
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# --- API configuration from env (no hardcoded URLs or keys in code) ---
GATEWAY_BASE = os.getenv("GATEWAY_BASE", "").strip()
token = os.getenv("token", "").strip()
if not GATEWAY_BASE or not token:
    raise RuntimeError("Set GATEWAY_BASE and token in .env")

# Skip cache so each request gets a fresh response (gateway may respect X-Skip-Cache)
SKIP_CACHE_HEADERS = {"X-Skip-Cache": "true"}

openai.api_base = GATEWAY_BASE
openai.api_key = token
openai_client = OpenAI(base_url=GATEWAY_BASE, api_key=token, default_headers=SKIP_CACHE_HEADERS)
gemini_client = genai.Client(
    vertexai=True,
    api_key="dummy",
    http_options=HttpOptions(
        base_url=GATEWAY_BASE,
        headers={**SKIP_CACHE_HEADERS, "Authorization": f"Bearer {token}"},
    ),
)

@app.post("/generate")
async def generate(prompt: str):
    engine = ThumbnailEngine(openai_client, gemini_client)
    validator = ThumbnailValidator()

    # Challenge C: Failure Handling & Recovery — prompt injection on retry
    retry_strategies = [
        None, 
        "Abstract geometric shapes and tech patterns only. Strictly NO people or faces.", 
        "Minimalist solid color gradient. Completely abstract. Zero human subjects or silhouettes."
    ]
    max_retries = 3
    reasons = []
    for attempt in range(max_retries):
        reasons = []
        print(f"\n{'='*60}")
        print(f"ATTEMPT {attempt + 1}/{max_retries}")
        print(f"{'='*60}")

        print("[Step 1] Decompose prompt (LLM)...")
        plan = engine.decompose_prompt(prompt)
        print(f"  -> title: {plan['title']!r}")
        print(f"  -> image_prompt: {plan['image_prompt']}")
        print(f"  -> mode: {plan['mode']}")

        extra = retry_strategies[attempt] if attempt < len(retry_strategies) else None
        print(f"[Step 2] Generate background (Gemini){' [constraint: ' + extra + ']' if extra else ''}...")
        bg = engine.generate_background(plan["image_prompt"], extra_constraint=extra)
        print(f"  -> saved to: {bg}")

        print("[Step 3] Overlay text...")
        final_img = engine.overlay_text(bg, plan["title"], plan["mode"])
        print(f"  -> saved to: {final_img}")

        print("[Step 4] Verify text fidelity (OCR on center crop)...")
        is_text_ok = validator.verify_text_fidelity(final_img, plan["title"])
        print(f"  -> match: {is_text_ok}")

        # Mobile Legibility Check (Constraint 3.1) [cite: 31, 59]
        print("[Step 5] Check Mobile readability...")
        is_mobile_readable = validator.verify_mobile_readability(final_img, plan['title'])
        print(f"  -> mobile readable: {is_mobile_readable}")

        print("[Step 6] Check contrast (RMS)...")
        rms, is_contrast_ok = validator.check_contrast(final_img)
        print(f"  -> RMS: {rms:.4f}, pass (> 0.15): {is_contrast_ok}")

        # Step 7: Visual integrity — LLM-only (VLM-as-a-Judge, no Laplacian)
        print("[Step 7] Check visual integrity (LLM audit)...")
        _result, is_clean_geometry = validator.check_visual_integrity(bg, gemini_client)
        print(f"  -> visual integrity pass: {is_clean_geometry}")

        if is_text_ok and is_mobile_readable and is_contrast_ok and is_clean_geometry:
            print(f"\n*** SUCCESS (attempt {attempt + 1}) ***\n")
            return {"status": "success", "url": final_img, "attempts": attempt + 1}
        # Degraded-graceful recovery: retry with stricter constraints on failure.
        if not is_text_ok:
            reasons.append("text_fidelity (OCR did not detect expected title)")
        if not is_mobile_readable:
            reasons.append("mobile_readability (title not readable at 200px)")
        if not is_contrast_ok:
            reasons.append("contrast (image contrast below threshold)")
        if not is_clean_geometry:
            reasons.append("visual_integrity (LLM: faces/text/artifacts detected)")
        print(f"Attempt {attempt + 1} failed: {', '.join(reasons)}. Retrying...")

    # Structured output when all 3 attempts fail
    fallback_path = "outputs/fallback_solid_color.png"
    os.makedirs("outputs", exist_ok=True)
    if not os.path.exists(fallback_path):
        img = Image.new("RGB", (1280, 720), color=(45, 45, 55))
        img.save(fallback_path)
    return {
        "status": "failed",
        "error_type": "ConstraintViolation",
        "message": "Quality constraints not met after 3 attempts.",
        "failure_log": reasons,
        "fallback_image": fallback_path,
    }
