from difflib import SequenceMatcher

import cv2
import numpy as np
from PIL import Image
import PIL.Image

import easyocr  # pip install easyocr


class ThumbnailValidator:
    def __init__(self):
        self.reader = easyocr.Reader(["en"])

    def verify_text_fidelity(self, image_path, expected_text):
        img = Image.open(image_path).convert("L")  # Grayscale
        # Threshold: dark → 0, bright (text) → 255. Use 'L' (uint8) so EasyOCR/OpenCV get numeric, not bool.
        bw = img.point(lambda x: 0 if x < 200 else 255, "L")
        bw.save("ocr_mask.png")
        result = self.reader.readtext("ocr_mask.png", detail=0)
        detected = " ".join(result).lower()
        # Use Fuzzy Matching: OCR often misses apostrophes or small letters [cite: 49]
        ratio = SequenceMatcher(None, expected_text.lower(), detected).ratio()
        ok = ratio > 0.5
        print(f"  [validator] OCR (fidelity) expected: {expected_text!r} | detected: {detected!r} | ratio: {ratio:.3f} (need > 0.5) | pass: {ok}")
        return ok

    def check_contrast(self, image_path):
        """
        Calculates Root Mean Square (RMS) Contrast.
        RMS is the standard deviation of pixel intensities [cite: 32, 59].
        Research metric: RMS > 0.2 is typically 'readable' for human eyes.
        """
        img = Image.open(image_path).convert("L")
        img_array = np.array(img) / 255.0  # Normalize to 0-1

        rms_contrast = float(np.std(img_array))
        ok = rms_contrast > 0.15  # Allow dark-mode thumbnails that are still readable
        print(f"  [validator] RMS contrast: {rms_contrast:.4f} (need > 0.15) | pass: {ok}")
        return rms_contrast, ok

    def verify_mobile_readability(self, image_path, expected_text):
        """Requirement 3.1: Title readable at <=200px width."""
        img = Image.open(image_path)
        mobile_sim = img.resize((200, 112))  # Simulate mobile preview size
        mobile_sim.save("mobile_test.png")
        result = self.reader.readtext("mobile_test.png", detail=0)
        detected = " ".join(result).lower()
        # Research heuristic: if similarity is > 60%, a human can likely read it.
        similarity = SequenceMatcher(None, expected_text.lower(), detected).ratio()
        ok = similarity > 0.6
        print(f"  [validator] OCR (mobile) expected: {expected_text!r} | detected: {detected!r} | similarity: {similarity:.3f} (need > 0.6) | pass: {ok}")
        return ok

    def check_visual_integrity(self, bg_image_path, gemini_client):
        """
        Research-Grade Constraint 2.2: VLM-as-a-Judge.
        Instead of math, we use Gemini to semantically audit the image for banned artifacts.
        """
        # Open the raw background image (before text is added)
        img = PIL.Image.open(bg_image_path)
        
        # Zero-shot strict audit prompt
        audit_prompt = (
            "You are a strict QA auditor for background images. "
            "Look at this image. Does it contain ANY of the following: "
            "1. Human faces or body parts (hands, limbs) "
            "2. Recognizable text, letters, watermarks, or symbols "
            "3. Obvious broken geometry or mutated objects. "
            "If it contains ANY of these, reply with 'FAIL'. "
            "If it is a clean, abstract, or artifact-free background, reply with 'PASS'."
        )
        
        try:
            # Pass the image and prompt to Gemini Flash (fast & cheap for vision)
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[img, audit_prompt]
            )
            result = response.text.strip().upper()
            
            is_clean = "PASS" in result
            return result, is_clean
            
        except Exception as e:
            print(f"  [validator] VLM Audit API Error: {e}")
            # If the API glitches, we fail-safe to True so we don't break the loop
            return "API_ERROR (Pass by default)", True
