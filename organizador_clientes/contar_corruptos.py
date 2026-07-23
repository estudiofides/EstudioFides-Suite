"""
Cuenta y lista los archivos marcados como ERROR_LECTURA (no se pudieron
abrir: corruptos, protegidos con contraseña, formato raro).

Uso:
    cd ~/Documents/EstudioFides-Suite/organizador_clientes
    python3 contar_corruptos.py
"""
import sqlite3
from pathlib import Path

DB = Path(__file__).parent / "database" / "organizador.db"

conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM archivos WHERE metodo = 'ERROR_LECTURA'")
total = cur.fetchone()[0]
print(f"Total ERROR_LECTURA: {total:,}\n")

cur.execute("""
    SELECT extension, COUNT(*) FROM archivos
    WHERE metodo = 'ERROR_LECTURA'
    GROUP BY extension
    ORDER BY COUNT(*) DESC
""")
for ext, n in cur.fetchall():
    print(f"  {ext:<10} {n:>8,}")

print()
print("Primeros 20 ejemplos:")
cur.execute("""
    SELECT ruta FROM archivos
    WHERE metodo = 'ERROR_LECTURA'
    LIMIT 20
""")
for (ruta,) in cur.fetchall():
    print(f"  {ruta}")

conn.close()
