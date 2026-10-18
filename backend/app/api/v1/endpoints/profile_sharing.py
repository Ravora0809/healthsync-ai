from __future__ import annotations
import hashlib, secrets, smtplib, uuid
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models import User, MedicalRecord, AuditEvent
from app.models.models import HealthProfile, SecureShare

router = APIRouter(tags=["Health profile and secure sharing"])

class ProfileBody(BaseModel):
    data: dict = Field(default_factory=dict)
class ShareBody(BaseModel):
    recipient_name: str = Field(min_length=2, max_length=200)
    recipient_email: EmailStr
    record_ids: list[str] = Field(min_length=1, max_length=100)
    purpose: str = Field(min_length=5, max_length=500)
    expires_in_hours: int = Field(default=72, ge=1, le=168)

def audit(db, user_id, action, details):
    db.add(AuditEvent(owner_user_id=user_id, action=action, details=details))

def send_share_email(to_email: str, recipient_name: str, owner_name: str, url: str, purpose: str, expiry: datetime):
    if not (settings.smtp_host and settings.smtp_user and settings.smtp_app_password):
        raise HTTPException(503, "Secure sharing email is not configured. Set SMTP_HOST, SMTP_USER, SMTP_APP_PASSWORD and SMTP_FROM; no share was created.")
    msg=EmailMessage(); msg["Subject"]="Secure HEALTHSYNC-AI medical-record access"; msg["From"]=settings.smtp_from or settings.smtp_user; msg["To"]=to_email
    msg.set_content(f"Hello {recipient_name},\n\n{owner_name} has securely shared selected medical records with you.\nPurpose: {purpose}\nAccess expires: {expiry.strftime('%Y-%m-%d %H:%M UTC')}\n\nOpen the secure link: {url}\n\nThis link grants access only to the selected records and expires automatically. The patient can revoke it earlier. Do not forward this email. If you were not expecting this, do not open the link and contact the sender.\n")
    try:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.login(settings.smtp_user, settings.smtp_app_password); smtp.send_message(msg)
    except Exception as exc:
        raise HTTPException(502, f"Could not deliver secure sharing email; no share was created ({type(exc).__name__}).")

@router.get("/profile")
def get_profile(db: Session=Depends(get_db), user: User=Depends(get_current_user)):
    row=db.query(HealthProfile).filter(HealthProfile.owner_user_id==user.id).first()
    return {"data": row.data if row else {}, "updated_at": row.updated_at.isoformat() if row else None}

@router.put("/profile")
def save_profile(p: ProfileBody, db: Session=Depends(get_db), user: User=Depends(get_current_user)):
    allowed={"date_of_birth","sex_at_birth","height_cm","weight_kg","blood_group","allergies","conditions","medications","surgeries","family_history","emergency_contact_name","emergency_contact_phone","primary_doctor","primary_hospital","insurance_provider","insurance_policy_number","preferred_pharmacy","notes"}
    if set(p.data)-allowed: raise HTTPException(422, "Unsupported profile fields: "+", ".join(sorted(set(p.data)-allowed)))
    for k,v in p.data.items():
        if not isinstance(v,(str,int,float,type(None))): raise HTTPException(422, f"Invalid value for {k}.")
        if isinstance(v,str) and len(v)>5000: raise HTTPException(422, f"Value too long for {k}.")
    row=db.query(HealthProfile).filter(HealthProfile.owner_user_id==user.id).first()
    if row: row.data=p.data
    else: row=HealthProfile(owner_user_id=user.id,data=p.data); db.add(row)
    audit(db,user.id,"health_profile_updated",{"fields":sorted(p.data.keys())}); db.commit(); db.refresh(row)
    return {"data":row.data,"updated_at":row.updated_at.isoformat()}

@router.post("/shares", status_code=201)
def create_share(p: ShareBody, request: Request, db: Session=Depends(get_db), user: User=Depends(get_current_user)):
    ids=[]
    for raw in p.record_ids:
        try: ids.append(str(uuid.UUID(raw)))
        except ValueError: raise HTTPException(422,"One of the selected record IDs is invalid.")
    ids=list(dict.fromkeys(ids))
    rows=db.query(MedicalRecord).filter(MedicalRecord.owner_user_id==user.id, MedicalRecord.id.in_([uuid.UUID(x) for x in ids])).all()
    if len(rows)!=len(ids): raise HTTPException(404,"One or more selected records were not found in your account.")
    configured_url = settings.public_app_url.strip()
    parsed_url = urlparse(configured_url) if configured_url else None
    is_https_url = bool(parsed_url and parsed_url.scheme == "https" and parsed_url.hostname and not parsed_url.username and not parsed_url.password)
    # HTTP is allowed only for loopback development so local testing works without
    # weakening the HTTPS requirement for staging/production deployments.
    is_local_dev_url = bool(
        settings.environment.lower() == "development"
        and parsed_url
        and parsed_url.scheme == "http"
        and parsed_url.hostname in {"localhost", "127.0.0.1"}
        and not parsed_url.username
        and not parsed_url.password
    )
    if not (is_https_url or is_local_dev_url):
        raise HTTPException(
            503,
            "Secure sharing requires PUBLIC_APP_URL to be HTTPS. For local development only, use http://localhost:5173 or http://127.0.0.1:5173 with ENVIRONMENT=development. No share was created.",
        )
    token=secrets.token_urlsafe(32); token_hash=hashlib.sha256(token.encode()).hexdigest(); expiry=datetime.now(timezone.utc)+timedelta(hours=p.expires_in_hours)
    row=SecureShare(owner_user_id=user.id,recipient_name=p.recipient_name.strip(),recipient_email=str(p.recipient_email).lower(),record_ids=ids,token_hash=token_hash,purpose=p.purpose.strip(),expires_at=expiry)
    db.add(row); db.flush()
    url=f"{settings.public_app_url.rstrip('/')}/shared/{token}"
    try: send_share_email(row.recipient_email,row.recipient_name,user.full_name,url,row.purpose,expiry)
    except Exception: db.rollback(); raise
    audit(db,user.id,"secure_share_created",{"share_id":str(row.id),"recipient_email":row.recipient_email,"record_count":len(ids),"expires_at":expiry.isoformat(),"purpose":row.purpose})
    db.commit(); db.refresh(row)
    return {"id":str(row.id),"recipient_name":row.recipient_name,"recipient_email":row.recipient_email,"record_count":len(ids),"purpose":row.purpose,"expires_at":expiry.isoformat(),"revoked":False,"email_sent":True}

