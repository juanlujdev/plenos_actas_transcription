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
    apodos: list[str] = []


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


def ruta_en_historial(historial: Path, fichero: Path) -> Path:
    sello = f"{datetime.now():%Y-%m-%d-%H%M%S}"
    destino = historial / f"{fichero.stem}-{sello}{fichero.suffix}"
    n = 1
    while destino.exists():
        n += 1
        destino = historial / f"{fichero.stem}-{sello}-{n}{fichero.suffix}"
    return destino


def guardar(corp: Corporacion, ruta: Path) -> None:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if ruta.exists():
        historial = ruta.parent / "historial"
        historial.mkdir(exist_ok=True)
        shutil.copy2(ruta, ruta_en_historial(historial, ruta.with_name("corporacion.json")))
    ruta.write_text(json.dumps(corp.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")


_en_uso: Corporacion | None = None


def usar(corp: Corporacion) -> None:
    global _en_uso
    _en_uso = corp


def en_uso() -> Corporacion:
    if _en_uso is None:
        usar(cargar())
    return _en_uso


_ORDINALES = {
    "hombre": {1: "primer", 2: "segundo", 3: "tercer", 4: "cuarto", 5: "quinto"},
    "mujer": {1: "primera", 2: "segunda", 3: "tercera", 4: "cuarta", 5: "quinta"},
}


def _ordinal(sexo: str, n: int) -> str:
    return _ORDINALES[sexo].get(n) or f"{n}.{'º' if sexo == 'hombre' else 'ª'}"


def _por_sexo(p: Persona | Secretaria, masculino: str, femenino: str) -> str:
    return masculino if p.sexo == "hombre" else femenino


def con_tratamiento(p: Persona | Secretaria) -> str:
    return f"{_por_sexo(p, 'D.', 'Dª')} {p.nombre}"


def cargo_en_texto(p: Persona) -> str:
    if p.cargo == "alcalde":
        return _por_sexo(p, "Alcalde", "Alcaldesa")
    if p.cargo == "teniente":
        return f"{_ordinal(p.sexo, p.orden_teniente)} Teniente de Alcalde"
    return _por_sexo(p, "Concejal", "Concejala")


def _titular(p: Persona) -> str:
    return (f"{_por_sexo(p, 'el Sr.', 'la Sra.')} {_por_sexo(p, 'Alcalde', 'Alcaldesa')} – "
            f"{_por_sexo(p, 'Presidente', 'Presidenta')}, {con_tratamiento(p)}")


def formula_presidencia(corp: Corporacion) -> str:
    preside = corp.quien_preside()
    if corp.presidencia.motivo == "titular":
        return _titular(preside)
    teniente = (f"{_por_sexo(preside, 'el', 'la')} {_ordinal(preside.sexo, preside.orden_teniente)} "
                f"Teniente Alcalde {con_tratamiento(preside)}")
    alcalde = corp.alcalde()
    if corp.presidencia.motivo == "delegacion":
        return (f"{teniente}, que actúa en virtud de la delegación de funciones efectuadas por "
                f"{_titular(alcalde)}")
    del_alcalde = _titular(alcalde).replace("el Sr.", "del Sr.", 1).replace("la Sra.", "de la Sra.", 1)
    return f"{teniente}, en sustitución {del_alcalde}, por ausencia"


def tratamiento_presidencia(corp: Corporacion) -> str:
    preside = corp.quien_preside()
    cargo = _por_sexo(preside, "Alcalde", "Alcaldesa") if corp.presidencia.motivo == "titular" else "Teniente de Alcalde"
    return f"{_por_sexo(preside, 'el Sr.', 'la Sra.')} {cargo}"


def abre_la_sesion(corp: Corporacion) -> str:
    return f"{_por_sexo(corp.quien_preside(), 'el Presidente', 'la Presidenta')} abre la sesión"


def etiqueta_secretaria(corp: Corporacion) -> str:
    return _por_sexo(corp.secretaria, "Secretario", "Secretaria")


def la_secretaria(corp: Corporacion) -> str:
    return f"{_por_sexo(corp.secretaria, 'el', 'la')} {etiqueta_secretaria(corp)}"


def cargo_secretaria(corp: Corporacion) -> str:
    return f"{etiqueta_secretaria(corp)} – {_por_sexo(corp.secretaria, 'Interventor', 'Interventora')}"


def hay_alcaldesa(corp: Corporacion) -> bool:
    return corp.alcalde().sexo == "mujer"


def _ordenados(corp: Corporacion) -> list[Persona]:
    preside = corp.quien_preside()
    resto = [p for p in corp.miembros if p is not preside]
    alcalde = [p for p in resto if p.cargo == "alcalde"]
    tenientes = sorted((p for p in resto if p.cargo == "teniente"), key=lambda p: p.orden_teniente)
    concejales = [p for p in resto if p.cargo == "concejal"]
    return [preside, *alcalde, *tenientes, *concejales]


_PARTICULAS = {"de", "del", "la", "las", "los", "y", "san"}


def _primer_apellido(p: Persona) -> str | None:
    unidades: list[str] = []
    for palabra in reversed(p.nombre.split()):
        if unidades and palabra.lower() in _PARTICULAS:
            unidades[-1] = f"{palabra} {unidades[-1]}"
        else:
            unidades.append(palabra)
    unidades.reverse()
    if len(unidades) < 2:
        return None
    return unidades[-2] if len(unidades) >= 3 else unidades[-1]


def _frase_apodos(p: Persona | Secretaria) -> str:
    if not p.apodos:
        return ""
    ellos = _por_sexo(p, "él", "ella")
    la = _por_sexo(p, "lo", "la")
    apodos = " o ".join(f'"{a}"' for a in p.apodos)
    return (f'En la sesión se dirigen a {ellos} como {apodos}: es la misma persona. '
            f'En el acta se {la} nombra siempre "{con_tratamiento(p)}".')


def _linea_miembro(p: Persona) -> str:
    cargo = cargo_en_texto(p)
    if p.cargo == "alcalde":
        cargo = f"{cargo}-{_por_sexo(p, 'Presidente', 'Presidenta')}".upper()
    elif p.cargo == "teniente":
        cargo = cargo.upper()
    grupo = "equipo de gobierno" if p.grupo == "gobierno" else "oposición"
    if p.cargo == "concejal":
        linea = f"- {p.nombre} — {cargo}, {grupo} ({p.partido})"
    else:
        linea = f"- {p.nombre} — {cargo} ({p.partido}), {grupo}"
    if p.situacion:
        linea += f", {p.situacion}"
    for extra in (_frase_apodos(p), p.observacion):
        if extra:
            linea += "\n  " + extra
    return linea


def _parrafo_presidencia(corp: Corporacion) -> str:
    preside, alcalde = corp.quien_preside(), corp.alcalde()
    trato = tratamiento_presidencia(corp)
    se_nombra = f"En el acta se {_por_sexo(preside, 'le', 'la')} nombra \"{trato}\", o {con_tratamiento(preside)}."
    if corp.presidencia.motivo == "titular":
        return f"PRESIDENCIA: {preside.nombre} preside las sesiones como {cargo_en_texto(preside)} titular. {se_nombra}"
    el_alcalde = _por_sexo(alcalde, "el Sr. Alcalde", "la Sra. Alcaldesa")
    if corp.presidencia.motivo == "delegacion":
        lineas = [f"PRESIDENCIA: {preside.nombre} preside las sesiones en virtud de la delegación de "
                  f"funciones efectuada por {el_alcalde}-{_por_sexo(alcalde, 'Presidente', 'Presidenta')}."]
    else:
        lineas = [f"PRESIDENCIA: {preside.nombre} preside en sustitución de {el_alcalde}, por ausencia."]
    if hay_alcaldesa(corp):
        lineas.append(se_nombra)
    else:
        cargo = _por_sexo(preside, "Alcalde", "Alcaldesa")
        lineas.append(f"NO es {cargo} ni {cargo} en funciones y NUNCA se {_por_sexo(preside, 'le', 'la')} "
                      f"nombra así en el acta: es {trato}, o {con_tratamiento(preside)}.")
    lineas.append(f"{con_tratamiento(alcalde)} sigue siendo {el_alcalde} a todos los efectos: es \"{el_alcalde} {con_tratamiento(alcalde)}\". "
                  f"Cuando asiste a la sesión e interviene en el debate sin presidirla, lo hace como "
                  f"{_por_sexo(alcalde, 'un concejal más', 'una concejala más')}: "
                  f"\"{_por_sexo(alcalde, 'el Sr. concejal', 'la Sra. concejala')} {con_tratamiento(alcalde)}\".")
    return "\n".join(lineas)


_NUMEROS = {2: "DOS", 3: "TRES", 4: "CUATRO", 5: "CINCO"}


def _avisos_apellido(corp: Corporacion) -> list[str]:
    avisos = []
    vistos = set()
    for p in corp.miembros:
        ap = _primer_apellido(p)
        if ap is None or ap in vistos:
            continue
        vistos.add(ap)
        comparten = [q for q in corp.miembros if _primer_apellido(q) == ap]
        if len(comparten) < 2:
            continue
        n = _NUMEROS.get(len(comparten), str(len(comparten)))
        nombres = ", ".join(q.nombre for q in comparten)
        avisos.append(
            f"ATENCIÓN: son {n} personas distintas que comparten apellido ({nombres}). \"{ap}\" a "
            f"secas no identifica a ninguna de ellas. Para atribuirle una intervención a una de ellas "
            f"hace falta el nombre de pila, o que la etiqueta de locutor esté identificada según las "
            f"reglas de ETIQUETAS DE LOCUTOR. Si solo se oye el apellido, la atribución es \"no identificado en la "
            f"grabación\".")
    return avisos


def bloque_corporacion(corp: Corporacion) -> str:
    partes = ["CORPORACIÓN MUNICIPAL (para escribir bien los nombres —ver regla 4— y\n"
              "acertar el tratamiento —ver regla 8—):"]
    partes += [_linea_miembro(p) for p in _ordenados(corp)]
    partes.append(_parrafo_presidencia(corp))
    partes += _avisos_apellido(corp)
    partes.append(
        f"- {corp.secretaria.nombre} — {etiqueta_secretaria(corp)}-"
        f"{_por_sexo(corp.secretaria, 'Interventor', 'Interventora')} del Ayuntamiento. NO es miembro de "
        f"la Corporación y no vota: da fe de la sesión, lee acuerdos e informa cuando se le pide. "
        f"Su voz sale en la grabación, pero nunca va en "
        f"`asistentes` ni en `ausentes`."
        + (f"\n  {_frase_apodos(corp.secretaria)}" if corp.secretaria.apodos else ""))
    return "\n".join(partes)


def _etiqueta_voz(corp: Corporacion, p: Persona) -> str:
    if p is corp.quien_preside():
        return f"{p.nombre} (preside)"
    if p.cargo == "alcalde":
        return f"{p.nombre} ({cargo_en_texto(p)})"
    return p.nombre


def personas_voz(corp: Corporacion) -> list[tuple[str, str, str]]:
    voces = [(con_tratamiento(p), _etiqueta_voz(corp, p), " / ".join(p.apodos)) for p in _ordenados(corp)]
    s = corp.secretaria
    voces.append((con_tratamiento(s), f"{s.nombre} ({etiqueta_secretaria(corp)})", " / ".join(s.apodos)))
    return voces


def nombres_y_apodos(corp: Corporacion) -> list[str]:
    nombres = []
    for p in [*_ordenados(corp), corp.secretaria]:
        nombres += [p.nombre, *p.apodos]
    return list(dict.fromkeys(nombres))


def resumen(corp: Corporacion) -> list[str]:
    lineas = []
    for p in _ordenados(corp):
        grupo = "gobierno" if p.grupo == "gobierno" else "oposición"
        extra = " — preside" if p is corp.quien_preside() else ""
        lineas.append(f"{p.nombre} — {cargo_en_texto(p)} ({p.partido}, {grupo}){extra}")
    lineas.append(f"{corp.secretaria.nombre} — {cargo_secretaria(corp)}")
    return lineas
