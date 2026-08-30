# /app/routers/invoices/invoices_router.py | Updated: 2026-08-26
from fastapi import APIRouter, Request, Depends, Form, HTTPException, Path, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, desc
from datetime import datetime, date
from typing import List, Optional
from decimal import Decimal
from app.database.database import get_db
from app.core.template_loader import jinja as templates

from app.models.invoices.invoice_model import Invoice, InvoiceItem
from app.models.invoices.invoice_payment_model import InvoicePayment
from app.models.invoices.invoice_activity_model import Concept, InvoiceActivity
from app.models.estimates.estimate_model import Estimate, EstimateDetail
from app.models.customers.customer_model import Customer
from app.models.inventory.year_model import Year
from app.models.inventory.time_model import TimeCatalog
from app.models.company.company import Company

router = APIRouter(
    prefix="/invoices",
    tags=["invoices"]
)

# ============================================================
# 1. VIEW INVOICE (TEMPLATE RENDER)
# ============================================================
@router.get("/view/{invoice_id}", response_class=HTMLResponse)
def view_invoice(
    invoice_id: int, 
    request: Request, 
    return_url: Optional[str] = None,
    selected_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        return RedirectResponse("/customers/list", status_code=303)

    customer = db.query(Customer).filter(Customer.id == invoice.customer_id).first()
    invoice_items = db.query(InvoiceItem).filter(InvoiceItem.invoice_id == invoice_id).all()
    
    years = db.query(Year).order_by(Year.year.desc()).all()
    times = db.query(TimeCatalog).order_by(TimeCatalog.time_value.asc()).all()
    company = db.query(Company).first()

    # Obtener pagos del invoice
    payments = db.query(InvoicePayment).filter(
        InvoicePayment.invoice_id == invoice_id
    ).order_by(desc(InvoicePayment.payment_date)).all()
    
    # Calcular total pagado
    total_paid = sum(p.amount for p in payments if p.payment_status in ["DEPOSITED", "PENDING"])
    balance_due = float(invoice.total or 0) - float(total_paid)

    # Obtener actividades del invoice
    activities = db.query(InvoiceActivity).filter(
        InvoiceActivity.invoice_id == invoice_id
    ).order_by(desc(InvoiceActivity.created_at)).all()

    return templates.TemplateResponse(
        request=request,
        name="invoices/invoice_view.html",
        context={
            "customer": customer,
            "invoice": invoice,
            "invoice_items": invoice_items,
            "years": years,
            "times": times,
            "company": company,
            "return_url": return_url,
            "selected_date": selected_date,
            "payments": payments,
            "total_paid": float(total_paid),
            "balance_due": balance_due,
            "activities": activities
        }
    )


# ============================================================
# 2. GENERATE / CLONE INVOICE FROM ESTIMATE (POST)
# ============================================================
@router.post("/generate/{estimate_id}")
def generate_invoice_from_estimate(
    estimate_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    estimate = db.query(Estimate).filter(Estimate.id == estimate_id).first()
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found for invoice generation.")

    existing_invoice = db.query(Invoice).filter(Invoice.estimate_id == estimate_id).first()
    if existing_invoice:
        return RedirectResponse(url=f"/invoices/view/{existing_invoice.id}", status_code=303)

    current_username = request.session.get("username") or "System"

    new_invoice = Invoice(
        estimate_id=estimate.id,
        customer_id=estimate.customer_id,
        vehicle_year_id=estimate.vehicle_year_id,
        vehicle_vin=estimate.vehicle_vin,
        vehicle_make=estimate.vehicle_make,
        vehicle_model=estimate.vehicle_model,
        glass_type=estimate.glass_type,
        window_position=estimate.window_position,
        service_type=estimate.service_type,
        customer_address=estimate.customer_address,
        date_request=estimate.date_request,
        estimated_appointment_date=estimate.estimated_appointment_date,
        estimated_appointment_time=estimate.estimated_appointment_time,
        operator_username=current_username,
        authorized_by=estimate.authorized_by,
        auth_date_time=estimate.auth_date_time,
        status="PENDING",
        invoice_number=f"INV-{estimate.id}",
        language=estimate.language,
        subtotal=estimate.subtotal,
        tax=estimate.tax,
        total=estimate.total,
        labor_cost=estimate.labor_cost,
        materials_cost=estimate.materials_cost,
        misc_cost=estimate.misc_cost,
        mobile_fee_override=estimate.mobile_fee_override,
        special_discount=estimate.special_discount,
        special_discount_reason=estimate.special_discount_reason,
        alt_contact_name=estimate.alt_contact_name,
        alt_contact_phone=estimate.alt_contact_phone,
        alt_contact_relation=estimate.alt_contact_relation,
        payment_method1=estimate.payment_method1,
        payment_amount1=estimate.payment_amount1,
        payment_method2=estimate.payment_method2,
        payment_amount2=estimate.payment_amount2,
        payment_status=estimate.payment_status or "PENDING",
        notes=estimate.notes
    )
    
    db.add(new_invoice)
    db.commit()
    db.refresh(new_invoice)
    target_id = new_invoice.id

    estimate.invoice_number = new_invoice.invoice_number
    db.commit()

    estimate_details = db.query(EstimateDetail).filter(EstimateDetail.estimate_id == estimate_id).all()
    for detail in estimate_details:
        new_item = InvoiceItem(
            invoice_id=target_id,
            product_name=detail.product_name,
            description=detail.description,
            quantity=detail.quantity,
            part_number=detail.part_number,
            supplier=detail.supplier,
            cost=detail.cost,
            price=detail.price,
            is_taxable=detail.is_taxable,
            tax_amount=detail.tax_amount,
            is_received=detail.is_received,
            received_by=detail.received_by,
            received_at=detail.received_at
        )
        db.add(new_item)

    db.commit()

    return RedirectResponse(url=f"/invoices/view/{target_id}", status_code=303)


# ============================================================
# 3. UPDATE INVOICE (POST)
# ============================================================
@router.post("/update/{invoice_id}")
def update_invoice(
    invoice_id: int = Path(...),
    request: Request = None,
    return_url: Optional[str] = Form(None),
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
    target_id = invoice_id
    inv = db.query(Invoice).filter(Invoice.id == target_id).first()
    
    if inv:
        inv.service_type = service_type
        inv.vehicle_year_id = vehicle_year_id
        inv.vehicle_vin = vehicle_vin
        inv.vehicle_make = vehicle_make
        inv.vehicle_model = vehicle_model
        inv.estimated_appointment_date = estimated_appointment_date
        inv.estimated_appointment_time = estimated_appointment_time
        inv.labor_cost = labor
        inv.materials_cost = mat
        inv.misc_cost = misc
        inv.subtotal = subtotal
        inv.tax = tax_total
        inv.total = total_amount
        inv.alt_contact_name = alt_full_name
        inv.alt_contact_phone = alt_phone
        inv.alt_contact_relation = alt_relationship
        inv.mobile_fee_override = (mobile_fee_override == "true")
        
        db.query(InvoiceItem).filter(InvoiceItem.invoice_id == target_id).delete()
        db.commit()

    tax_list = is_taxable if is_taxable else []
    
    for i in range(len(product_name)):
        is_tax = "on" in str(tax_list[i]) if i < len(tax_list) else False
        
        new_item = InvoiceItem(
            invoice_id=target_id,
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
        db.add(new_item)
    
    db.commit()
    
    # Redirigir a return_url si existe, si no a la vista del invoice
    if return_url:
        return RedirectResponse(url=return_url, status_code=303)
    else:
        return RedirectResponse(url=f"/invoices/view/{target_id}", status_code=303)


# ============================================================
# 4. VOID INVOICE
# ============================================================
@router.post("/void/{invoice_id}")
def void_invoice(
    invoice_id: int,
    request: Request,
    reason: str = Form(...),
    return_url: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="La factura no existe.")

    if invoice.status in ["Void", "Voided"]:
        raise HTTPException(status_code=400, detail="Esta factura ya se encuentra anulada.")

    current_username = request.session.get("username") or "System"

    invoice.status = "Void"
    invoice.void_reason = reason
    invoice.voided_at = datetime.utcnow()
    invoice.voided_by = current_username

    db.commit()

    if return_url:
        return RedirectResponse(url=return_url, status_code=303)
    else:
        return RedirectResponse(url=f"/invoices/view/{invoice_id}", status_code=303)


# ============================================================
# 5. GET INVOICE HISTORY BY CUSTOMER ID (AJAX)
# ============================================================
@router.get("/history/{customer_id}")
def get_invoice_history(
    customer_id: int,
    db: Session = Depends(get_db)
):
    """
    Retorna el historial de facturas para un cliente específico.
    Incluye: lista de invoices + totales desglosados por estado.
    """
    invoices = db.query(Invoice).filter(
        Invoice.customer_id == customer_id
    ).order_by(Invoice.id.desc()).all()
    
    result = []
    total_general = 0.0
    total_pending = 0.0
    total_paid = 0.0
    
    for inv in invoices:
        # Obtener el año desde la tabla years usando vehicle_year_id
        year_value = None
        if inv.vehicle_year_id:
            year_record = db.query(Year).filter(Year.id == inv.vehicle_year_id).first()
            if year_record:
                year_value = year_record.year
        
        total = float(inv.total) if inv.total else 0.0
        total_general += total
        
        status_upper = (inv.status or "PENDING").upper()
        if status_upper in ["PAID", "COMPLETED", "PAGADO"]:
            total_paid += total
        else:
            total_pending += total
        
        result.append({
            "id": inv.id,
            "invoice_number": inv.invoice_number or f"INV-{inv.id}",
            "estimate_id": inv.estimate_id,
            "year": year_value,
            "make": inv.vehicle_make or "",
            "model": inv.vehicle_model or "",
            "total": total,
            "service_type": inv.service_type or "",
            "status": inv.status or "PENDING",
            "operator": inv.operator_username or "",
            "date": inv.time_created.strftime("%Y-%m-%d") if inv.time_created else (
                inv.date_request.strftime("%Y-%m-%d") if inv.date_request else None
            )
        })
    
    return JSONResponse(content={
        "invoices": result,
        "totals": {
            "general": total_general,
            "pending": total_pending,
            "paid": total_paid
        }
    })


# ============================================================
# 6. GET INVOICE DETAILS (para Details button - opcional)
# ============================================================
@router.get("/details/{invoice_id}")
def get_invoice_details(
    invoice_id: int,
    db: Session = Depends(get_db)
):
    """
    Retorna los items de una factura específica.
    """
    items = db.query(InvoiceItem).filter(
        InvoiceItem.invoice_id == invoice_id
    ).all()
    
    result = []
    for item in items:
        result.append({
            "product_name": item.product_name,
            "price": float(item.price) if item.price else 0.0,
            "quantity": item.quantity or 1,
            "description": item.description or ""
        })
    
    return JSONResponse(content=result)


# ============================================================
# 7. SECCIÓN DE PAGOS - INVOICE PAYMENTS
# ============================================================

# ============================================================
# 7.1 OBTENER TODOS LOS PAGOS DE UN INVOICE
# ============================================================
@router.get("/{invoice_id}/payments")
async def get_invoice_payments(
    request: Request,
    invoice_id: int,
    db: Session = Depends(get_db)
):
    """Obtener todos los pagos de un invoice específico"""
    try:
        # Verificar que el invoice existe
        invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not invoice:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Invoice no encontrado"}
            )
        
        # Obtener pagos ordenados por fecha descendente
        payments = db.query(InvoicePayment).filter(
            InvoicePayment.invoice_id == invoice_id
        ).order_by(desc(InvoicePayment.payment_date)).all()
        
        # Calcular total pagado
        total_paid = sum(p.amount for p in payments if p.payment_status in ["DEPOSITED", "PENDING"])
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {
                    "payments": [p.to_dict() for p in payments],
                    "total_paid": float(total_paid),
                    "count": len(payments)
                }
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


# ============================================================
# 7.2 CREAR NUEVO PAGO
# ============================================================
@router.post("/{invoice_id}/payments")
async def create_invoice_payment(
    request: Request,
    invoice_id: int,
    db: Session = Depends(get_db)
):
    """Crear un nuevo pago para un invoice"""
    try:
        # Verificar que el invoice existe
        invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not invoice:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Invoice no encontrado"}
            )
        
        # Obtener datos del formulario
        form_data = await request.form()
        
        # Validar campos obligatorios
        payment_type = form_data.get("payment_type")
        amount_str = form_data.get("amount")
        payment_date_str = form_data.get("payment_date")
        
        if not payment_type:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "El tipo de pago es obligatorio"}
            )
        
        if not amount_str:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "El monto es obligatorio"}
            )
        
        try:
            amount = Decimal(amount_str)
            if amount <= 0:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "El monto debe ser mayor a 0"}
                )
        except:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Monto inválido"}
            )
        
        if not payment_date_str:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "La fecha de pago es obligatoria"}
            )
        
        try:
            payment_date = datetime.strptime(payment_date_str, "%Y-%m-%d").date()
        except:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Fecha inválida (formato YYYY-MM-DD)"}
            )
        
        # Obtener usuario de la sesión
        username = request.session.get("username") or request.session.get("user_name") or "system"
        
        # ============================================================
        # VALIDACIÓN: NO PERMITIR PAGO MAYOR AL BALANCE PENDIENTE
        # ============================================================
        # Calcular balance actual antes de crear el pago
        existing_payments = db.query(InvoicePayment).filter(
            InvoicePayment.invoice_id == invoice_id
        ).all()
        
        current_total_paid = sum(p.amount for p in existing_payments if p.payment_status in ["DEPOSITED", "PENDING"])
        balance_due = float(invoice.total or 0) - float(current_total_paid)
        
        # Validar que el pago no supere el balance
        if float(amount) > balance_due:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": f"El monto del pago (${float(amount):.2f}) excede el balance pendiente (${balance_due:.2f})"}
            )
        # ============================================================
        
        # Crear el pago
        new_payment = InvoicePayment(
            invoice_id=invoice_id,
            payment_type=payment_type,
            amount=amount,
            reference=form_data.get("reference", "").strip() or None,
            payment_date=payment_date,
            notes=form_data.get("notes", "").strip() or None,
            payment_status="PENDING",
            created_by=username
        )
        
        db.add(new_payment)
        db.commit()
        db.refresh(new_payment)
        
        # Actualizar payment_status del invoice si es necesario
        # Actualizar el total pagado y balance
        payments = db.query(InvoicePayment).filter(
            InvoicePayment.invoice_id == invoice_id
        ).all()
        
        total_paid = sum(p.amount for p in payments if p.payment_status in ["DEPOSITED", "PENDING"])
        balance_due = float(invoice.total or 0) - float(total_paid)
        
        # Si el balance es 0, marcar como PAID
        if balance_due <= 0:
            invoice.status = "PAID"              # ← Call Center ve PAID
            invoice.payment_status = "PENDING"   # ← Contabilidad ve PENDING
        elif total_paid > 0:
            invoice.status = "PARTIALLY_PAID"    # ← Call Center ve PARTIALLY_PAID
            invoice.payment_status = "PENDING"   # ← Contabilidad ve PENDING
        else:
            invoice.status = "PENDING"           # ← Call Center ve PENDING
            invoice.payment_status = "PENDING"   # ← Contabilidad ve PENDING
        
        db.commit()
        
        return JSONResponse(
            status_code=201,
            content={
                "success": True,
                "message": "Pago registrado exitosamente",
                "data": new_payment.to_dict()
            }
        )
        
    except Exception as e:
        db.rollback()
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


