# test_existing_ocr.py
import easyocr
from pdf2image import convert_from_path
from paddleocr import PaddleOCR
import pytesseract

# Download a sample gazette PDF first
pdf_path = "बाल.pdf"
images = convert_from_path(pdf_path, first_page=1, last_page=10)

# Test 1: EasyOCR (GPU recommended)
reader_easy = easyocr.Reader(['ne', 'en'], gpu=True)
result_easy = reader_easy.readtext(images[0])

# Test 2: PaddleOCR
ocr_paddle = PaddleOCR(lang='ne')
result_paddle = ocr_paddle.ocr(images[0])

# Test 3: Tesseract with Nepali
result_tess = pytesseract.image_to_string(images[0], lang='nep+eng')

# Compare outputs
print("=== EASYOCR ===")
print(' '.join([text[1] for text in result_easy]))
print("\n=== PADDLEOCR ===")
print(result_paddle)
print("\n=== TESSERACT ===")
print(result_tess)