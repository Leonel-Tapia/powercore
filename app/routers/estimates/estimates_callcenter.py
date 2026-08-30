# /app/routers/estimates/estimates_callcenter.py | Updated: 2026-08-21

from datetime import date, datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.template_loader import jinja as templates
from app.database.database import get_db
from app.models.call_center.estimate_history_model import EstimatesHistory
from app.models.customers.customer_model import Customer
from app.models.estimates.estimate_model import Estimate
from app.models.inventory.year_model import Year
from app.models.invoices.invoice_model import Invoice, InvoiceItem

router = APIRouter(prefix="/call_center", tags=["call_center"])


class EstimateHistoryCreate(BaseModel):
    estimate_id: int
    action_type: str
    message: Optional[str] = None
    created_by: str


def format_time_12hr(time_obj):
    if not time_obj:
        return "N/A"
    if hasattr(time_obj, "strftime"):
        return time_obj.strftime("%I:%M %p")
    try:
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                parsed_time = datetime.strptime(str(time_obj), fmt)
                return parsed_time.strftime("%I:%M %p")
            except ValueError:
                continue
    except Exception:
        pass
    return str(time_obj)


def clone_estimate_items_to_invoice(estimate, new_invoice):
    """Función auxiliar para clonar los ítems del estimado a la factura"""
    estimate_items = getattr(estimate, "items", None) or getattr(estimate, "details", [])
    for est_item in estimate_items:
        invoice_item = InvoiceItem(
            product_name=getattr(est_item, "product_name", getattr(est_item, "name", "Glass Service")),
            description=getattr(est_item, "description", None),
            quantity=getattr(est_item, "quantity", 1),
            part_number=getattr(est_item, "part_number", None),
            supplier=getattr(est_item, "supplier", None),
            cost=getattr(est_item, "cost", 0.0),
            price=getattr(est_item, "price", getattr(est_item, "unit_price", 0.0)),
            is_taxable=getattr(est_item, "is_taxable", True),
            tax_amount=getattr(est_item, "tax_amount", 0.0)
        )
        new_invoice.items.append(invoice_item)


# ============================================================
# 1. DAILY ESTIMATES / APPOINTMENTS PENDING CONFIRMATION VIEW
# ============================================================
@router.get("/daily_estimates", response_class=HTMLResponse)
def daily_estimates_view(
    request: Request,
    selected_date: Optional[str] = None,
    service_type: Optional[str] = "all",
    db: Session = Depends(get_db),
):
    if selected_date:
        try:
            target_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
        except ValueError:
            target_date = date.today()
    else:
        target_date = date.today()

    day_name = target_date.strftime("%A")
    today_date_str = date.today().strftime("%Y-%m-%d")

    base_query = (
        db.query(Estimate, Customer, Year)
        .outerjoin(Customer, Estimate.customer_id == Customer.id)
        .outerjoin(Year, Estimate.vehicle_year_id == Year.id)
        .filter(Estimate.estimated_appointment_date == target_date)
    )

    all_day_records = base_query.all()

    total_estimates = len(all_day_records)
    shop_count = sum(
        1
        for est, _, _ in all_day_records
        if est.service_type and est.service_type.lower() == "shop"
    )
    mobile_count = sum(
        1
        for est, _, _ in all_day_records
        if est.service_type and est.service_type.lower() in ["mobile", "movil"]
    )

    estimates_query = base_query
    if service_type and service_type != "all":
        st_lower = service_type.lower()
        if st_lower == "movil" or st_lower == "mobile":
           estimates_query = estimates_query.filter(
                or_(
                    func.lower(Estimate.service_type) == "mobile",
                    func.lower(Estimate.service_type) == "movil",
                )
            )
        elif st_lower == "shop":
            estimates_query = estimates_query.filter(
                func.lower(Estimate.service_type) == "shop"
            )

    estimates_query = estimates_query.order_by(
        Estimate.estimated_appointment_time.asc()
    ).all()

    formatted_estimates = []
    for estimate, customer, vehicle_year in estimates_query:
        formatted_time = format_time_12hr(estimate.estimated_appointment_time)

        resolved_customer = customer
        if not resolved_customer and getattr(estimate, "customer_id", None):
            resolved_customer = (
                db.query(Customer).filter(Customer.id == estimate.customer_id).first()
            )

        if not resolved_customer and getattr(estimate, "customer_phone", None):
            resolved_customer = (
                db.query(Customer).filter(Customer.phone == estimate.customer_phone).first()
            )

        customer_name = "Unknown"
        if resolved_customer and getattr(resolved_customer, "name", None):
            customer_name = resolved_customer.name
        elif resolved_customer and getattr(resolved_customer, "full_name", None):
            customer_name = resolved_customer.full_name
        elif getattr(estimate, "customer_name", None):
            customer_name = estimate.customer_name

        formatted_estimates.append(
            (estimate, resolved_customer, formatted_time, customer_name, vehicle_year)
        )

    return templates.TemplateResponse(
        request=request,
        name="estimates/estimates_pending_confirmation.html",
        context={
            "estimates_data": formatted_estimates,
            "selected_date": target_date.strftime("%Y-%m-%d"),
            "today_date": today_date_str,
            "day_name": day_name,
            "service_type": service_type or "all",
            "total_estimates": total_estimates,
            "shop_count": shop_count,
            "mobile_count": mobile_count,
        },
    )