# ============================================================
# 7.3 ACTUALIZAR ESTADO DE UN PAGO
# ============================================================
@router.put("/payments/{payment_id}/status")
async def update_payment_status(
    request: Request,
    payment_id: int,
    db: Session = Depends(get_db)
):
    """Actualizar el estado de un pago (DEPOSITED, BOUNCED, REJECTED, etc.)"""
    try:
        # Buscar el pago
        payment = db.query(InvoicePayment).filter(InvoicePayment.id == payment_id).first()
        if not payment:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Pago no encontrado"}
            )
        
        # Obtener datos del formulario
        form_data = await request.form()
        new_status = form_data.get("payment_status")
        
        if not new_status:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "El estado es obligatorio"}
            )
        
        # Validar estados permitidos
        allowed_statuses = ["DEPOSITED", "BOUNCED", "CANCELLED", "VOID", "REJECTED", "FAILED", "REFUNDED"]
        if new_status not in allowed_statuses:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": f"Estado inválido. Permitidos: {', '.join(allowed_statuses)}"}
            )
        
        # Obtener usuario de la sesión
        username = request.session.get("username") or request.session.get("user_name") or "system"
        
        # Actualizar según el estado
        if new_status == "DEPOSITED":
            payment.payment_status = "DEPOSITED"
            payment.deposited_at = datetime.now()
            payment.deposited_by = username
            
        elif new_status in ["BOUNCED", "REJECTED"]:
            reason = form_data.get("rejection_reason", "").strip()
            if not reason:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "La razón del rechazo es obligatoria"}
                )
            
            fee_str = form_data.get("fee_amount", "0")
            try:
                fee_amount = Decimal(fee_str) if fee_str else Decimal("0.00")
            except:
                fee_amount = Decimal("0.00")
            
            payment.payment_status = new_status
            payment.rejection_reason = reason
            payment.rejection_date = datetime.now()
            payment.rejected_by = username
            payment.fee_amount = fee_amount
            
        elif new_status == "CANCELLED":
            payment.payment_status = "CANCELLED"
            
        elif new_status == "VOID":
            payment.payment_status = "VOID"
            
        elif new_status == "FAILED":
            payment.payment_status = "FAILED"
            
        elif new_status == "REFUNDED":
            payment.payment_status = "REFUNDED"
        
        # Actualizar timestamp
        payment.updated_at = datetime.now()
        
        db.commit()
        db.refresh(payment)
        
        # Actualizar el invoice
        invoice = db.query(Invoice).filter(Invoice.id == payment.invoice_id).first()
        if invoice:
            payments = db.query(InvoicePayment).filter(
                InvoicePayment.invoice_id == invoice.id
            ).all()
            
            total_paid = sum(p.amount for p in payments if p.payment_status in ["DEPOSITED", "PENDING"])
            balance_due = float(invoice.total or 0) - float(total_paid)
            
            if balance_due <= 0:
                invoice.status = "PAID"              # ← Call Center ve PAID
                invoice.payment_status = "PENDING"   # ← Contabilidad ve PENDING
            elif total_paid > 0:
                invoice.status = "PARTIALLY_PAID"    # ← Call Center ve PARTIALLY_PAID
                invoice.payment_status = "PENDING"   # ← Contabilidad ve PENDING
            else:
                invoice.status = "PENDING"           # ← Call Center ve PENDING
                invoice.payment_status = "PENDING"   # ← Contabilidad ve PENDING
            
            db.commit()
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": f"Estado del pago actualizado a {new_status}",
                "data": payment.to_dict()
            }
        )
        
    except Exception as e:
        db.rollback()
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


