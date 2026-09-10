# Ejemplos

Scripts de un solo uso, escritos antes de que el paquete tuviera `mef report` / `mef chart-local`.
Están fijados al dataset `canon_minero`, así que **hay que descargarlo primero**:

```bash
mef fetch <resource_id-del-canon-minero> canon_minero --limit 50000
```

- `generate_report.py` — dashboard HTML con el top 10 de departamentos y ejecutoras.
- `generate_report_advanced.py` — versión con más cortes (mensual, departamentos, municipalidades).

Para cualquier informe nuevo, prefiere el CLI: hace lo mismo sin escribir código.

```bash
mef report "SELECT DEPARTAMENTO_EJECUTORA_NOMBRE, SUM(MONTO_RECAUDADO) AS total
            FROM canon_minero GROUP BY 1 ORDER BY total DESC LIMIT 10" \
           "Top 10 departamentos por canon" -f markdown,html,pdf
```
