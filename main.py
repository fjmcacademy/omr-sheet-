from fastapi import FastAPI, Depends, HTTPException, Header, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import Optional
from pathlib import Path
import csv, io, json, os
import cv2, numpy as np
from .db import Base, engine, get_db
from .models import Student, Exam, Result, Slot, Booking
from .config import ADMIN_KEY, UPLOAD_DIR, MAX_UPLOAD_MB
from .security import hash_password, verify_password
from .omr import read_bubbles, evaluate
from .analytics import exam_analytics

Base.metadata.create_all(bind=engine)
Path(UPLOAD_DIR).mkdir(parents=True,exist_ok=True)
app=FastAPI(title="FJMC Academy Smart OMR",version="2.0.0")
app.mount("/static",StaticFiles(directory="app/static"),name="static")

def admin(x_admin_key: str = Header(default="")):
    if x_admin_key != ADMIN_KEY: raise HTTPException(401,"Invalid admin key")

class StudentIn(BaseModel):
    roll_no:str; name:str=""; password:str
class ExamIn(BaseModel):
    title:str; question_count:int=Field(100,ge=1,le=200); options:str="ABCD"
    positive:float=4; negative:float=1; answer_keys:dict={}
class LoginIn(BaseModel):
    roll_no:str; password:str
class KeyIn(BaseModel):
    answer_keys:dict
class SlotIn(BaseModel):
    exam_id:int; starts_at:str; capacity:int=30

@app.get("/",response_class=HTMLResponse)
def home(): return Path("app/static/index.html").read_text()

@app.get("/api/health")
def health(): return {"status":"ok","version":"2.0.0"}

@app.post("/api/students",dependencies=[Depends(admin)])
def add_student(data:StudentIn,db:Session=Depends(get_db)):
    if db.scalar(select(Student).where(Student.roll_no==data.roll_no)): raise HTTPException(409,"Roll number already exists")
    s=Student(roll_no=data.roll_no,name=data.name,password_hash=hash_password(data.password))
    db.add(s); db.commit(); db.refresh(s)
    return {"id":s.id,"roll_no":s.roll_no,"name":s.name}

@app.post("/api/student/login")
def student_login(data:LoginIn,db:Session=Depends(get_db)):
    s=db.scalar(select(Student).where(Student.roll_no==data.roll_no,Student.active==True))
    if not s or not verify_password(data.password,s.password_hash): raise HTTPException(401,"Invalid credentials")
    return {"roll_no":s.roll_no,"name":s.name}

@app.post("/api/exams",dependencies=[Depends(admin)])
def create_exam(data:ExamIn,db:Session=Depends(get_db)):
    if len(data.answer_keys)>data.question_count: raise HTTPException(400,"Too many answer keys")
    e=Exam(**data.model_dump()); db.add(e); db.commit(); db.refresh(e); return {"id":e.id,"title":e.title}

@app.get("/api/exams")
def exams(db:Session=Depends(get_db)):
    return [{"id":e.id,"title":e.title,"question_count":e.question_count,"published":e.published} for e in db.scalars(select(Exam)).all()]

@app.put("/api/exams/{exam_id}/key",dependencies=[Depends(admin)])
def update_key(exam_id:int,data:KeyIn,db:Session=Depends(get_db)):
    e=db.get(Exam,exam_id)
    if not e: raise HTTPException(404,"Exam not found")
    e.answer_keys=data.answer_keys; db.commit(); return {"saved":True,"questions":len(e.answer_keys)}

@app.post("/api/exams/{exam_id}/publish",dependencies=[Depends(admin)])
def publish(exam_id:int,db:Session=Depends(get_db)):
    e=db.get(Exam,exam_id)
    if not e: raise HTTPException(404,"Exam not found")
    e.published=True; db.commit(); return {"published":True}

@app.post("/api/scan/{exam_id}",dependencies=[Depends(admin)])
async def scan(exam_id:int, file:UploadFile=File(...), roll_no: str="", student_name: str="", db:Session=Depends(get_db)):
    e=db.get(Exam,exam_id)
    if not e: raise HTTPException(404,"Exam not found")
    raw=await file.read()
    if len(raw)>MAX_UPLOAD_MB*1024*1024: raise HTTPException(413,"File too large")
    arr=np.frombuffer(raw,np.uint8); image=cv2.imdecode(arr,cv2.IMREAD_COLOR)
    if image is None: raise HTTPException(400,"Unsupported image; upload JPG or PNG")
    try: parsed=read_bubbles(image,e.question_count,e.options)
    except Exception as ex: raise HTTPException(422,f"OMR processing failed: {ex}")
    answers=parsed["answers"]
    marks=evaluate(answers,e.answer_keys,e.positive,e.negative) if e.answer_keys else {"score":0,"correct":0,"wrong":0,"blank":e.question_count}
    student=db.scalar(select(Student).where(Student.roll_no==roll_no)) if roll_no else None
    result=Result(exam_id=e.id,student_id=student.id if student else None,roll_no=roll_no or "UNREAD",
      student_name=student_name or (student.name if student else ""),answers=answers,score=marks["score"],
      correct=marks["correct"],wrong=marks["wrong"],blank=marks["blank"],
      review_required=bool(parsed["review_questions"]) or parsed["confidence"]<0.55,confidence=parsed["confidence"])
    db.add(result); db.commit(); db.refresh(result)
    return {"result_id":result.id,"roll_no":result.roll_no,"answers":answers,"marks":marks,
      "confidence":parsed["confidence"],"review_required":result.review_required,
      "review_questions":parsed["review_questions"],"scanner_note":parsed["note"],
      "warning":"Template geometry must be calibrated against your printed answer sheet before live exams."}

