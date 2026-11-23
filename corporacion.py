import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError, model_validator

RUTA_SEMILLA = Path(__file__).resolve().parent / "corporacion_inicial.json"


class ErrorCorporacion(Exception):
    pass


class Persona(BaseModel):
    nombre: str
    sexo: Literal["hombre", "mujer"]
    cargo: Literal["alcalde", "teniente", "concejal"]
    orden_teniente: int | None = None
    partido: str
    grupo: Literal["gobierno", "oposicion"]
    apodos: list[str] = []
    observacion: str = ""
    situacion: str = ""


class Secretaria(BaseModel):
    nombre: str
    sexo: Literal["hombre", "mujer"]


class Presidencia(BaseModel):
    persona: str
    motivo: Literal["titular", "delegacion", "ausencia"]


class Corporacion(BaseModel):
    miembros: list[Persona]
    secretaria: Secretaria
    presidencia: Presidencia

    @model_validator(mode="after")
    def _validar(self):
        if sum(p.cargo == "alcalde" for p in self.miembros) != 1:
            raise ValueError("Tiene que haber un Alcalde o Alcaldesa, y solo uno.")
        nombres = [p.nombre for p in self.miembros]
        if len(set(nombres)) != len(nombres):
            raise ValueError("Hay dos miembros con el mismo nombre.")
        ordenes = []
        for p in self.miembros:
            if p.cargo == "teniente":
                if p.orden_teniente is None:
                    raise ValueError(f"A {p.nombre} le falta el número de Teniente de Alcalde.")
                ordenes.append(p.orden_teniente)
            elif p.orden_teniente is not None:
                raise ValueError(f"{p.nombre} no es Teniente de Alcalde y no puede tener número de teniente.")
        if len(set(ordenes)) != len(ordenes):
            raise ValueError("Hay dos Tenientes de Alcalde con el mismo número.")
        preside = next((p for p in self.miembros if p.nombre == self.presidencia.persona), None)
        if preside is None:
            raise ValueError("Quien preside tiene que ser un miembro de la corporación.")
        if self.presidencia.motivo == "titular":
            if preside.cargo != "alcalde":
                raise ValueError("Solo el Alcalde o Alcaldesa puede presidir como titular.")
        elif preside.cargo != "teniente":
            raise ValueError("Por delegación o ausencia solo puede presidir un Teniente de Alcalde.")
        return self

    def alcalde(self) -> Persona:
        return next(p for p in self.miembros if p.cargo == "alcalde")

    def quien_preside(self) -> Persona:
        return next(p for p in self.miembros if p.nombre == self.presidencia.persona)


def errores_legibles(e: ValidationError) -> list[str]:
    return [err["msg"].removeprefix("Value error, ") for err in e.errors()]


def _leer(ruta: Path) -> Corporacion:
    try:
        return Corporacion.model_validate_json(ruta.read_text(encoding="utf-8"))
    except ValidationError as e:
        raise ErrorCorporacion("El fichero de la corporación está dañado: " + " ".join(errores_legibles(e))) from e
    except (OSError, ValueError) as e:
        raise ErrorCorporacion(f"El fichero de la corporación está dañado: no se puede leer ({e}).") from e


def semilla() -> Corporacion:
    return _leer(RUTA_SEMILLA)


def cargar() -> Corporacion:
    ruta = os.environ.get("CORPORACION_JSON")
    if ruta and Path(ruta).exists():
        return _leer(Path(ruta))
    return semilla()


def guardar(corp: Corporacion, ruta: Path) -> None:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if ruta.exists():
        historial = ruta.parent / "historial"
        historial.mkdir(exist_ok=True)
        shutil.copy2(ruta, historial / f"corporacion-{datetime.now():%Y-%m-%d-%H%M%S}.json")
    ruta.write_text(json.dumps(corp.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")


_en_uso: Corporacion | None = None


def usar(corp: Corporacion) -> None:
    global _en_uso
    _en_uso = corp


def en_uso() -> Corporacion:
    if _en_uso is None:
        usar(cargar())
    return _en_uso
