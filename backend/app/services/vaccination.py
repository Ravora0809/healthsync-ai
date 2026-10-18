"""Conservative extraction of fields from vaccination-card OCR text."""
import re
from datetime import date

def _suggestions(text: str) -> dict:
    names = [
        "COVID-19", "Influenza", "Hepatitis B", "Hepatitis A", "HPV", "MMR", "Tdap", "DPT", "DTaP", "Td", "Tetanus", "Polio", "IPV", "OPV", "Varicella", "Chickenpox", "Rotavirus", "Pneumococcal", "Rabies", "Typhoid", "Yellow fever", "Japanese encephalitis", "Meningococcal", "BCG", "Shingles", "RSV",
    ]
    folded = text.casefold()
    suggested_name = next((name for name in names if name.casefold() in folded), "")
    date_values = []
    for match in re.finditer(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b|\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})\b", text):
        groups = match.groups()
        try:
            if groups[0]:
                dt = date(int(groups[0]), int(groups[1]), int(groups[2]))
            else:
                a, b, year = int(groups[3]), int(groups[4]), int(groups[5])
                # Ambiguous numeric dates use day/month/year (common in India); show it as a suggestion only.
                dt = date(year, b, a)
            if dt.isoformat() not in date_values:
                date_values.append(dt.isoformat())
        except ValueError:
            continue
    dose = ""
    dose_match = re.search(r"\b(?:dose|dosage)\s*(?:no\.?|number)?\s*[:#-]?\s*(\d+(?:st|nd|rd|th)?|first|second|third|booster)\b", text, flags=re.I)
    if dose_match:
        dose = dose_match.group(1)
    return {"suggested_name": suggested_name, "suggested_date_received": date_values[0] if date_values else "", "suggested_next_due": date_values[1] if len(date_values) > 1 else "", "other_dates_found": date_values[2:], "suggested_dose": dose, "needs_review": True}