@app.get("/api/results/{result_id}",dependencies=[Depends(admin)])
def get_result(result_id:int,db:Session=Depends(get_db)):
    r=db.get(Result,result_id)
    if not r: raise HTTPException(404,"Result not found")
    return {"id":r.id,"exam_id":r.exam_id,"roll_no":r.roll_no,"name":r.student_name,"answers":r.answers,
      "score":r.score,"correct":r.correct,"wrong":r.wrong,"blank":r.blank,
      "confidence":r.confidence,"review_required":r.review_required}

@app.get("/api/student/{roll_no}/results")
def student_results(roll_no:str,db:Session=Depends(get_db)):
    s=db.scalar(select(Student).where(Student.roll_no==roll_no))
    if not s: raise HTTPException(404,"Student not found")
    rows=db.scalars(select(Result).where(Result.roll_no==roll_no).order_by(Result.created_at.desc())).all()
    return [{"id":r.id,"exam_id":r.exam_id,"score":r.score,"correct":r.correct,"wrong":r.wrong,"blank":r.blank} for r in rows]

@app.get("/api/exams/{exam_id}/analytics",dependencies=[Depends(admin)])
def analytics(exam_id:int,db:Session=Depends(get_db)):
    e=db.get(Exam,exam_id)
    if not e: raise HTTPException(404,"Exam not found")
    rows=db.scalars(select(Result).where(Result.exam_id==exam_id)).all()
    data=exam_analytics(rows,e.question_count)
    ranked=sorted(rows,key=lambda r:r.score,reverse=True)
    data["leaderboard"]=[{"rank":i+1,"roll_no":r.roll_no,"name":r.student_name,"score":r.score} for i,r in enumerate(ranked)]
    return data

@app.get("/api/exams/{exam_id}/export.csv",dependencies=[Depends(admin)])
def export_csv(exam_id:int,db:Session=Depends(get_db)):
    rows=db.scalars(select(Result).where(Result.exam_id==exam_id).order_by(Result.score.desc())).all()
    buf=io.StringIO(); w=csv.writer(buf); w.writerow(["roll_no","name","score","correct","wrong","blank","confidence","review_required"])
    for r in rows: w.writerow([r.roll_no,r.student_name,r.score,r.correct,r.wrong,r.blank,r.confidence,r.review_required])
    buf.seek(0); return StreamingResponse(iter([buf.getvalue()]),media_type="text/csv",headers={"Content-Disposition":f"attachment; filename=exam_{exam_id}_results.csv"})

@app.post("/api/slots",dependencies=[Depends(admin)])
def create_slot(data:SlotIn,db:Session=Depends(get_db)):
    if not db.get(Exam,data.exam_id): raise HTTPException(404,"Exam not found")
    s=Slot(**data.model_dump()); db.add(s); db.commit(); db.refresh(s); return {"id":s.id}

@app.get("/api/slots")
def list_slots(db:Session=Depends(get_db)):
    return [{"id":s.id,"exam_id":s.exam_id,"starts_at":s.starts_at,"capacity":s.capacity,"booked":s.booked} for s in db.scalars(select(Slot)).all()]

@app.post("/api/slots/{slot_id}/book")
def book_slot(slot_id:int,roll_no:str,db:Session=Depends(get_db)):
    s=db.get(Slot,slot_id)
    if not s: raise HTTPException(404,"Slot not found")
    if s.booked>=s.capacity: raise HTTPException(409,"Slot is full")
    if db.scalar(select(Booking).where(Booking.slot_id==slot_id,Booking.roll_no==roll_no)): raise HTTPException(409,"Already booked")
    db.add(Booking(slot_id=slot_id,roll_no=roll_no)); s.booked+=1; db.commit(); return {"booked":True}

@app.get("/api/admin/review-queue",dependencies=[Depends(admin)])
def review_queue(db:Session=Depends(get_db)):
    rows=db.scalars(select(Result).where(Result.review_required==True).order_by(Result.created_at.desc())).all()
    return [{"id":r.id,"exam_id":r.exam_id,"roll_no":r.roll_no,"confidence":r.confidence,"answers":r.answers} for r in rows]
