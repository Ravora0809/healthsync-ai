import hashlib,hmac,secrets
from datetime import datetime,timedelta,timezone
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError,VerificationError
from fastapi import APIRouter,Depends,HTTPException
from jose import jwt
from pydantic import BaseModel,EmailStr,Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.session import get_db
from app.models import User,PendingSignup
from app.api.deps import get_current_user
from app.services.otp import send_otp_email
router=APIRouter(tags=["Authentication"]); hasher=PasswordHasher()
class Signup(BaseModel):
    full_name:str=Field(min_length=2,max_length=120); email:EmailStr; password:str=Field(min_length=8,max_length=128); confirm_password:str=Field(min_length=8,max_length=128)
class Verify(BaseModel): email:EmailStr; otp:str=Field(pattern=r"^\d{6}$")
class Login(BaseModel): email:EmailStr; password:str
def hash_otp(email,otp): return hashlib.sha256(f"{email}:{otp}:{settings.jwt_secret}".encode()).hexdigest()
def token(user):
    now=datetime.now(timezone.utc)
    return jwt.encode({"sub":str(user.id),"email":user.email,"iat":now,"exp":now+timedelta(minutes=settings.jwt_expire_minutes)},settings.jwt_secret,algorithm="HS256")
def user_out(user): return {"id":str(user.id),"full_name":user.full_name,"email":user.email,"is_active":user.is_active,"email_verified":user.email_verified}
@router.post("/signup",status_code=202)
def signup(p:Signup,db:Session=Depends(get_db)):
    email=str(p.email).strip().lower(); name=p.full_name.strip()
    if len(name)<2: raise HTTPException(422,"Please enter your full name.")
    if p.password!=p.confirm_password: raise HTTPException(422,"Passwords do not match.")
    if db.query(User).filter(User.email==email).first(): raise HTTPException(409,"An account with this email already exists. Please log in.")
    now=datetime.now(timezone.utc); pending=db.query(PendingSignup).filter(PendingSignup.email==email).with_for_update().first()
    if pending:
        sent=pending.last_sent_at
        if sent.tzinfo is None: sent=sent.replace(tzinfo=timezone.utc)
        if (now-sent).total_seconds()<settings.otp_resend_seconds: raise HTTPException(429,"An OTP was sent recently. Please wait before trying again.")
    otp=f"{secrets.randbelow(1000000):06d}"; values=dict(full_name=name,password_hash=hasher.hash(p.password),otp_hash=hash_otp(email,otp),expires_at=now+timedelta(minutes=settings.otp_ttl_minutes),attempts=0,last_sent_at=now)
    if pending:
        for k,v in values.items(): setattr(pending,k,v)
    else: db.add(PendingSignup(email=email,**values))
    try: db.flush(); send_otp_email(email,otp); db.commit()
    except Exception: db.rollback(); raise HTTPException(503,"Unable to send verification code. Check OTP delivery settings.")
    delivery_message = ("Verification code sent to your email. Check your inbox and spam folder." if settings.otp_delivery.lower() == "smtp" else "Development OTP generated. Email delivery is disabled; check the backend logs for the code.")
    return {"message":f"{delivery_message} Your account is not created until verification.","email":email,"expires_in_minutes":settings.otp_ttl_minutes}
@router.post("/resend-otp",status_code=202)
def resend(body:dict,db:Session=Depends(get_db)):
    raw=body.get("email");
    if not isinstance(raw,str) or "@" not in raw: raise HTTPException(422,"A valid email is required.")
    email=raw.strip().lower(); p=db.query(PendingSignup).filter(PendingSignup.email==email).with_for_update().first()
    if not p: raise HTTPException(404,"No pending signup found. Please sign up again.")
    now=datetime.now(timezone.utc); sent=p.last_sent_at
    if sent.tzinfo is None: sent=sent.replace(tzinfo=timezone.utc)
    if (now-sent).total_seconds()<settings.otp_resend_seconds: raise HTTPException(429,"Please wait before requesting another code.")
    otp=f"{secrets.randbelow(1000000):06d}"; p.otp_hash=hash_otp(email,otp); p.expires_at=now+timedelta(minutes=settings.otp_ttl_minutes); p.attempts=0; p.last_sent_at=now
    try: send_otp_email(email,otp); db.commit()
    except Exception: db.rollback(); raise HTTPException(503,"Unable to send a new verification code.")
    delivery_message = ("A new verification code was sent to your email. Check your inbox and spam folder." if settings.otp_delivery.lower() == "smtp" else "Development OTP generated. Email delivery is disabled; check the backend logs for the code.")
    return {"message":delivery_message,"email":email}
@router.post("/verify-otp")
def verify(p:Verify,db:Session=Depends(get_db)):
    email=str(p.email).strip().lower(); pending=db.query(PendingSignup).filter(PendingSignup.email==email).with_for_update().first()
    if not pending: raise HTTPException(404,"No pending signup found. Please sign up again.")
    now=datetime.now(timezone.utc); exp=pending.expires_at
    if exp.tzinfo is None: exp=exp.replace(tzinfo=timezone.utc)
    if exp<=now: db.delete(pending); db.commit(); raise HTTPException(400,"Verification code expired. Please sign up again.")
    if pending.attempts>=settings.otp_max_attempts: raise HTTPException(429,"Too many incorrect attempts. Please sign up again.")
    if not hmac.compare_digest(hash_otp(email,p.otp),pending.otp_hash): pending.attempts+=1; db.commit(); raise HTTPException(400,"Invalid verification code.")
    if db.query(User).filter(User.email==email).first(): db.delete(pending); db.commit(); raise HTTPException(409,"An account with this email already exists.")
    user=User(full_name=pending.full_name,email=email,password_hash=pending.password_hash,is_active=True,email_verified=True)
    try: db.add(user); db.flush(); db.delete(pending); db.commit(); db.refresh(user)
    except IntegrityError: db.rollback(); raise HTTPException(409,"This email has already been registered.")
    return {"message":"Email verified. Account created successfully.","user":user_out(user),"access_token":token(user),"token_type":"bearer"}
@router.post("/login")
def login(p:Login,db:Session=Depends(get_db)):
    email=str(p.email).strip().lower(); user=db.query(User).filter(User.email==email).first()
    if not user: raise HTTPException(401,"Invalid email or password.")
    try: hasher.verify(user.password_hash,p.password)
    except (VerifyMismatchError,VerificationError,ValueError): raise HTTPException(401,"Invalid email or password.")
    if not user.email_verified: raise HTTPException(403,"Please verify your email before logging in.")
    if not user.is_active: raise HTTPException(403,"This account is inactive.")
    return {"message":"Login successful.","user":user_out(user),"access_token":token(user),"token_type":"bearer"}
@router.get("/me")
def me(user:User=Depends(get_current_user)): return {"user":user_out(user)}


class ChangePassword(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)


@router.post("/change-password")
def change_password(p: ChangePassword, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if p.new_password != p.confirm_password:
        raise HTTPException(422, "New password and confirmation do not match.")
    if p.current_password == p.new_password:
        raise HTTPException(422, "Choose a new password different from your current password.")
    try:
        hasher.verify(user.password_hash, p.current_password)
    except (VerifyMismatchError, VerificationError, ValueError):
        raise HTTPException(400, "Current password is incorrect.")
    user.password_hash = hasher.hash(p.new_password)
    db.add(user)
    db.commit()
    return {"message": "Password changed successfully. Sign in again on other devices if required."}
