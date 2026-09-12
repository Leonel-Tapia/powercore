# RUTA: app/routers/invoices/technician_routes.py
# CREADO: 2026-09-04
# ACTUALIZADO: 2026-09-12 - Agregado endpoint /daily-closing (reporte de cierre del técnico)

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, datetime
from typing import Optional
from app.database.database import get_db
from app.models.invoices.invoice_model import Invoice
from app.models.invoices.invoice_payment_model import InvoicePayment
from app.models.customers.customer_model import Customer
from app.core.template_loader import jinja as templates

router = APIRouter(prefix="/technician", tags=["Technician"])

# Orden fijo para mostrar métodos de pago
PAYMENT_METHODS_ORDER = [
    "CASH",
    "CREDIT_CARD",
    "DEBIT_CARD",
    "CHECK",
    "TRANSFER",
    "ZELLE",
    "OTHER",
]

# Etiquetas legibles
PAYMENT_METHOD_LABELS = {
    "CASH": "Cash",
    "CREDIT_CARD": "Credit Card",
    "DEBIT_CARD": "Debit Card",
    "CHECK": "Check",
    "TRANSFER": "Transfer",
    "ZELLE": "Zelle",
    "OTHER": "Other",
}


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


# ============================================================
# DAILY CLOSING REPORT (para técnico)
# ============================================================
@router.get("/daily-closing", response_class=HTMLResponse)
def technician_daily_closing(
    request: Request,
    selected_date: Optional[str] = None,
    service_type: Optional[str] = "MOVIL",
    db: Session = Depends(get_db)
):
    """
    Reporte de cierre diario para el técnico logueado.
    Filtra por fecha de PAGO (payment_date) y por tipo de servicio (MOVIL / SHOP).
    Muestra únicamente pagos con status DEPOSITED o PENDING.
    """
    # 1. Validar sesión
    user_id = request.session.get("user_id")
    user_role = request.session.get("role")

    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    if user_role != "technician":
        return RedirectResponse(url="/company/main_menu", status_code=303)

    # 2. Parsear fecha (default = hoy)
    if selected_date:
        try:
            target_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
        except ValueError:
            target_date = date.today()
    else:
        target_date = date.today()

    # 3. Normalizar tipo de servicio
    service_type_clean = (service_type or "MOVIL").strip().upper()

    # 4. Query: pagos del técnico logueado en la fecha y tipo de servicio indicados
    query = (
        db.query(
            InvoicePayment.id,
            InvoicePayment.invoice_id,
            InvoicePayment.payment_type,
            InvoicePayment.amount,
            InvoicePayment.reference,
            InvoicePayment.payment_date,
            InvoicePayment.payment_status,
            InvoicePayment.created_by,
            Customer.name.label("customer_name"),
        )
        .join(Invoice, InvoicePayment.invoice_id == Invoice.id)
        .join(Customer, Invoice.customer_id == Customer.id)
        .filter(InvoicePayment.payment_date == target_date)
        .filter(Invoice.technician_id == user_id)
        .filter(InvoicePayment.payment_status.in_(["DEPOSITED", "PENDING"]))
    )

    # Filtro por tipo de servicio (MOVIL o SHOP)
    if service_type_clean == "SHOP":
        query = query.filter(Invoice.service_type == "SHOP")
    else:
        # MOVIL: acepta variantes que existen en la BD
        query = query.filter(Invoice.service_type.in_(["MOVIL", "MOBILE", "Mobile", "mobile", "Movil"]))

    payments = query.order_by(InvoicePayment.id.asc()).all()

    # 5. Calcular totales por método de pago
    totals_by_method = {m: 0.0 for m in PAYMENT_METHODS_ORDER}
    for p in payments:
        method = (p.payment_type or "OTHER").strip().upper()
        if method not in totals_by_method:
            totals_by_method[method] = 0.0
        totals_by_method[method] += float(p.amount or 0)

    grand_total = sum(totals_by_method.values())

    # 6. Nombre del técnico
    technician_name = request.session.get("user_name", "Technician")

    return templates.TemplateResponse(
        request=request,
        name="invoices/technician_daily_closing.html",
        context={
            "technician_name": technician_name,
            "selected_date": target_date.strftime("%Y-%m-%d"),
            "target_date": target_date,
            "service_type": "SHOP" if service_type_clean == "SHOP" else "MOVIL",
            "payments": payments,
            "totals_by_method": totals_by_method,
            "grand_total": grand_total,
            "method_labels": PAYMENT_METHOD_LABELS,
            "method_order": PAYMENT_METHODS_ORDER,
            "today": date.today(),
        }
    )