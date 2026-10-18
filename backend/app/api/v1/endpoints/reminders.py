import uuid
from datetime import datetime
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User,Reminder
router=APIRouter(tags=["Reminders"])
class Create(BaseModel): title:str=Field(min_length=1,max_length=200); description:str|None=None; due_at:datetime
def out(x): return {"id":str(x.id),"title":x.title,"description":x.description,"due_at":x.due_at.isoformat(),"is_completed":x.is_completed}
@router.get("")
def listing(db:Session=Depends(get_db),user:User=Depends(get_current_user)): return [out(x) for x in db.query(Reminder).filter(Reminder.owner_user_id==user.id).order_by(Reminder.due_at.asc()).all()]
@router.post("")
def create(p:Create,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    x=Reminder(owner_user_id=user.id,**p.model_dump()); db.add(x); db.commit(); db.refresh(x); return out(x)
@router.patch("/{rid}/complete")
def complete(rid:str,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    try: uid=uuid.UUID(rid)
    except ValueError: raise HTTPException(400,"Invalid reminder ID.")
    x=db.query(Reminder).filter(Reminder.id==uid,Reminder.owner_user_id==user.id).first()
    if not x: raise HTTPException(404,"Reminder not found.")
    x.is_completed=True; db.commit(); db.refresh(x); return out(x)

@router.delete("/{rid}", status_code=204)
def delete(rid: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        uid = uuid.UUID(rid)
    except ValueError:
        raise HTTPException(400, "Invalid reminder ID.")
    row = db.query(Reminder).filter(Reminder.id == uid, Reminder.owner_user_id == user.id).first()
    if not row:
        raise HTTPException(404, "Reminder not found.")
    db.delete(row)
    db.commit()
    return None