# ============================================================
# 7.4 ELIMINAR UN PAGO (OPCIONAL)
# ============================================================
@router.delete("/payments/{payment_id}")
async def delete_payment(
    request: Request,
    payment_id: int,
    db: Session = Depends(get_db)
):
    """Eliminar un pago (solo si está PENDING o CANCELLED)"""
    try:
        payment = db.query(InvoicePayment).filter(InvoicePayment.id == payment_id).first()
        if not payment:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Pago no encontrado"}
            )
        
        # Solo permitir eliminar pagos PENDING o CANCELLED
        if payment.payment_status not in ["PENDING", "CANCELLED"]:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Solo se pueden eliminar pagos PENDING o CANCELLED"}
            )
        
        invoice_id = payment.invoice_id
        
        db.delete(payment)
        db.commit()
        
        # Actualizar el invoice
        invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if invoice:
            payments = db.query(InvoicePayment).filter(
                InvoicePayment.invoice_id == invoice_id
            ).all()
            
            total_paid = sum(p.amount for p in payments if p.payment_status in ["DEPOSITED", "PENDING"])
            balance_due = float(invoice.total or 0) - float(total_paid)
            
            if balance_due <= 0:
                invoice.status = "PAID"              # ← Call Center ve PAID
                invoice.payment_status = "PENDING"   # ← Contabilidad ve PENDING
            elif total_paid > 0:
                invoice.status = "PARTIALLY_PAID"    # ← Call Center ve PARTIALLY_PAID
                invoice.payment_status = "PENDING"   # ← Contabilidad ve PENDING
            else:
                invoice.status = "PENDING"           # ← Call Center ve PENDING
                invoice.payment_status = "PENDING"   # ← Contabilidad ve PENDING
            
            db.commit()
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Pago eliminado exitosamente"
            }
        )
        
    except Exception as e:
        db.rollback()
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


