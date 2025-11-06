# from django.db.models.signals import post_save
# from django.dispatch import receiver
# from .models import Reading, MonthlyBilling, Service

# @receiver(post_save, sender=Reading)
# def update_monthly_billing(sender, instance, created, **kwargs):
#     # Extraer mes y año de la lectura
#     month = instance.reading_date.month
#     year = instance.reading_date.year

#     # Obtener la política de servicio.
#     # Si tienes varios servicios, ajusta la lógica para seleccionar el adecuado.
#     service = Service.objects.first()  # Asumiendo que hay un único servicio

#     # Buscar o crear el registro de facturación mensual correspondiente
#     billing, created_billing = MonthlyBilling.objects.get_or_create(
#         customer=instance.customer,
#         service=service,
#         month=month,
#         year=year
#     )
#     # Se actualiza la facturación recalculando consumo y total_amount
#     billing.save()