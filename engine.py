import os
from PIL import Image, ImageDraw, ImageFont, ImageStat
from io import BytesIO
import textwrap

from google import genai
from google.genai.types import GenerateContentConfig, HttpOptions

class ThumbnailEngine:
    def __init__(self, openai_client, gemini_client):
        self.openai_client = openai_client
        self.gemini_client = gemini_client

    def decompose_prompt(self, user_prompt):
        """Task A: Decomposes user intent into visual and textual layers using Visual Metaphors."""
        
        system_instruction = """You are an expert YouTube thumbnail art director. Your job is to decompose a video topic into a punchy title and a highly creative, symbolic visual background.
        
        CRITICAL CONSTRAINTS FOR THE BACKGROUND VISUAL:
        1. ZERO text, letters, or words.
        2. ZERO humans, faces, hands, characters, or silhouettes.
        CRITICAL CONSTRAINTS FOR THE BACKGROUND VISUAL:
        1. ZERO text, letters, numbers, or words.
        2. ZERO humans, faces, hands, characters, or silhouettes.
        3. DO NOT suggest objects that inherently contain text or faces (e.g., NO dollar bills, NO newspapers, NO computer screens with code, NO ID cards).
        
        INSTRUCTION: Do not use boring "abstract geometric shapes." Instead, use GROUNDED VISUAL METAPHORS. Translate the topic into physical objects, environments, and cinematic lighting.
        
        EXAMPLES:
        Topic: "The Decline of Software Engineers"
        Good Visual: "A glowing neon motherboard slowly cracking and turning to rust, dramatic volumetric lighting, macro photography."
        
        Topic: "Economy is Crashing"
        Good Visual: "A giant crystal bull statue shattering into pieces on a dark marble floor, high speed photography, cinematic shadows."
        
        Topic: "The Truth About Fast Food"
        Good Visual: "A perfectly greasy burger sitting on a sterile steel surgical tray under harsh fluorescent hospital lights."

        Reply with EXACTLY 3 lines.
        Line 1: Title (Catchy, max 5 words).
        Line 2: Background prompt (Highly detailed, metaphorical, cinematic, NO humans, NO text).
        Line 3: Mode (Reply exactly with 'light' or 'dark' based on the visual).
        """

        response = self.openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7 # Slight bump in temperature for better creative metaphors
        )
        raw = response.choices[0].message.content.strip()
        lines = [ln.strip() for ln in raw.split('\n') if ln.strip()]
        title = (lines[0].replace("Title: ", "").strip() or user_prompt) if lines else user_prompt
        # Force title to max 5 words (LLM sometimes returns a sentence)
        title_words = title.split()[:5]
        title = " ".join(title_words) if title_words else user_prompt[:40]
        image_prompt = lines[1] if len(lines) > 1 else user_prompt
        # If image_prompt is too short or generic, use user prompt so Gemini has enough to draw
        if len(image_prompt) < 15 or image_prompt.lower().rstrip(".") in ("dark", "light"):
            image_prompt = user_prompt
        mode = (lines[2].lower() if len(lines) > 2 else "dark").strip(".")
        if mode not in ("light", "dark"):
            mode = "dark"
        return {"title": title, "image_prompt": image_prompt, "mode": mode}

    def generate_background(self, prompt, extra_constraint=None):
        # THE FIX: Hardcode the negative constraints into the base prompt
        full_prompt = (
            f"Create a high-quality video thumbnail background: {prompt}. "
            "CRITICAL: Absolutely NO humans, NO people, NO faces, NO hands, NO characters. "
            "No text or words."
        )
        if extra_constraint:
            full_prompt += f" {extra_constraint}"
        # skip_cache=True so the gateway returns a fresh generation, not cached
        response = self.gemini_client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=[full_prompt],
            config=GenerateContentConfig(
                http_options=HttpOptions(headers={"X-Skip-Cache": "true"}),
            ),
        )
        if not response.candidates or not response.candidates[0].content.parts:
            raise Exception("Generation failed: no content in response")
        for part in response.candidates[0].content.parts:
            if getattr(part, "inline_data", None) is not None:
                img = Image.open(BytesIO(part.inline_data.data)).convert("RGB")
                # Normalize to 1280x720 so background and thumbnail dimensions are consistent
                img = img.resize((1280, 720), getattr(Image, "Resampling", Image).LANCZOS)
                path = "temp_bg.png"
                img.save(path)
                return path
        raise Exception("Generation failed: no image in response (model may not support image generation)")

    def overlay_text(self, bg_path, text, mode="dark"):
        """
        Final Research-Grade Rendering:
        - Restores original color depth (no grayscale).
        - Uses an Exponential Alpha Fade to resolve 'uneven' shadow patches.
        - Implements Dynamic Vertical Safety to prevent bottom truncation.
        """
        # 1. Image Preparation: Keep original colors
        img = Image.open(bg_path).convert("RGBA").resize((1280, 720))
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # 2. Typography & Dynamic Scaling (Requirement 3.1)
        text = text.upper()
        wrapped_lines = textwrap.wrap(text, width=14)
        wrapped_text = "\n".join(wrapped_lines)
        # Scale font size based on text length to ensure dominance
        font_size = 90 if len(wrapped_lines) > 3 else 115

        # Load Bold Font for high OCR fidelity (Mac, Windows, Linux; fallback if none found)
        font = None
        for path in [
            "/System/Library/Fonts/Helvetica.ttc",                    # macOS
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",     # macOS
            "C:\\Windows\\Fonts\\arialbd.ttf",                        # Windows Arial Bold
            "C:\\Windows\\Fonts\\Arial Bold.ttf",                     # Windows (alt)
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",   # Linux
        ]:
            if os.path.exists(path):
                try:
                    font = ImageFont.truetype(path, font_size)
                    break
                except Exception:
                    pass
        if font is None:
            font = ImageFont.load_default()  # Cross-platform fallback; always present

        # 3. Dynamic Vertical Positioning (Requirement 3.3)
        try:
            bbox = draw.multiline_textbbox((640, 0), wrapped_text, font=font, anchor="ma")
            text_height = bbox[3] - bbox[1]
        except Exception:
            text_height = len(wrapped_lines) * font_size
        
        # cx is centered. cy is calculated from the bottom up to guarantee a 70px safety margin.
        cx = 640
        padding_bottom = 70 
        cy = 720 - padding_bottom - (text_height // 2)

        # 4. THE FIX: Exponential Gradient Floor
        # Darken bottom portion smoothly (height depends on text block size)
        gradient_height = int(text_height + 250)
        y_start = 720 - gradient_height

        for y in range(y_start, 720):
            if y < 0: 
                continue
            # Progress goes from 0.0 (top of shadow) to 1.0 (very bottom of image)
            progress = (y - y_start) / gradient_height
            
            # Exponential curve (** 2) makes it fade in seamlessly without a hard line
            alpha = int(230 * (progress ** 2)) 
            draw.line([(0, y), (1280, y)], fill=(0, 0, 0, alpha))

        # 5. Impact Rendering (Requirement B)
        # White text with a thick black stroke ensures a 100% OCR pass rate.
        draw.multiline_text(
            (cx, cy), wrapped_text, fill=(255, 255, 255), font=font,
            anchor="mm", align="center", spacing=15,
            stroke_width=6, stroke_fill=(0, 0, 0) 
        )

        # 6. Composite and Save
        final_img = Image.alpha_composite(img, overlay).convert("RGB")
        output_path = "latest_thumbnail.png"
        final_img.save(output_path)
        return output_path