"""Expanded domain events — V17 transaction vocabulary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Masters
CUSTOMER_CREATED = "CustomerCreated"
SUPPLIER_CREATED = "SupplierCreated"
PRODUCT_CREATED = "ProductCreated"
EMPLOYEE_CREATED = "EmployeeCreated"

# Sales
INVOICE_CREATED = "InvoiceCreated"
INVOICE_APPROVED = "InvoiceApproved"
INVOICE_POSTED = "InvoicePosted"
INVOICE_REJECTED = "InvoiceRejected"
SALES_ORDER_CREATED = "SalesOrderCreated"

# Purchase
PURCHASE_RECEIVED = "PurchaseReceived"
PURCHASE_INVOICE_APPROVED = "PurchaseInvoiceApproved"
GRN_RECEIVED = "GRNReceived"

# Inventory
STOCK_ADJUSTED = "StockAdjusted"
STOCK_TRANSFERRED = "StockTransferred"

# Production
PRODUCTION_COMPLETED = "ProductionCompleted"
PRODUCTION_ISSUED = "ProductionIssued"
BATCH_TICKET_CREATED = "BatchTicketCreated"
FORMULA_SAVED = "FormulaSaved"
FORMULA_APPROVED = "FormulaApproved"
SPRAY_DRYER_STARTED = "SprayDryerStarted"
SPRAY_DRYER_COMPLETED = "SprayDryerCompleted"
REACTOR_COMPLETED = "ReactorCompleted"
CORRUGATED_COMPLETED = "CorrugatedCompleted"
GRAVURE_COMPLETED = "GravureCompleted"
PET_BLOWING_COMPLETED = "PetBlowingCompleted"
QC_INSPECTION_COMPLETED = "QCInspectionCompleted"
QC_COA_APPROVED = "QCCOAApproved"

# Finance
PAYMENT_RECEIVED = "PaymentReceived"
PAYMENT_MADE = "PaymentMade"
JOURNAL_POSTED = "JournalPosted"

# Portal
PORTAL_ORDER_SUBMITTED = "PortalOrderSubmitted"

ALL_EVENTS = [
    CUSTOMER_CREATED, SUPPLIER_CREATED, PRODUCT_CREATED, EMPLOYEE_CREATED,
    INVOICE_CREATED, INVOICE_APPROVED, INVOICE_POSTED, INVOICE_REJECTED,
    SALES_ORDER_CREATED, PURCHASE_RECEIVED, PURCHASE_INVOICE_APPROVED, GRN_RECEIVED,
    STOCK_ADJUSTED, STOCK_TRANSFERRED, PRODUCTION_COMPLETED, PRODUCTION_ISSUED,
    BATCH_TICKET_CREATED, FORMULA_SAVED, FORMULA_APPROVED,
    SPRAY_DRYER_STARTED, SPRAY_DRYER_COMPLETED, REACTOR_COMPLETED,
    CORRUGATED_COMPLETED, GRAVURE_COMPLETED, PET_BLOWING_COMPLETED,
    QC_INSPECTION_COMPLETED, QC_COA_APPROVED,
    PAYMENT_RECEIVED, PAYMENT_MADE, JOURNAL_POSTED, PORTAL_ORDER_SUBMITTED,
]


@dataclass
class DomainEvent:
    event_type: str
    aggregate_type: str | None = None
    aggregate_id: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    company_id: int = 1
    branch_id: int | None = None
    user_id: int | None = None
    trace_id: str | None = None
    published_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
