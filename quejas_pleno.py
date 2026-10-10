"""Comprueba el informe.json de un pleno contra las quejas justificadas que se hicieron de su acta.

    python quejas_pleno.py 2026-09-03          # carpeta de ACTAS_DIR o uploads/actas
    python quejas_pleno.py 2026-09-03 RUTA     # o una carpeta concreta

Local, no versionado: lee datos reales. Una queja nueva es una entrada en CASOS.
"""
import json
import re
import sys
from pathlib import Path

from plenos_informe import InformePleno, incoherencias
from procesar_pleno import dir_borrador


def texto_acta(informe: InformePleno) -> str:
    """Todo el texto libre que acaba impreso en el acta."""
    trozos = [informe.motivo_convocatoria or "", *informe.declaraciones_apertura]
    for p in informe.orden_del_dia:
        trozos += [p.titulo, p.texto, p.acuerdo or ""]
    for b in informe.ruegos_y_preguntas:
        trozos += [b.formulados_por, *b.puntos]
    return "\n".join(trozos)


def fuera_de_citas(texto: str) -> str:
    return re.sub("“[^”]*”|«[^»]*»|\"[^\"]*\"", " ", texto)


def _sin(informe, *patrones):
    t = texto_acta(informe)
    return not any(re.search(p, t, re.IGNORECASE) for p in patrones)


def _con(informe, *patrones):
    t = texto_acta(informe)
    return all(re.search(p, t, re.IGNORECASE) for p in patrones)


def _punto(informe, numero):
    return next((p for p in informe.orden_del_dia if p.numero == numero), None)


def _votacion(informe, numero, a_favor, en_contra, resultado):
    p = _punto(informe, numero)
    v = p.votacion if p else None
    return bool(v and v.a_favor == a_favor and v.en_contra == en_contra
                and v.resultado == resultado
                and not re.search(r"\b(rechaz|desestim)", (p.acuerdo or "") if resultado == "aprobado" else ""))


CASOS = {
    # Quejas del pleno del 7-X-2026 sobre el acta del pleno del 3-IX-2026.
    "2026-09-03": [
        ("fecha", "El acta sale fechada el 30 de septiembre (la Presidencia lo dijo mal al abrir)",
         lambda i: i.fecha_pleno == "2026-09-03"),
        ("punto1-votacion", "Punto 1: con 3 a favor, 2 en contra y 2 abstenciones el acta decía «rechazar»",
         lambda i: _votacion(i, 1, 3, 2, "aprobado")),
        ("punto3-votacion", "Punto 3: 3 a favor y 4 en contra, resultado rechazado",
         lambda i: _votacion(i, 3, 3, 4, "rechazado")),
        ("pesquera", "«Pesquera» salía como «visera»",
         lambda i: _sin(i, r"\bvisera\b") and _con(i, r"Pesquera")),
        ("playeta", "«La Playeta» mal escrita", lambda i: _sin(i, r"\bplayera\b|\bplaceta\b")),
        ("chorreras", "«torrejas… galletas» acabó como «regulación de acceso a Las Chorreras»",
         lambda i: _sin(i, r"regulaci[oó]n de acceso a Las Chorreras")),
        ("hoya", "«Hoya de las Vejas» en lugar de «Hoya de las Abejas»",
         lambda i: _sin(i, r"Hoya de las Vejas")),
        ("tenso-enfrentamiento", "«tenso enfrentamiento» y «acusaciones mutuas» donde solo acusaba una parte",
         lambda i: _sin(i, r"tenso enfrentamiento", r"\bmutu[ao]s\b", r"altercado")),
        ("amenaza-expulsion", "«amenaza con promover su expulsión» por una frase que no es amenaza",
         lambda i: _sin(i, r"amenaza con promover")),
        ("alcaldesa", "«Alcaldesa» (fuera de citas) para quien preside como Teniente de Alcalde",
         lambda i: "alcaldesa" not in fuera_de_citas(texto_acta(i)).lower()),
        ("escombros", "Falta la respuesta de Fernando Pons sobre los escombros",
         lambda i: _con(i, r"escombros")),
    ],
}


def comprobar(fecha: str, carpeta: Path) -> int:
    informe = InformePleno.model_validate_json((carpeta / f"{fecha}-informe.json").read_text(encoding="utf-8"))
    fallos = 0
    for id_, queja, ok in CASOS.get(fecha, []):
        bien = ok(informe)
        fallos += not bien
        print(f"  {'✓' if bien else '✗'} {id_}: {queja}")
    transcripcion = next(iter(carpeta.glob("*-transcripcion.md")), None)
    auto = incoherencias(informe, transcripcion.read_text(encoding="utf-8") if transcripcion else None)
    for p in auto:
        fallos += 1
        print(f"  ✗ [automática] {p.seccion}: {p.afirmacion_dudosa} → {p.motivo}")
    print(f"\n{'✓ Ninguna queja en pie' if not fallos else f'✗ {fallos} quejas/comprobaciones en pie'}")
    return fallos


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    fecha = sys.argv[1]
    carpeta = Path(sys.argv[2]) if len(sys.argv) > 2 else dir_borrador(fecha)
    sys.exit(1 if comprobar(fecha, carpeta) else 0)