@router.get("/shares")
def list_shares(db: Session=Depends(get_db), user: User=Depends(get_current_user)):
    rows=db.query(SecureShare).filter(SecureShare.owner_user_id==user.id).order_by(SecureShare.created_at.desc()).limit(100).all(); now=datetime.now(timezone.utc)
    return [{"id":str(x.id),"recipient_name":x.recipient_name,"recipient_email":x.recipient_email,"record_count":len(x.record_ids),"purpose":x.purpose,"expires_at":x.expires_at.isoformat(),"revoked":bool(x.revoked_at),"expired":(x.expires_at.replace(tzinfo=timezone.utc) if x.expires_at.tzinfo is None else x.expires_at)<=now,"created_at":x.created_at.isoformat()} for x in rows]

@router.post("/shares/{share_id}/revoke")
def revoke_share(share_id: str, db: Session=Depends(get_db), user: User=Depends(get_current_user)):
    try: sid=uuid.UUID(share_id)
    except ValueError: raise HTTPException(400,"Invalid share ID.")
    row=db.query(SecureShare).filter(SecureShare.id==sid,SecureShare.owner_user_id==user.id).first()
    if not row: raise HTTPException(404,"Share not found.")
    if not row.revoked_at: row.revoked_at=datetime.now(timezone.utc); audit(db,user.id,"secure_share_revoked",{"share_id":str(row.id),"recipient_email":row.recipient_email}); db.commit()
    return {"id":str(row.id),"revoked":True}

def resolve_share(token: str, db: Session):
    row=db.query(SecureShare).filter(SecureShare.token_hash==hashlib.sha256(token.encode()).hexdigest()).first()
    now=datetime.now(timezone.utc)
    if not row or row.revoked_at or (row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at.tzinfo is None else row.expires_at)<=now:
        raise HTTPException(410,"This secure share link is invalid, expired, or revoked.")
    return row

@router.get("/shared/{token}")
def shared_record_list(token: str, request: Request, db: Session=Depends(get_db)):
    share=resolve_share(token,db); ids=[uuid.UUID(x) for x in share.record_ids]
    rows=db.query(MedicalRecord).filter(MedicalRecord.owner_user_id==share.owner_user_id,MedicalRecord.id.in_(ids)).all()
    share.last_accessed_at=datetime.now(timezone.utc); audit(db,share.owner_user_id,"secure_share_accessed",{"share_id":str(share.id),"record_count":len(rows)}); db.commit()
    return {"shared_by":db.query(User).filter(User.id==share.owner_user_id).first().full_name,"recipient_name":share.recipient_name,"purpose":share.purpose,"expires_at":share.expires_at.isoformat(),"records":[{"id":str(r.id),"title":r.title,"record_type":r.record_type,"record_date":r.record_date.isoformat() if r.record_date else None,"provider_name":r.provider_name,"doctor_name":r.doctor_name,"extracted_text":r.extracted_text,"extracted_data":r.extracted_data or {},"file_url":f"/api/secure-sharing/shared/{token}/records/{r.id}/file"} for r in rows]}

@router.get("/shared/{token}/records/{record_id}/file")
def shared_file(token: str, record_id: str, db: Session=Depends(get_db)):
    share=resolve_share(token,db)
    try: rid=uuid.UUID(record_id)
    except ValueError: raise HTTPException(404,"Record not found.")
    if str(rid) not in share.record_ids: raise HTTPException(403,"This record was not included in the share.")
    record=db.query(MedicalRecord).filter(MedicalRecord.id==rid,MedicalRecord.owner_user_id==share.owner_user_id).first()
    if not record: raise HTTPException(404,"Record not found.")
    path=Path(record.storage_key).resolve()
    owner_dir=(Path(settings.upload_dir)/str(share.owner_user_id)).resolve()
    if owner_dir not in path.parents: raise HTTPException(403,"Stored file path is outside this patient storage area.")
    if not path.is_file(): raise HTTPException(404,"Original document is unavailable.")
    share.last_accessed_at=datetime.now(timezone.utc); audit(db,share.owner_user_id,"secure_share_file_accessed",{"share_id":str(share.id),"record_id":str(record.id)}); db.commit()
    return FileResponse(path,filename=record.original_filename,media_type="application/octet-stream",headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff","Content-Security-Policy":"default-src 'none'; sandbox"})