# ============================================================
# 2. CONFIRM ESTIMATE APPOINTMENT (POST)
# ============================================================
@router.post("/confirm_appointment/{estimate_id}")
def confirm_appointment(
    estimate_id: int,
    request: Request,
    redirect_date: Optional[str] = Form(None),
    service_type: Optional[str] = Form("all"),
    db: Session = Depends(get_db),
):
    estimate = db.query(Estimate).filter(Estimate.id == estimate_id).first()
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found.")

    today = date.today()
    if (
        estimate.estimated_appointment_date
        and estimate.estimated_appointment_date < today
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot confirm an estimate with a past date. You must edit the"
                " estimate and update the appointment date."
            ),
        )

    current_username = request.session.get("username") or "System"

    estimate.status = "Confirmed"
    estimate.authorized_by = current_username
    estimate.auth_date_time = datetime.now()

    new_history = EstimatesHistory(
        estimate_id=estimate_id,
        action_type="Confirmed",
        message=(
            f"Appointment confirmed for {estimate.estimated_appointment_date}"
            f" {format_time_12hr(estimate.estimated_appointment_time)}."
        ),
        created_by=current_username,
        created_at=datetime.now(),
    )
    db.add(new_history)

    existing_invoice = db.query(Invoice).filter(Invoice.estimate_id == estimate_id).first()
    if not existing_invoice:
        new_invoice = Invoice(
            estimate_id=estimate_id,
            customer_id=estimate.customer_id,
            vehicle_year_id=getattr(estimate, "vehicle_year_id", None),
            vehicle_vin=getattr(estimate, "vehicle_vin", None),
            vehicle_make=getattr(estimate, "vehicle_make", None),
            vehicle_model=getattr(estimate, "vehicle_model", None),
            glass_type=getattr(estimate, "glass_type", None),
            window_position=getattr(estimate, "window_position", None),
            service_type=getattr(estimate, "service_type", None),
            customer_address=getattr(estimate, "customer_address", None),
            estimated_appointment_date=getattr(estimate, "estimated_appointment_date", None),
            estimated_appointment_time=getattr(estimate, "estimated_appointment_time", None),
            operator_username=getattr(estimate, "operator_username", None),
            language=getattr(estimate, "language", "English"),
            subtotal=getattr(estimate, "subtotal", 0.0),
            tax=getattr(estimate, "tax", 0.0),
            total=getattr(estimate, "total", 0.0),
            labor_cost=getattr(estimate, "labor_cost", 0.0),
            materials_cost=getattr(estimate, "materials_cost", 0.0),
            misc_cost=getattr(estimate, "misc_cost", 0.0),
            mobile_fee_override=getattr(estimate, "mobile_fee_override", False),
            special_discount=getattr(estimate, "special_discount", 0.0),
            special_discount_reason=getattr(estimate, "special_discount_reason", None),
            alt_contact_name=getattr(estimate, "alt_contact_name", None),
            alt_contact_phone=getattr(estimate, "alt_contact_phone", None),
            alt_contact_relation=getattr(estimate, "alt_contact_relation", None),
            payment_status=getattr(estimate, "payment_status", "PENDING"),
            notes=getattr(estimate, "notes", None),
            status="PENDING",
            created_by=current_username,
            created_at=datetime.now(),
            authorized_by=current_username,
            auth_date_time=datetime.now(),
        )
        clone_estimate_items_to_invoice(estimate, new_invoice)
        db.add(new_invoice)
        db.flush()  # <-- obtener ID generado

        # Guardar número de invoice (ID autonumérico)
        estimate.invoice_number = new_invoice.id

    db.commit()

    redirect_url = "/call_center/daily_estimates?service_type=all"
    if redirect_date:
        redirect_url += f"&selected_date={redirect_date}"

    return RedirectResponse(url=redirect_url, status_code=303)


