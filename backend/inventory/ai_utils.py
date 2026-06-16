import re
from google.cloud import vision

def parse_label_text(text, region_scan=None):
    """
    Parses OCR text to find potential batch numbers, expiry dates, quantities, and product names
    and calculates a confidence score for each.
    """
    results = {
        "product_name": {"value": None, "confidence": 0},
        "batch_number": {"value": None, "confidence": 0},
        "expiry_date": {"value": None, "confidence": 0},
        "quantity": {"value": None, "confidence": 0},
        "barcode": {"value": None, "confidence": 0},
        "raw_text": text
    }

    lines = text.split('\n')
    
    # Batch Number
    # Strong match: "BATCH:", "LOT:", "BN:"
    batch_strong = re.search(r'(?i)(?:BATCH|LOT|BN)[\s\:\#]*([A-Z0-9\-]+)', text)
    if batch_strong:
        results['batch_number'] = {"value": batch_strong.group(1), "confidence": 95}
    elif region_scan == 'batch':
        # If user explicitly scanned a region for batch, take the most likely alphanumeric string
        tokens = [t for t in text.split() if any(c.isdigit() for c in t) and len(t) >= 4]
        if tokens:
            results['batch_number'] = {"value": tokens[0], "confidence": 85}

    # Expiry Date
    # Strong match: "EXP", "EXPIRY", "BEST BEFORE"
    exp_strong = re.search(r'(?i)(?:EXP|EXPIRY|BEST BEFORE)[\s\:\.]*(\d{2,4}[-/]\d{2,4}(?:[-/]\d{2,4})?)', text)
    if exp_strong:
        results['expiry_date'] = {"value": exp_strong.group(1), "confidence": 95}
    else:
        # Weak match: just look for a date pattern
        exp_weak = re.search(r'(\d{2,4}[-/]\d{2,4}(?:[-/]\d{2,4})?)', text)
        if exp_weak:
            results['expiry_date'] = {"value": exp_weak.group(1), "confidence": 60}
            if region_scan == 'expiry':
                results['expiry_date']['confidence'] = 90

    # Quantity
    # "20 Tablets", "50 Sachets", "Pack of 10"
    qty_match = re.search(r'(?i)(\d+)[\s]*(Tablets|Sachets|Condoms|Capsules|Vials|Pills)', text)
    if qty_match:
        results['quantity'] = {"value": qty_match.group(1), "confidence": 90}
    else:
        qty_pack = re.search(r'(?i)Pack of (\d+)', text)
        if qty_pack:
            results['quantity'] = {"value": qty_pack.group(1), "confidence": 95}

    # Product Name
    # Usually the largest text, but in raw OCR it's often the first or second line, without numbers.
    for line in lines:
        line = line.strip()
        if len(line) > 3 and not any(c.isdigit() for c in line) and not re.search(r'(?i)(batch|lot|exp|mfg)', line):
            # Potential product name
            results['product_name'] = {"value": line, "confidence": 75}
            break

    return results

def analyze_image_with_vision(image_content, region_scan=None):
    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=image_content)
    
    response = client.text_detection(image=image)
    texts = response.text_annotations
    
    if response.error.message:
        raise Exception(
            f"{response.error.message}\nFor more info on error messages, check: "
            "https://cloud.google.com/apis/design/errors"
        )
        
    if texts:
        full_text = texts[0].description
        return parse_label_text(full_text, region_scan)
    
    return {
        "product_name": {"value": None, "confidence": 0},
        "batch_number": {"value": None, "confidence": 0},
        "expiry_date": {"value": None, "confidence": 0},
        "quantity": {"value": None, "confidence": 0},
        "barcode": {"value": None, "confidence": 0},
        "raw_text": ""
    }
