# RUTA: app/routers/invoices/technician_routes.py
# CREADO: 2026-09-04
# ACTUALIZADO: 2026-09-04 - Agregado nombre y dirección del cliente

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
from app.database.database import get_db
from app.models.invoices.invoice_model import Invoice
from app.models.customers.customer_model import Customer
from app.core.template_loader import jinja as templates

router = APIRouter(prefix="/technician", tags=["Technician"])


@router.get("/dashboard", response_class=HTMLResponse)
def technician_dashboard(request: Request, db: Session = Depends(get_db)):
    # Verificar que el usuario esté autenticado y sea técnico
    user_id = request.session.get("user_id")
    user_role = request.session.get("role")

    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    if user_role != "technician":
        return RedirectResponse(url="/company/main_menu", status_code=303)

    # Obtener la fecha actual como objeto Python date
    today = date.today()

    # Obtener las citas del día para este técnico con JOIN a customers
    invoices = (
        db.query(
            Invoice.id,
            Invoice.estimated_appointment_time,
            Invoice.service_type,
            Customer.name.label("customer_name"),
            Customer.address.label("customer_address"),
            Invoice.vehicle_make,
            Invoice.vehicle_model,
            Invoice.total,
            Invoice.payment_status,
            Invoice.payment_amount1,
            Invoice.payment_amount2,
            (Invoice.total - func.coalesce(Invoice.payment_amount1, 0) - func.coalesce(Invoice.payment_amount2, 0)).label("balance")
        )
        .join(Customer, Invoice.customer_id == Customer.id)
        .filter(Invoice.technician_id == user_id)
        .filter(Invoice.date_request == today)
        .order_by(Invoice.estimated_appointment_time.asc())
        .all()
    )

    # Obtener el nombre del técnico
    technician_name = request.session.get("user_name", "Técnico")

    return templates.TemplateResponse(
        request=request,
        name="invoices/technician_dashboard.html",
        context={
            "technician_name": technician_name,
            "invoices": invoices,
            "today": today
        }
    )