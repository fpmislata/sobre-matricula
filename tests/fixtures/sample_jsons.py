"""JSONs de resultado reutilizables para tests."""
from copy import deepcopy

_BASE = {
    "expediente": "15001",
    "nombre": "ANA",
    "apellido1": "MARTIN",
    "apellido2": "RUIZ",
    "tipo_asistencia": "presencial",
    "ciclo": {
        "codigo": "DAW",
        "nombre_completo": "Desarrollo de Aplicaciones Web",
        "grado": "superior",
        "texto_original": "DAW",
    },
    "curso": {"inicio": "2025", "fin": "2026"},
    "documento": {
        "tipo": "DNI",
        "numero_extraido": "87654321X",
        "numero_verificado": "87654321X",
        "estado": "verificado",
        "detalle_correccion": None,
    },
    "cotejo_documento_identidad": {
        "realizado": True,
        "numero_coincide": True,
        "numero_usado": "dni",
        "nombre_coincide": True,
        "apellido1_coincide": True,
        "apellido2_coincide": True,
        "correcciones_aplicadas": [],
    },
    "datos_extraidos_dni": {
        "nombre": "ANA",
        "apellido1": "MARTIN",
        "apellido2": "RUIZ",
        "numero_documento": "87654321X",
    },
    "fotos": {
        "foto_carnet_encontrada": True,
        "foto_dni_encontrada": False,
        "foto_seleccionada": "carnet",
        "detalle": {
            "foto_carnet": {"es_color": True, "nitidez": 234.5},
            "foto_dni": None,
        },
    },
    "metadata": {
        "pdf_original": "15001-01.pdf",
        "procesado_en": "2026-01-01T12:00:00",
        "paginas_totales": 2,
        "nombre_documento": "ANA_MARTIN_RUIZ,ANA_E15001_P2526_M",
        "carpeta_salida": "/tmp/output/DAW/ANA_MARTIN_RUIZ,ANA_E15001_P2526_M",
        "en_revision": False,
        "motivos_revision": [],
        "errores": [],
    },
}


def result_valido() -> dict:
    return deepcopy(_BASE)


def result_sin_apellido2() -> dict:
    r = deepcopy(_BASE)
    r["apellido2"] = None
    r["datos_extraidos_dni"]["apellido2"] = None
    return r


def result_en_revision(motivos: list[str] | None = None) -> dict:
    r = deepcopy(_BASE)
    r["metadata"]["en_revision"] = True
    r["metadata"]["motivos_revision"] = motivos or ["campo obligatorio ausente: ciclo"]
    r["ciclo"]["codigo"] = None
    return r


def result_dni_erroneo() -> dict:
    r = deepcopy(_BASE)
    r["documento"]["estado"] = "erroneo"
    r["documento"]["numero_verificado"] = None
    r["cotejo_documento_identidad"]["numero_usado"] = "formulario_dni_invalido"
    return r


def form_data_completo() -> dict:
    """Respuesta de extract_form_data simulada (salida del LLM normalizada)."""
    return {
        "expediente": "15001",
        "tipo_documento": "DNI",
        "numero_documento": "87654321X",
        "nombre": "ANA",
        "apellido1": "MARTIN",
        "apellido2": "RUIZ",
        "ciclo_detectado": "Desarrollo de Aplicaciones Web",
        "ciclo_codigo": "DAW",
        "grado": "superior",
        "tipo_asistencia": "presencial",
        "curso_inicio": "2025",
        "curso_fin": "2026",
    }


def llm_form_response() -> dict:
    """JSON crudo que devuelve el LLM para el formulario (antes de normalizar)."""
    return {
        "expediente": "15001",
        "tipo_documento": "DNI",
        "numero_documento": "87654321X",
        "nombre": "ANA",
        "apellido1": "MARTIN",
        "apellido2": "RUIZ",
        "ciclo_detectado": "DAW",
        "ciclo_codigo": "DAW",
        "grado": "superior",
        "tipo_asistencia": "presencial",
        "curso_inicio": "2025",
        "curso_fin": "2026",
    }


def llm_page_response_documento() -> dict:
    """Respuesta del LLM para analyze_page — documento de identidad."""
    return {
        "tipo_pagina": "documento_identidad",
        "subtipo_documento": "DNI",
        "datos_documento": {
            "nombre": "ANA",
            "apellido1": "MARTIN",
            "apellido2": "RUIZ",
            "numero_documento": "87654321X",
        },
    }


def llm_page_response_foto() -> dict:
    """Respuesta del LLM para analyze_page — foto carnet."""
    return {
        "tipo_pagina": "foto_carnet",
        "subtipo_documento": None,
        "datos_documento": {
            "nombre": None,
            "apellido1": None,
            "apellido2": None,
            "numero_documento": None,
        },
    }


def llm_page_response_otro() -> dict:
    """Respuesta del LLM para analyze_page — otro."""
    return {
        "tipo_pagina": "otro",
        "subtipo_documento": None,
        "datos_documento": {
            "nombre": None,
            "apellido1": None,
            "apellido2": None,
            "numero_documento": None,
        },
    }