# ============================================================
# 8. INVOICES WORKSHOP VIEW
# ============================================================
@router.get("/workshop", response_class=HTMLResponse)
def invoices_workshop_view(
    request: Request,
    selected_date: Optional[str] = None,
    status_filter: Optional[str] = "all",
    db: Session = Depends(get_db)
):
    """Vista de Invoices para Workshop / Taller"""
    
    # Determinar fecha
    if selected_date:
        try:
            target_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
        except ValueError:
            target_date = date.today()
    else:
        target_date = date.today()
    
    day_name = target_date.strftime("%A")
    return_url = f"/invoices/workshop?selected_date={selected_date or target_date.strftime('%Y-%m-%d')}&status_filter={status_filter or 'all'}"
    
    # Query base
    base_query = db.query(Invoice).filter(
        Invoice.estimated_appointment_date == target_date
    )
    
    # Obtener todos para contar
    all_invoices = base_query.all()
    
    # Contar por estado
    total_invoices = len(all_invoices)
    pending_count = sum(1 for inv in all_invoices if inv.status and inv.status.upper() == "PENDING")
    partially_paid_count = sum(1 for inv in all_invoices if inv.status and inv.status.upper() == "PARTIALLY_PAID")
    paid_count = sum(1 for inv in all_invoices if inv.status and inv.status.upper() == "PAID")
    void_count = sum(1 for inv in all_invoices if inv.status and inv.status.upper() == "VOID")
    
    # Aplicar filtro de estado
    if status_filter and status_filter != "all":
        if status_filter.upper() == "PENDING":
            base_query = base_query.filter(Invoice.status == "PENDING")
        elif status_filter.upper() == "PARTIALLY_PAID":
            base_query = base_query.filter(Invoice.status == "PARTIALLY_PAID")
        elif status_filter.upper() == "PAID":
            base_query = base_query.filter(Invoice.status == "PAID")
        elif status_filter.upper() == "VOID":
            base_query = base_query.filter(Invoice.status.ilike("void"))
     
    invoices = base_query.order_by(Invoice.id.desc()).all()
    
    # Preparar datos
    invoices_data = []
    for inv in invoices:
        # Obtener customer
        customer = db.query(Customer).filter(Customer.id == inv.customer_id).first() if inv.customer_id else None
        
        # Obtener año del vehículo
        vehicle_year = None
        if inv.vehicle_year_id:
            year_record = db.query(Year).filter(Year.id == inv.vehicle_year_id).first()
            if year_record:
                vehicle_year = year_record.year
        
        # Calcular total pagado
        payments = db.query(InvoicePayment).filter(
            InvoicePayment.invoice_id == inv.id
        ).all()
        total_paid = sum(p.amount for p in payments if p.payment_status in ["DEPOSITED", "PENDING"])
        balance_due = float(inv.total or 0) - float(total_paid)
        
        invoices_data.append((inv, customer, vehicle_year, total_paid, balance_due))
    
    return templates.TemplateResponse(
        request=request,
        name="call_center/call_center_invoices_workshop.html",
        context={
            "invoices_data": invoices_data,
            "selected_date": target_date.strftime("%Y-%m-%d"),
            "day_name": day_name,
            "status_filter": status_filter or "all",
            "total_invoices": total_invoices,
            "pending_count": pending_count,
            "partially_paid_count": partially_paid_count,
            "paid_count": paid_count,
            "void_count": void_count,
            "return_url": return_url
        }
    )


