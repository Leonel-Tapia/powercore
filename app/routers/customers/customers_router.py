# PATH: app/routers/customers/customers_router.py | UPDATED: 2026-08-03
import re
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from datetime import datetime
from decimal import Decimal

from app.database.database import get_db
from app.core.template_loader import jinja as templates
from app.models.customers.customer_model import Customer


router = APIRouter(
    prefix="/customers",
    tags=["customers"]
)


# ============================================================
# ⭐ 0. LIVE SEARCH JSON
# ============================================================
@router.get("/search-json")
def customers_search_json(q: str = "", db: Session = Depends(get_db)):

    q_clean = re.sub(r'\D', '', q)

    query = (
        db.query(Customer)
        .filter(
            or_(
                Customer.name.ilike(f"%{q}%"),
                Customer.phone.ilike(f"%{q}%"),
                Customer.phone_numeric.ilike(f"%{q_clean}%") if q_clean else False
            )
        )
        .order_by(Customer.name.asc())
        .limit(20)
        .all()
    )

    return [
        {
            "id": c.id,
            "name": c.name,
            "phone": c.phone,
            "mood": c.mood,
            "status": c.status
        }
        for c in query
    ]


# ============================================================
# 1. LIST VIEW
# ============================================================
@router.get("/list", response_class=HTMLResponse)
def customers_list(
    request: Request,
    db: Session = Depends(get_db),
    page: int = 1,
    search: str = ""
):
    limit = 15
    offset = (page - 1) * limit

    query = db.query(Customer)

    if search:
        search_term = f"%{search}%"
        search_clean = re.sub(r'\D', '', search)
        search_digits = f"%{search_clean}%" if search_clean else "%"

        query = query.filter(
            or_(
                Customer.name.ilike(search_term),
                Customer.phone.ilike(search_term),
                Customer.phone_numeric.ilike(search_digits)
            )
        )

    query = query.order_by(Customer.name.asc())

    total = query.count()
    total_pages = (total + limit - 1) // limit

    customers = query.offset(offset).limit(limit).all()

    return templates.TemplateResponse(
        request=request,
        name="customers/customers_list.html",
        context={
            "customers": customers,
            "page": page,
            "total_pages": total_pages,
            "search": search
        }
    )


# ============================================================
# 2. ADD FORM VIEW
# ============================================================
@router.get("/add", response_class=HTMLResponse)
def customers_add_form(
    request: Request,
    name: str = "",
    phone: str = "",
    origin: str = "manager"
):
    return templates.TemplateResponse(
        request=request,
        name="customers/customers_add.html",
        context={
            "name": name,
            "phone": phone,
            "origin": origin
        }
    )


# ============================================================
# 3. ADD CUSTOMER (POST)
# ============================================================
@router.post("/add")
def customers_add(
    name: str = Form(...),
    business_name: str = Form(None),
    contact_name: str = Form(None),
    contact_phone: str = Form(None),
    contact_name2: str = Form(None),
    contact_phone2: str = Form(None),
    contact_relationship: str = Form(None),
    phone: str = Form(None),
    phone2: str = Form(None),
    email: str = Form(None),
    address: str = Form(None),
    city: str = Form(None),
    state: str = Form(None),
    zip_code: str = Form(None),
    tax_id: str = Form(None),
    language: str = Form(None),
    customer_type: str = Form(None),
    mood: str = Form(None),
    status: str = Form("ACTIVE"),
    internal_notes: str = Form(None),
    allow_sms: str = Form("true"),
    sms_opt_out_reason: str = Form(None),
    preferred_contact_method: str = Form(None),
    preferred_contact: str = Form(None),
    referral_source: str = Form(None),
    tags: str = Form(None),
    birthday: str = Form(None),
    last_purchase_date: str = Form(None),
    credit_limit: str = Form("0"),
    customer_rating: str = Form(None),
    is_tax_exempt: str = Form("false"),
    tax_exempt: str = Form("false"),
    tax_exempt_license: str = Form(None),
    origin: str = Form("manager"),
    db: Session = Depends(get_db)
):

    allow_sms_bool = allow_sms.lower() == "true"
    is_tax_exempt_bool = is_tax_exempt.lower() == "true"
    tax_exempt_bool = tax_exempt.lower() == "true"

    birthday_date = datetime.strptime(birthday, "%Y-%m-%d").date() if birthday else None
    last_purchase_date_date = datetime.strptime(last_purchase_date, "%Y-%m-%d").date() if last_purchase_date else None

    try:
        credit_limit_decimal = Decimal(credit_limit)
    except:
        credit_limit_decimal = Decimal("0.00")

    customer_rating_int = int(customer_rating) if customer_rating and customer_rating.isdigit() else None

    new_customer = Customer(
        name=name,
        business_name=business_name,
        contact_name=contact_name,
        contact_phone=contact_phone,
        contact_phone_numeric=re.sub(r'\D', '', contact_phone or ""),
        contact_name2=contact_name2,
        contact_phone2=contact_phone2,
        contact_phone2_numeric=re.sub(r'\D', '', contact_phone2 or ""),
        contact_relationship=contact_relationship,
        phone=phone,
        phone_numeric=re.sub(r'\D', '', phone or ""),
        phone2=phone2,
        phone2_numeric=re.sub(r'\D', '', phone2 or ""),
        email=email,
        address=address,
        city=city,
        state=state,
        zip_code=zip_code,
        tax_id=tax_id,
        language=language,
        customer_type=customer_type,
        mood=mood,
        status=status,
        internal_notes=internal_notes,
        allow_sms=allow_sms_bool,
        sms_opt_out_reason=sms_opt_out_reason,
        preferred_contact_method=preferred_contact_method,
        preferred_contact=preferred_contact,
        referral_source=referral_source,
        tags=tags,
        birthday=birthday_date,
        last_purchase_date=last_purchase_date_date,
        credit_limit=credit_limit_decimal,
        customer_rating=customer_rating_int,
        is_tax_exempt=is_tax_exempt_bool,
        tax_exempt=tax_exempt_bool,
        tax_exempt_license=tax_exempt_license
    )

    try:
        db.add(new_customer)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[POWERCORE ERROR] {str(e)}")

    # Redirección dinámica basada en el origen
    if origin == "call_center":
        return RedirectResponse(url="/call_center/search", status_code=303)
    
    return RedirectResponse(url="/customers/list", status_code=303)