# ============================================================
# 3. ESTIMATE HISTORY / AUDIT API ENDPOINTS
# ============================================================
@router.post("/estimates/history", status_code=status.HTTP_201_CREATED)
def create_estimate_history(
    data: EstimateHistoryCreate, db: Session = Depends(get_db)
):
    new_history = EstimatesHistory(
        estimate_id=data.estimate_id,
        action_type=data.action_type,
        message=data.message,
        created_by=data.created_by,
        created_at=datetime.now(),
    )
    db.add(new_history)

    if data.action_type == "Confirmed":
        estimate = db.query(Estimate).filter(Estimate.id == data.estimate_id).first()
        if estimate:
            estimate.status = "Confirmed"
            estimate.authorized_by = data.created_by
            estimate.auth_date_time = datetime.now()
            
            existing_invoice = db.query(Invoice).filter(Invoice.estimate_id == data.estimate_id).first()
            if not existing_invoice:
                new_invoice = Invoice(
                    estimate_id=data.estimate_id,
                    customer_id=estimate.customer_id,
                    vehicle_year_id=getattr(estimate, "vehicle_year_id", None),
                    vehicle_vin=getattr(estimate, "vehicle_vin", None),
                    vehicle_make=getattr(estimate, "vehicle_make", None),
                    vehicle_model=getattr(estimate, "vehicle_model", None),
                    glass_type=getattr(estimate, "glass_type", None),
                    window_position=getattr(estimate, "window_position", None),
                    service_type=getattr(estimate, "service_type", None),
                    customer_address=getattr(estimate, "customer_address", None),
                    estimated_appointment_date=getattr(estimate, "estimated_appointment_date", None),
                    estimated_appointment_time=getattr(estimate, "estimated_appointment_time", None),
                    operator_username=getattr(estimate, "operator_username", None),
                    language=getattr(estimate, "language", "English"),
                    subtotal=getattr(estimate, "subtotal", 0.0),
                    tax=getattr(estimate, "tax", 0.0),
                    total=getattr(estimate, "total", 0.0),
                    labor_cost=getattr(estimate, "labor_cost", 0.0),
                    materials_cost=getattr(estimate, "materials_cost", 0.0),
                    misc_cost=getattr(estimate, "misc_cost", 0.0),
                    mobile_fee_override=getattr(estimate, "mobile_fee_override", False),
                    special_discount=getattr(estimate, "special_discount", 0.0),
                    special_discount_reason=getattr(estimate, "special_discount_reason", None),
                    alt_contact_name=getattr(estimate, "alt_contact_name", None),
                    alt_contact_phone=getattr(estimate, "alt_contact_phone", None),
                    alt_contact_relation=getattr(estimate, "alt_contact_relation", None),
                    payment_status=getattr(estimate, "payment_status", "PENDING"),
                    notes=getattr(estimate, "notes", None),
                    status="PENDING",
                    created_by=data.created_by,
                    created_at=datetime.now(),
                    authorized_by=data.created_by,
                    auth_date_time=datetime.now(),
                )
                clone_estimate_items_to_invoice(estimate, new_invoice)
                db.add(new_invoice)
                db.flush()  # <-- obtener ID generado

                # Guardar número de invoice (ID autonumérico)
                estimate.invoice_number = new_invoice.id

    db.commit()
    db.refresh(new_history)

    return {
        "success": True,
        "message": "History recorded successfully.",
        "id": new_history.id,
    }