# ============================================================
# 9. SECCIÓN DE ACTIVIDADES (CONCEPTS & ACTIVITIES)
# ============================================================

# ============================================================
# 9.1 OBTENER TODOS LOS CONCEPTOS ACTIVOS
# ============================================================
@router.get("/concepts")
async def get_concepts(
    db: Session = Depends(get_db)
):
    """Obtener todos los conceptos activos"""
    try:
        concepts = db.query(Concept).filter(
            Concept.is_active == True
        ).order_by(Concept.sort_order, Concept.name).all()
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": [c.to_dict() for c in concepts]
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


# ============================================================
# 9.2 OBTENER ACTIVIDADES DE UN INVOICE
# ============================================================
@router.get("/{invoice_id}/activities")
async def get_invoice_activities(
    invoice_id: int,
    db: Session = Depends(get_db)
):
    """Obtener todas las actividades de un invoice"""
    try:
        activities = db.query(InvoiceActivity).filter(
            InvoiceActivity.invoice_id == invoice_id
        ).order_by(desc(InvoiceActivity.created_at)).all()
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": [a.to_dict() for a in activities]
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


# ============================================================
# 9.3 AGREGAR NUEVA ACTIVIDAD A UN INVOICE
# ============================================================
@router.post("/{invoice_id}/activities")
async def create_invoice_activity(
    request: Request,
    invoice_id: int,
    db: Session = Depends(get_db)
):
    """Agregar una nueva actividad a un invoice"""
    try:
        # Verificar que el invoice existe
        invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not invoice:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Invoice no encontrado"}
            )
        
        # Obtener datos del formulario
        form_data = await request.form()
        concept_id = form_data.get("concept_id")
        description = form_data.get("description", "").strip() or None
        
        if not concept_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "El concepto es obligatorio"}
            )
        
        # Verificar que el concepto existe
        concept = db.query(Concept).filter(Concept.id == concept_id).first()
        if not concept:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Concepto no encontrado"}
            )
        
        # Obtener usuario de la sesión
        username = request.session.get("username") or request.session.get("user_name") or "system"
        
        # Crear la actividad
        new_activity = InvoiceActivity(
            invoice_id=invoice_id,
            concept_id=concept_id,
            description=description,
            created_by=username
        )
        
        db.add(new_activity)
        db.commit()
        db.refresh(new_activity)
        
        return JSONResponse(
            status_code=201,
            content={
                "success": True,
                "message": "Actividad registrada exitosamente",
                "data": new_activity.to_dict()
            }
        )
        
    except Exception as e:
        db.rollback()
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )