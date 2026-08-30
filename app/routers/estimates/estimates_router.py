# /app/routers/estimates/estimates_router.py | Updated: 2026-08-15
from fastapi import APIRouter, Request, Depends, Form, HTTPException, Path, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from datetime import datetime
from typing import List, Optional
from app.database.database import get_db
from app.core.template_loader import jinja as templates

from app.models.estimates.estimate_model import Estimate, EstimateDetail
from app.models.customers.customer_model import Customer
from app.models.inventory.year_model import Year
from app.models.inventory.time_model import TimeCatalog
from app.models.company.company import Company

router = APIRouter(
    prefix="/estimates",
    tags=["estimates"]
)

# ============================================================
# 0. CHECK AVAILABILITY ENDPOINT (AJAX / MODAL)
# ============================================================
@router.get("/invoices/check")
def check_availability(
    date: str,
    time: str,
    service_type: str,
    exclude_estimate_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    clean_time = time[:5] if time else ""

    estimates = db.query(Estimate).filter(
        Estimate.estimated_appointment_date == date,
        Estimate.service_type == service_type.upper(),
        Estimate.status != "Void"
    ).all()

    estimate_exists = any(
        str(est.estimated_appointment_time)[:5] == clean_time
        and (not exclude_estimate_id or est.id != exclude_estimate_id)
        for est in estimates
    )

    invoice_exists = False
    is_occupied = estimate_exists or invoice_exists

    return {"exists": is_occupied}


# ============================================================
# 1. NEW ESTIMATE VIEW
# ============================================================
@router.get("/new/{customer_id}", response_class=HTMLResponse)
def create_estimate_view(
    customer_id: int, 
    request: Request, 
    origin: Optional[str] = None, 
    db: Session = Depends(get_db)
):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    years = db.query(Year).order_by(Year.year.desc()).all()
    times = db.query(TimeCatalog).order_by(TimeCatalog.time_value.asc()).all()
    company = db.query(Company).first()

    return templates.TemplateResponse(
        request=request,
        name="estimates/estimates_add.html",
        context={
            "customer": customer,
            "estimate": None,
            "years": years,
            "times": times,
            "company": company,
            "origin": origin
        }
    )


# ============================================================
# 2. EDIT EXISTING ESTIMATE VIEW
# ============================================================
@router.get("/edit/{estimate_id}", response_class=HTMLResponse)
def edit_estimate_view(
    estimate_id: int, 
    request: Request, 
    origin: Optional[str] = None,
    selected_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    estimate = db.query(Estimate).filter(Estimate.id == estimate_id).first()
    if not estimate:
        return RedirectResponse("/customers/list", status_code=303)

    customer = db.query(Customer).filter(Customer.id == estimate.customer_id).first()
    estimate_details = db.query(EstimateDetail).filter(EstimateDetail.estimate_id == estimate_id).all()
    
    years = db.query(Year).order_by(Year.year.desc()).all()
    times = db.query(TimeCatalog).order_by(TimeCatalog.time_value.asc()).all()
    company = db.query(Company).first()

    return templates.TemplateResponse(
        request=request,
        name="estimates/estimates_editar.html",
        context={
            "customer": customer,
            "estimate": estimate,
            "estimate_details": estimate_details,
            "years": years,
            "times": times,
            "company": company,
            "origin": origin,
            "selected_date": selected_date
        }
    )


# ============================================================
# 2.5 AFTER SAVE VIEW
# ============================================================
@router.get("/after_save/{estimate_id}", response_class=HTMLResponse)
def after_save_view(
    estimate_id: int, 
    request: Request, 
    origin: Optional[str] = None, 
    db: Session = Depends(get_db)
):
    estimate = db.query(Estimate).filter(Estimate.id == estimate_id).first()
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")
    
    history = db.query(Estimate)\
        .filter(Estimate.customer_id == estimate.customer_id)\
        .order_by(Estimate.id.desc())\
        .limit(3).all()

    return templates.TemplateResponse(
        request=request,
        name="estimates/estimate_after_save.html",
        context={
            "estimate": estimate,
            "estimate_id": estimate_id,
            "customer_id": estimate.customer_id,
            "history": history,
            "origin": origin 
        }
    )


# ============================================================
# 3. SAVE ESTIMATE (POST)
# ============================================================
@router.post("/save")
def save_estimate(
    request: Request,
    customer_id: int = Form(...),
    estimate_id: str = Form(...),
    service_type: str = Form(...),
    vehicle_year_id: int = Form(...),
    vehicle_vin: Optional[str] = Form(None),
    vehicle_make: Optional[str] = Form(None),
    vehicle_model: Optional[str] = Form(None),
    estimated_appointment_date: Optional[str] = Form(None),
    estimated_appointment_time: Optional[str] = Form(None),
    labor: float = Form(0.0),
    mat: float = Form(0.0),
    misc: float = Form(0.0),
    subtotal: float = Form(0.0),
    tax_total: float = Form(0.0),
    total_amount: float = Form(0.0),
    alt_full_name: Optional[str] = Form(None),
    alt_phone: Optional[str] = Form(None),
    alt_relationship: Optional[str] = Form(None),
    mobile_fee_override: Optional[str] = Form(None),
    origin: Optional[str] = Form(None),
    product_name: List[str] = Form(..., alias="product_name[]"),
    description: List[str] = Form(..., alias="description[]"),
    quantity: List[int] = Form(..., alias="quantity[]"),
    cost: List[float] = Form(..., alias="cost[]"),
    price: List[float] = Form(..., alias="price[]"),
    is_taxable: List[str] = Form(None, alias="is_taxable[]"),
    tax_amount: List[float] = Form([], alias="tax_amount[]"),
    db: Session = Depends(get_db)
):
    current_username = request.session.get("username")
    
    new_estimate = Estimate(
        customer_id=customer_id,
        service_type=service_type,
        vehicle_year_id=vehicle_year_id,
        vehicle_vin=vehicle_vin,
        vehicle_make=vehicle_make,
        vehicle_model=vehicle_model,
        estimated_appointment_date=estimated_appointment_date,
        estimated_appointment_time=estimated_appointment_time,
        labor_cost=labor,
        materials_cost=mat,
        misc_cost=misc,
        subtotal=subtotal,
        tax=tax_total,
        total=total_amount,
        alt_contact_name=alt_full_name,
        alt_contact_phone=alt_phone,
        alt_contact_relation=alt_relationship,
        mobile_fee_override=(mobile_fee_override == "true"),
        status="Estimate",
        operator_username=current_username
    )
    db.add(new_estimate)
    db.commit()
    db.refresh(new_estimate)
    target_id = new_estimate.id

    tax_list = is_taxable if is_taxable else []
    
    for i in range(len(product_name)):
        is_tax = "on" in str(tax_list[i]) if i < len(tax_list) else False
        
        new_detail = EstimateDetail(
            estimate_id=target_id,
            product_name=product_name[i],
            description=description[i],
            quantity=quantity[i],
            cost=cost[i],
            price=price[i],
            is_taxable=is_tax,
            tax_amount=tax_amount[i],
            part_number=product_name[i],
            supplier=None
        )
        db.add(new_detail)
    
    db.commit()

    resolved_origin = origin or request.query_params.get("origin")
    origin_param = f"?origin={resolved_origin}" if resolved_origin else ""
    
    return RedirectResponse(url=f"/estimates/after_save/{target_id}{origin_param}", status_code=303)


# ============================================================
# 3.5 UPDATE ESTIMATE (POST)
# ============================================================
@router.post("/update/{estimate_id}")
def update_estimate(
    estimate_id: int = Path(...),
    request: Request = None,
    origin: Optional[str] = Form(None),
    selected_date: Optional[str] = Form(None),
    customer_id: int = Form(...),
    service_type: str = Form("Mobile"),
    vehicle_year_id: int = Form(...),
    vehicle_vin: Optional[str] = Form(None),
    vehicle_make: Optional[str] = Form(None),
    vehicle_model: Optional[str] = Form(None),
    estimated_appointment_date: Optional[str] = Form(None),
    estimated_appointment_time: Optional[str] = Form(None),
    labor: float = Form(0.0),
    mat: float = Form(0.0),
    misc: float = Form(0.0),
    subtotal: float = Form(0.0),
    tax_total: float = Form(0.0),
    total_amount: float = Form(0.0),
    alt_full_name: Optional[str] = Form(None),
    alt_phone: Optional[str] = Form(None),
    alt_relationship: Optional[str] = Form(None),
    mobile_fee_override: Optional[str] = Form(None),
    product_name: List[str] = Form([], alias="product_name[]"),
    description: List[str] = Form([], alias="description[]"),
    quantity: List[int] = Form([], alias="quantity[]"),
    cost: List[float] = Form([], alias="cost[]"),
    price: List[float] = Form([], alias="price[]"),
    is_taxable: List[str] = Form(None, alias="is_taxable[]"),
    tax_amount: List[float] = Form([], alias="tax_amount[]"),
    db: Session = Depends(get_db)
):
    target_id = estimate_id
    est = db.query(Estimate).filter(Estimate.id == target_id).first()
    
    if est:
        est.service_type = service_type
        est.vehicle_year_id = vehicle_year_id
        est.vehicle_vin = vehicle_vin
        est.vehicle_make = vehicle_make
        est.vehicle_model = vehicle_model
        est.estimated_appointment_date = estimated_appointment_date
        est.estimated_appointment_time = estimated_appointment_time
        est.labor_cost = labor
        est.materials_cost = mat
        est.misc_cost = misc
        est.subtotal = subtotal
        est.tax = tax_total
        est.total = total_amount
        est.alt_contact_name = alt_full_name
        est.alt_contact_phone = alt_phone
        est.alt_contact_relation = alt_relationship
        est.mobile_fee_override = (mobile_fee_override == "true")
        
        db.query(EstimateDetail).filter(EstimateDetail.estimate_id == target_id).delete()
        db.commit()

    tax_list = is_taxable if is_taxable else []
    
    for i in range(len(product_name)):
        is_tax = "on" in str(tax_list[i]) if i < len(tax_list) else False
        
        new_detail = EstimateDetail(
            estimate_id=target_id,
            product_name=product_name[i],
            description=description[i],
            quantity=quantity[i],
            cost=cost[i],
            price=price[i],
            is_taxable=is_tax,
            tax_amount=tax_amount[i],
            part_number=product_name[i],
            supplier=None
        )
        db.add(new_detail)
    
    db.commit()
    
    resolved_origin = origin or (request.query_params.get("origin") if request else None)
    origin_param = f"?origin={resolved_origin}" if resolved_origin else ""
    
    return RedirectResponse(url=f"/estimates/after_save/{target_id}{origin_param}", status_code=303)


# ============================================================
# 4. VOID ESTIMATE
# ============================================================
@router.post("/void/{estimate_id}")
def void_estimate(
    estimate_id: int,
    request: Request,
    reason: str = Form(...),
    db: Session = Depends(get_db)
):
    estimate = db.query(Estimate).filter(Estimate.id == estimate_id).first()
    if not estimate:
        raise HTTPException(status_code=404, detail="El estimado no existe.")

    if estimate.status in ["Void", "Voided"]:
        raise HTTPException(status_code=400, detail="Este estimado ya se encuentra anulado.")

    if estimate.invoice_number:
        raise HTTPException(status_code=400, detail="No se puede anular un estimado que ya ha sido facturado.")

    current_username = request.session.get("username") or "System"

    estimate.status = "Void"
    estimate.void_reason = reason
    estimate.voided_at = datetime.utcnow()
    estimate.voided_by = current_username

    db.commit()

    return RedirectResponse(url=f"/estimates/after_save/{estimate_id}", status_code=303)


# ==============================================================================
# POWERCORE - DUPLICATE ESTIMATE FEATURE
# ==============================================================================
@router.get("/duplicate/{estimate_id}")
def duplicate_estimate(
    estimate_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    original_estimate = db.query(Estimate).filter(Estimate.id == estimate_id).first()
    if not original_estimate:
        raise HTTPException(status_code=404, detail="Estimate not found for duplication.")

    current_username = request.session.get("username") or "System"

    new_estimate = Estimate(
        customer_id=original_estimate.customer_id,
        service_type=original_estimate.service_type,
        vehicle_year_id=original_estimate.vehicle_year_id,
        vehicle_vin=original_estimate.vehicle_vin,
        vehicle_make=original_estimate.vehicle_make,
        vehicle_model=original_estimate.vehicle_model,
        estimated_appointment_date=original_estimate.estimated_appointment_date,
        estimated_appointment_time=original_estimate.estimated_appointment_time,
        labor_cost=original_estimate.labor_cost,
        materials_cost=original_estimate.materials_cost,
        misc_cost=original_estimate.misc_cost,
        subtotal=original_estimate.subtotal,
        tax=original_estimate.tax,
        total=original_estimate.total,
        alt_contact_name=original_estimate.alt_contact_name,
        alt_contact_phone=original_estimate.alt_contact_phone,
        alt_contact_relation=original_estimate.alt_contact_relation,
        mobile_fee_override=original_estimate.mobile_fee_override,
        status="Estimate",
        operator_username=current_username
    )
    db.add(new_estimate)
    db.commit()
    db.refresh(new_estimate)
    new_target_id = new_estimate.id

    original_details = db.query(EstimateDetail).filter(EstimateDetail.estimate_id == estimate_id).all()
    for detail in original_details:
        new_detail = EstimateDetail(
            estimate_id=new_target_id,
            product_name=detail.product_name,
            description=detail.description,
            quantity=detail.quantity,
            cost=detail.cost,
            price=detail.price,
            is_taxable=detail.is_taxable,
            tax_amount=detail.tax_amount,
            part_number=detail.part_number,
            supplier=detail.supplier
        )
        db.add(new_detail)

    db.commit()

    return RedirectResponse(url=f"/estimates/edit/{new_target_id}?origin=estimate_edit", status_code=303)