@router.get("/estimates/{estimate_id}/history")
def get_estimate_history(estimate_id: int, db: Session = Depends(get_db)):
    history_records = (
        db.query(EstimatesHistory)
        .filter(EstimatesHistory.estimate_id == estimate_id)
        .order_by(EstimatesHistory.created_at.desc())
        .all()
    )
    return history_records


# ============================================================
# 4. CONFIRM APPOINTMENT MODAL (POST)
# ============================================================
@router.post("/confirm_appointment_modal")
def confirm_appointment_modal(
    estimate_id: int = Form(...),
    action_type: str = Form(...),
    message: Optional[str] = Form(None),
    request: Request = None,
    db: Session = Depends(get_db),
):
    estimate = db.query(Estimate).filter(Estimate.id == estimate_id).first()
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found.")

    current_username = request.session.get("username") or "System"

    estimate.status = action_type
    if action_type == "Confirmed":
        estimate.authorized_by = current_username
        estimate.auth_date_time = datetime.now()

        existing_invoice = db.query(Invoice).filter(Invoice.estimate_id == estimate_id).first()
        if not existing_invoice:
            new_invoice = Invoice(
                estimate_id=estimate_id,
                customer_id=estimate.customer_id,
                vehicle_year_id=getattr(estimate, "vehicle_year_id", None),
                vehicle_vin=getattr(estimate, "vehicle_vin", None),
                vehicle_make=getattr(estimate, "vehicle_make", None),
                vehicle_model=getattr(estimate, "vehicle_model", None),
                glass_type=getattr(estimate, "glass_type", None),
                window_position=getattr(estimate, "window_position", None),
                service_type=getattr(estimate, "service_type", None),
                customer_address=getattr(estimate, "customer_address", None),
                estimated_appointment_date=getattr(estimate, "estimated_appointment_date", None),
                estimated_appointment_time=getattr(estimate, "estimated_appointment_time", None),
                operator_username=getattr(estimate, "operator_username", None),
                language=getattr(estimate, "language", "English"),
                subtotal=getattr(estimate, "subtotal", 0.0),
                tax=getattr(estimate, "tax", 0.0),
                total=getattr(estimate, "total", 0.0),
                labor_cost=getattr(estimate, "labor_cost", 0.0),
                materials_cost=getattr(estimate, "materials_cost", 0.0),
                misc_cost=getattr(estimate, "misc_cost", 0.0),
                mobile_fee_override=getattr(estimate, "mobile_fee_override", False),
                special_discount=getattr(estimate, "special_discount", 0.0),
                special_discount_reason=getattr(estimate, "special_discount_reason", None),
                alt_contact_name=getattr(estimate, "alt_contact_name", None),
                alt_contact_phone=getattr(estimate, "alt_contact_phone", None),
                alt_contact_relation=getattr(estimate, "alt_contact_relation", None),
                payment_status=getattr(estimate, "payment_status", "PENDING"),
                notes=getattr(estimate, "notes", None),
                status="PENDING",
                created_by=current_username,
                created_at=datetime.now(),
                authorized_by=current_username,
                auth_date_time=datetime.now(),
            )
            clone_estimate_items_to_invoice(estimate, new_invoice)
            db.add(new_invoice)
            db.flush()  # <-- obtener ID generado

            # Guardar número de invoice (ID autonumérico)
            estimate.invoice_number = new_invoice.id

    new_history = EstimatesHistory(
        estimate_id=estimate_id,
        action_type=action_type,
        message=message or f"Status updated to: {action_type}",
        created_by=current_username,
        created_at=datetime.now(),
    )
    db.add(new_history)
    db.commit()

    referer = request.headers.get("referer", "/call_center/daily_estimates")
    if "/call_center/daily_estimates" in referer:
        return RedirectResponse(url=referer, status_code=303)

    target_date_str = (
        estimate.estimated_appointment_date.strftime("%Y-%m-%d")
        if estimate.estimated_appointment_date
        else date.today().strftime("%Y-%m-%d")
    )
    return RedirectResponse(
        url=f"/call_center/daily_estimates?selected_date={target_date_str}&service_type=all",
        status_code=303,
    )
