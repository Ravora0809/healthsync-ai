"""Vaccination history APIs; scanned documents are suggestions until reviewed."""
import uuid
from datetime import date, datetime, time, timezone
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User, Vaccination, Reminder
from app.api.v1.endpoints.records import upload as upload_medical_record

router = APIRouter(tags=["Vaccinations"])


class Create(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    dose: str | None = Field(default=None, max_length=80)
    date_received: date | None = None
    next_due: date | None = None
    provider: str | None = Field(default=None, max_length=200)
    notes: str | None = None


class Update(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    dose: str | None = Field(default=None, max_length=80)
    date_received: date | None = None
    next_due: date | None = None
    provider: str | None = Field(default=None, max_length=200)
    notes: str | None = None


def out(x):
    return {"id": str(x.id), "name": x.name, "dose": x.dose,
            "date_received": x.date_received.isoformat() if x.date_received else None,
            "next_due": x.next_due.isoformat() if x.next_due else None,
            "provider": x.provider, "notes": x.notes,
            "created_at": x.created_at.isoformat() if x.created_at else None}


def _sync_due_reminder(db: Session, user: User, vaccine: Vaccination) -> None:
    """Create/update/remove only the reminder owned by this vaccination entry."""
    marker = f"[AUTO_VACCINATION:{vaccine.id}]"
    rows = [r for r in db.query(Reminder).filter(Reminder.owner_user_id == user.id, Reminder.is_completed.is_(False)).all() if marker in (r.description or "")]
    if vaccine.next_due and vaccine.next_due >= date.today():
        due_at = datetime.combine(vaccine.next_due, time(hour=9), tzinfo=timezone.utc)
        description = f"{marker} Date entered or confirmed by the patient from their record. Confirm the schedule with a healthcare professional."
        if rows:
            reminder = rows[0]
            reminder.title = f"Vaccination due: {vaccine.name}"
            reminder.description = description
            reminder.due_at = due_at
            for duplicate in rows[1:]:
                db.delete(duplicate)
        else:
            db.add(Reminder(owner_user_id=user.id, title=f"Vaccination due: {vaccine.name}", description=description, due_at=due_at))
    else:
        for reminder in rows:
            db.delete(reminder)
    db.commit()


@router.get("")
def listing(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [out(x) for x in db.query(Vaccination).filter(Vaccination.owner_user_id == user.id).order_by(Vaccination.date_received.desc().nullslast(), Vaccination.created_at.desc()).all()]


@router.post("")
def create(p: Create, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    values = p.model_dump()
    values["name"] = values["name"].strip()
    if not values["name"]:
        raise HTTPException(422, "Vaccine name cannot be blank.")
    x = Vaccination(owner_user_id=user.id, **values)
    db.add(x)
    db.commit()
    db.refresh(x)
    _sync_due_reminder(db, user, x)
    db.refresh(x)
    return out(x)


from app.services.vaccination import _suggestions


@router.post("/scan")
async def scan_card(file: UploadFile = File(...), title: str | None = Form(None), use_cloud_ocr: bool = Form(True), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Store a vaccination-card image as a medical record and return editable suggestions."""
    filename = file.filename or "vaccination-card"
    document = await upload_medical_record(
        file=file, title=(title or f"Vaccination card — {filename}"), record_type="vaccination",
        provider_name=None, doctor_name=None, record_date=None, use_cloud_ocr=use_cloud_ocr,
        db=db, user=user,
    )
    suggestions = _suggestions(document.get("extracted_text") or "")
    return {"record": document, "suggestions": suggestions, "message": "Card stored. Confirm every suggested field against the image before saving the vaccination entry."}


@router.patch("/{vaccination_id}")
def update(vaccination_id: str, p: Update, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        uid = uuid.UUID(vaccination_id)
    except ValueError:
        raise HTTPException(400, "Invalid vaccination ID.")
    row = db.query(Vaccination).filter(Vaccination.id == uid, Vaccination.owner_user_id == user.id).first()
    if not row:
        raise HTTPException(404, "Vaccination record not found.")
    changes = p.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is not None:
        changes["name"] = changes["name"].strip()
        if not changes["name"]:
            raise HTTPException(422, "Vaccine name cannot be blank.")
    for k, v in changes.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    _sync_due_reminder(db, user, row)
    db.refresh(row)
    return out(row)


@router.delete("/{vaccination_id}", status_code=204)
def delete(vaccination_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        uid = uuid.UUID(vaccination_id)
    except ValueError:
        raise HTTPException(400, "Invalid vaccination ID.")
    row = db.query(Vaccination).filter(Vaccination.id == uid, Vaccination.owner_user_id == user.id).first()
    if not row:
        raise HTTPException(404, "Vaccination record not found.")
    marker = f"[AUTO_VACCINATION:{row.id}]"
    for reminder in db.query(Reminder).filter(Reminder.owner_user_id == user.id).all():
        if marker in (reminder.description or ""):
            db.delete(reminder)
    db.delete(row)
    db.commit()
    return None
