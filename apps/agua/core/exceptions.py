# core/exceptions.py
from rest_framework.views import exception_handler

def custom_exception_handler(exc, context):
    """
    Reemplaza el campo 'detail' por 'error' en todas las respuestas de error.
    """
    response = exception_handler(exc, context)

    if response is not None and isinstance(response.data, dict):
        # Si la respuesta tiene 'detail', la reemplazamos
        if "detail" in response.data:
            response.data = {"error": response.data["detail"]}

        # Si hay varios errores (por validación, etc.), los formateamos igual
        elif isinstance(next(iter(response.data.values()), None), list):
            response.data = {"error": response.data}

    return response
