from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm
import pandas as pd
import models, schemas, auth, database
from database import engine

# Create tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Budget Planner API")

# --- Authentication ---
@app.post("/register")
def register(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    existing_user = db.query(models.User).filter(models.User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    hashed_pw = auth.get_password_hash(user.password)
    new_user = models.User(username=user.username, hashed_password=hashed_pw)
    db.add(new_user)
    db.commit()
    return {"message": "User created successfully"}

@app.post("/token", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = auth.create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

# --- Transactions CRUD ---
@app.post("/transactions/", response_model=schemas.TransactionResponse)
def create_transaction(
    transaction: schemas.TransactionCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    new_trans = models.Transaction(**transaction.dict(), user_id=current_user.id)
    db.add(new_trans)
    db.commit()
    db.refresh(new_trans)
    return new_trans

@app.get("/transactions/")
def get_transactions(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    return db.query(models.Transaction).filter(models.Transaction.user_id == current_user.id).all()

@app.delete("/transactions/{id}")
def delete_transaction(
    id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    trans = db.query(models.Transaction).filter(models.Transaction.id == id, models.Transaction.user_id == current_user.id).first()
    if not trans:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(trans)
    db.commit()
    return {"message": "Deleted"}

# --- Analysis & Reports (Pandas) ---
@app.get("/reports/summary")
def get_summary(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # Fetch data
    query = db.query(models.Transaction).filter(models.Transaction.user_id == current_user.id)
    df = pd.read_sql(query.statement, db.bind)
    
    if df.empty:
        return {"message": "No data available"}

    # Pandas Analysis
    total_income = df[df['type'] == 'income']['amount'].sum()
    total_expense = df[df['type'] == 'expense']['amount'].sum()
    balance = total_income - total_expense
    
    # Group by category
    category_group = df.groupby('category')['amount'].sum().to_dict()

    return {
        "total_income": total_income,
        "total_expense": total_expense,
        "balance": balance,
        "spending_by_category": category_group
    }

@app.get("/reports/chart-data")
def get_chart_data(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Returns data formatted specifically for frontend charts"""
    query = db.query(models.Transaction).filter(models.Transaction.user_id == current_user.id)
    df = pd.read_sql(query.statement, db.bind)
    
    if df.empty:
        return []

    # Prepare data for a monthly bar chart
    df['date'] = pd.to_datetime(df['date'])
    df['month'] = df['date'].dt.strftime('%Y-%m')
    monthly = df.groupby(['month', 'type'])['amount'].sum().unstack().fillna(0).reset_index()
    
    return monthly.to_dict(orient="records")