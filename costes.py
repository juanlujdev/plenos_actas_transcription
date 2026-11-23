"""Coste en dólares de cada ejecución del pipeline, por servicio."""
import json
from datetime import datetime
from pathlib import Path

AAI_PRECIO_HORA = 0.21
POR_DEFECTO = {"assemblyai": 0.40, "openrouter": 4.5}

_acumulado: dict[str, float] = {}


def reiniciar() -> None:
    _acumulado.clear()


def anotar(servicio: str, dolares: float) -> None:
    _acumulado[servicio] = _acumulado.get(servicio, 0.0) + dolares


def _leer(ruta: Path) -> list[dict]:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return datos if isinstance(datos, list) else []


def guardar(carpeta: Path) -> dict:
    entrada = {"fecha_hora": datetime.now().isoformat(timespec="seconds"),
               "assemblyai": _acumulado.get("assemblyai"),
               "openrouter": _acumulado.get("openrouter", 0.0)}
    ruta = carpeta / "costes.json"
    ruta.write_text(json.dumps(_leer(ruta) + [entrada], indent=2), encoding="utf-8")
    return entrada


def coste_habitual(actas: Path) -> dict[str, float]:
    ejecuciones = [e for ruta in actas.glob("*/costes.json") for e in _leer(ruta)]
    habitual = dict(POR_DEFECTO)
    for servicio in POR_DEFECTO:
        valores = [e[servicio] for e in ejecuciones if e.get(servicio) is not None]
        if valores:
            habitual[servicio] = sum(valores) / len(valores)
    return habitual
