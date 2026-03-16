c = open('/app/app/api/kpi_router.py').read()
c2 = c.replace(
    'db.execute(\n        "SELECT DISTINCT annee, mois, periode FROM kpis_mensuels ORDER BY annee DESC, mois DESC"\n    ).fetchall()',
    'db.execute(\n        text("SELECT DISTINCT annee, mois, periode FROM kpis_mensuels ORDER BY annee DESC, mois DESC")\n    ).fetchall()'
)
open('/app/app/api/kpi_router.py', 'w').write(c2)
print('changed' if c != c2 else 'no change')
if c == c2:
    for i, line in enumerate(c.split('\n')):
        if 'SELECT DISTINCT' in line:
            print(f"line {i}: {repr(line)}")
