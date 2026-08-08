---
type: concept
date_updated: 2026-08-08
source_count: 1
---

# Bucle generador → auditor → corrector

Mecanismo de fiabilidad de [[pipeline-plenos]] para que el informe sea fiel a la transcripción. Diseñado en [[2026-07-31-plenos-youtube-pipeline-design]], implementado en `scripts/plenos_informe.py` y aprobado por el usuario en un checkpoint explícito durante el desarrollo.

## Los tres roles

Un mismo modelo (temperatura 0) con **tres prompts distintos**, cada uno una función Python con su `response_schema`:

1. **Generador** — transcripción → `InformePleno`. Prohibido inferir o rellenar huecos; lo que no conste usa [[via-de-escape-en-el-esquema]].
2. **Auditor** — transcripción + informe → `AuditoriaInforme`: lista de problemas concretos, cada uno con sección, afirmación dudosa, motivo y **cita literal** de la transcripción como evidencia. Lista vacía = visto bueno.
3. **Corrector** — transcripción + informe completo + problemas → `InformePleno` corregido. Recibe siempre el contexto entero, nunca solo el punto a corregir, y devuelve **el mismo esquema que el generador**, de modo que el bucle es estable en tipos y el auditor siempre revisa el mismo objeto.

## El bucle

```python
informe = generar(transcripcion)
problemas = auditar(transcripcion, informe).problemas
vueltas = 0
while problemas and vueltas < MAX_VUELTAS:   # MAX_VUELTAS = 3
    informe = corregir(transcripcion, informe, problemas)
    vueltas += 1
    problemas = auditar(transcripcion, informe).problemas
return informe, problemas
```

**Sin framework de agentes**: no hay herramientas ni autonomía que orquestar, así que el flujo de control es un `while` propio y determinista. El tope de 3 vueltas existe porque dos prompts en desacuerdo pueden ciclar indefinidamente. Si tras el tope quedan problemas, se devuelven como pendientes y el informe se publica marcando esos puntos como no verificados.

Los tres roles se pueden inyectar como parámetros (`generar=`, `auditar=`, `corregir=`), lo que permite probar el bucle con fakes sin tocar la red — es lo que hacen los tests.

## Lo que el auditor no puede detectar

**Errores que ya vienen en la transcripción.** El auditor compara el informe contra la transcripción, así que si Whisper transcribió mal un nombre y el informe lo copia fielmente, el auditor da su visto bueno. Por eso la spec insiste en que la revisión humana contra el audio es una capa irreemplazable.

De ahí sale una consecuencia de diseño poco obvia: al añadir el listado de la corporación municipal al generador para que corrija los nombres deformados, **hubo que dárselo también al auditor**. Si no, vería "Sergio de Fez Cerezuela" en el informe, buscaría esa cadena en la transcripción (que dice "Féceres Zuela"), no la encontraría, y la marcaría como afirmación no respaldada — quemando las tres vueltas de corrección en cada ejecución sin arreglar nada. El auditor tiene instrucción explícita de no señalar esas correcciones ni el tiempo verbal.

## Coste

Mínimo 2 llamadas al modelo (generar + auditar); máximo 8 (generar + 4 auditorías + 3 correcciones). En la primera ejecución real el auditor dio el visto bueno a la primera, así que fueron 2.

## Relacionado

[[pipeline-plenos]], [[via-de-escape-en-el-esquema]], [[2026-07-31-plenos-youtube-pipeline-design]], [[clasificacion-ia]], [[por-que-plenos-en-local]]
