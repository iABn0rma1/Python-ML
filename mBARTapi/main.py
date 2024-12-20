from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from transformers import MBartForConditionalGeneration, MBart50TokenizerFast, T5Tokenizer, T5ForConditionalGeneration
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Initialize FastAPI app
app = FastAPI()

# Serve static files and set up templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Load MBart model and tokenizer (for non-English corrections)
mbart_model_name = "facebook/mbart-large-50-many-to-many-mmt"
mbart_tokenizer = MBart50TokenizerFast.from_pretrained(mbart_model_name)
mbart_model = MBartForConditionalGeneration.from_pretrained(mbart_model_name)

# Load T5 model and tokenizer (for English corrections)
t5_model_name = "vennify/t5-base-grammar-correction"
t5_tokenizer = T5Tokenizer.from_pretrained(t5_model_name)
t5_model = T5ForConditionalGeneration.from_pretrained(t5_model_name)

# Function to correct grammar for English using T5
def correct_grammar_english(text):
    input_text = "grammar: " + text
    inputs = t5_tokenizer(input_text, return_tensors="pt", max_length=512, truncation=True)
    outputs = t5_model.generate(inputs['input_ids'], max_length=512, num_beams=5, early_stopping=True)
    corrected_text = t5_tokenizer.decode(outputs[0], skip_special_tokens=True)
    return corrected_text

# Function to correct grammar for non-English using MBart
def correct_grammar_mbart(text, src_lang):
    mbart_tokenizer.src_lang = src_lang
    encoded_input = mbart_tokenizer(text, return_tensors="pt", padding=True, truncation=True)
    generated_tokens = mbart_model.generate(
        **encoded_input,
        max_length=512,
        num_beams=5,
        early_stopping=True,
        forced_bos_token_id=mbart_tokenizer.lang_code_to_id[src_lang]
    )
    corrected_text = mbart_tokenizer.decode(generated_tokens[0], skip_special_tokens=True)
    return corrected_text

# Helper function to highlight errors
def highlight_errors(original, corrected):
    original_tokens = original.split()
    corrected_tokens = corrected.split()
    highlighted = []
    for o_token, c_token in zip(original_tokens, corrected_tokens):
        if o_token != c_token:
            highlighted.append(f"<del style='color:red;'>{o_token}</del> <span style='color:green;'>{c_token}</span>")
        else:
            highlighted.append(o_token)
    return " ".join(highlighted)

# Helper function to track corrections
def get_corrections(original, corrected):
    original_tokens = original.split()
    corrected_tokens = corrected.split()
    corrections = {}
    for o_token, c_token in zip(original_tokens, corrected_tokens):
        if o_token != c_token:
            corrections[o_token] = c_token
    return corrected_tokens, corrections

# Route for the homepage
@app.get("/", response_class=HTMLResponse)
async def get_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "result": None})

@app.post("/", response_class=HTMLResponse)
async def post_home(request: Request, text: str = Form(...), lang_code: str = Form(...)):
    if lang_code == "en":
        corrected_text = correct_grammar_english(text)
    else:
        corrected_text = correct_grammar_mbart(text, lang_code)
    
    highlighted_text = highlight_errors(text, corrected_text)
    return templates.TemplateResponse(
        "index.html", {"request": request, "result": highlighted_text, "text": text}
    )

# Data model for API requests
class CorrectionRequest(BaseModel):
    text: str
    lang_code: str

class CorrectionResponse(BaseModel):
    corrected_text: str
    corrections: dict[str, str]  # Key: Incorrect word, Value: Correct word

# API endpoint for external applications
@app.post("/api", response_model=CorrectionResponse)
async def correct_text(request: CorrectionRequest):
    if request.lang_code == "en":
        corrected_text = correct_grammar_english(request.text)
    else:
        corrected_text = correct_grammar_mbart(request.text, request.lang_code)
    
    _, corrections = get_corrections(request.text, corrected_text)
    return CorrectionResponse(corrected_text=corrected_text, corrections=corrections)
