from apps.tenant.models import ReceiptBatch
from apps.agua.models import Reading, Debt, Company, Zona, CashConcept
from django_tenants.utils import schema_context
from django.db.models import Count
from django.template.loader import render_to_string
from django.db.models.functions import Cast, Coalesce
from django.db.models import Prefetch, IntegerField
from django.utils.timezone import now
from weasyprint import HTML
from decimal import Decimal
import os
from collections import defaultdict
from babel.dates import format_date
from datetime import date
from django.conf import settings
from pathlib import Path

from django.utils.text import slugify

def generate_receipts_task(batch_id, schema_name):

    batch = ReceiptBatch.objects.get(id=batch_id)
    
    with schema_context(batch.tenant):

        master_concepts = CashConcept.objects.filter(is_master_view=True,state=True).order_by("id")

        batch.status = "processing"
        batch.save(update_fields=["status"])

        company = Company.objects.first()        
        logo_path = None

        if company and company.ruc:

            abs_logo_path = os.path.join(settings.MEDIA_ROOT, f"{company.ruc}.jpeg")

            if os.path.exists(abs_logo_path):
                logo_path = Path(abs_logo_path).as_uri()

        if batch.type == 'masivo':
        
            zonas = Zona.objects.annotate(
                total=Count("customers__readings", distinct=True)
            )

        if batch.type == 'zona':

            zonas = Zona.objects.filter(pk=batch.zona_id).annotate(
                total=Count("customers__readings")
            )

        total_global = 0
        processed_global = 0

        # 🔹 primero calcular total global
        for zona in zonas:
            count = Reading.objects.filter(
                period__year=batch.period.year,
                period__month=batch.period.month,
                customer__zona=zona
            ).count()

            total_global += count

        batch.total_records = total_global
        batch.save(update_fields=["total_records"])

        chunk_size = 100

        # 🔥 recorrer zonas
        for zona in zonas:
            
            if schema_name == 'chilca':

                queryset = (
                    Reading.objects.filter(
                        period__year=batch.period.year,
                        period__month=batch.period.month,
                        customer__zona=zona
                    )
                    .select_related(
                        "customer",
                        "customer__zona",
                        "customer__manzana",
                    )
                    .prefetch_related(
                        Prefetch(
                            "customer__debts",
                            queryset=Debt.objects.filter(
                                paid=False,
                                period__lt=batch.period
                            ),
                            to_attr="previous_debts"
                        )
                    )

                    # ==========================================
                    # ORDENAMIENTO CATASTRO
                    # ==========================================
                    .annotate(
                        mz_number=Cast(
                            'customer__manzana__codigo',
                            IntegerField()
                        ),

                        predio_number=Cast(
                            'customer__predio',
                            IntegerField()
                        ),
                    )

                    .order_by(
                        'customer__sector',
                        'mz_number',
                        'predio_number',
                    )
                )

            else:

                queryset = (
                    Reading.objects.filter(
                        period__year=batch.period.year,
                        period__month=batch.period.month,
                        customer__zona=zona
                    )
                    .select_related("customer", "customer__zona")
                    .prefetch_related(
                        Prefetch(
                            "customer__debts",
                            queryset=Debt.objects.filter(
                                paid=False,
                                period__lt=batch.period
                            ),
                            to_attr="previous_debts"
                        )
                    )
                    .order_by("customer__codigo")
                )

            total = queryset.count()
            offset = 0

            base_path = os.path.join(
                settings.MEDIA_ROOT,
                "tenants",
                schema_name,
                "recibos",
                batch.ticket, 
                str(batch.period),
                f"zona_{slugify(zona.name)}"
            )
            os.makedirs(base_path, exist_ok=True)

            part = 1  # 👈 contador independiente

            while offset < total:

                chunk = queryset[offset:offset + chunk_size]

                html = build_html(chunk, company, logo_path, zona.name, schema_name, master_concepts)

                file_path = os.path.join(base_path, f"parte_{part}.pdf")

                if not os.path.exists(file_path):
                    HTML(string=html).write_pdf(file_path)

                offset += chunk_size
                part += 1  # 👈 incrementas aquí

                processed_global += len(chunk)

                # 🔥 progreso global REAL
                batch.processed_records = processed_global
                batch.progress = int((processed_global / total_global) * 100)
                batch.save(update_fields=["processed_records", "progress"])

        batch.status = "done"
        batch.finished_at = now()
        batch.save(update_fields=["status", "finished_at"])

def build_html(readings, company, logo_path, zona, schema_name, master_concepts):

    all_data = []
    all_readings_context = []
   
    for reading in readings:

        receipt_details = []
        
        debt = Debt.objects.filter(customer=reading.customer, period=reading.period).first()

        if not debt:
               
           continue

        detail_map = {
            detail.concept_id: detail.amount
            for detail in debt.details.all()
        }

        for concept in master_concepts:

            receipt_details.append({
              "concept": concept,
              "amount": detail_map.get(concept.id, 0)
            })

        debts = getattr(reading.customer, "previous_debts", [])

        yearly_data = defaultdict(
            lambda: {"total": Decimal("0.00"), "months": []}
        )

        for d in debts:
            year = d.period.year
            month_d = d.period.month
            yearly_data[year]["total"] += d.amount
            yearly_data[year]["months"].append(month_d)

        grouped_debts = []
        for year, data in yearly_data.items():
            grouped_debts.append({
                "year": year,
                "total": f"{data['total']:.2f}",
                "from_month": format_date(
                    date(year, min(data["months"]), 1),
                    "MMMM",
                    locale="es"
                ).capitalize(),
                "to_month": format_date(
                    date(year, max(data["months"]), 1),
                    "MMMM",
                    locale="es"
                ).capitalize(),
            })

        grouped_debts.sort(key=lambda x: x["year"], reverse=True)

        total_previous_debt = sum(
            (d.amount for d in debts),
            Decimal("0.00")
        )

        total_general = debt.amount + total_previous_debt

        all_data.append({
            "debt": debt,
            "details": receipt_details,
            "reading": reading,
            "grouped_debts": grouped_debts,
            "total_previous_debt": total_previous_debt,
            "total_general": total_general,
        })  


    background_image = None

    if schema_name == 'chilca':
             
       template = "agua/chilca.html"     
       abs_logo_path = os.path.join(settings.MEDIA_ROOT, "chilca.png")

       if os.path.exists(abs_logo_path):
          
          background_image = Path(abs_logo_path).as_uri()

    else:

       template = "agua/recibo.html"

    return render_to_string(template, {
        "readings_context": all_data,
        "company": company,
        "company_logo": logo_path,
        "zona": zona,
        "background_image" : background_image
    })
