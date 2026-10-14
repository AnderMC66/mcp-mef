"""Motor de búsqueda para MCP-MEF: Búsqueda de Texto Completo (FTS5) y Búsqueda Vectorial Semántica.

Implementa:
1. `mef_fts_search`: Búsqueda de texto completo usando SQLite FTS5 con ponderación BM25.
2. `mef_vector_search`: Búsqueda por similitud vectorial (TF-IDF subword/n-gram + similitud coseno con numpy),
   permitiendo coincidencia semántica y conceptual sobre nombres de proyectos, obras, actividades y clasificadores.
3. `mef_create_search_index`: Creación e indexación automática de tablas locales.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import Counter
from typing import Any

import numpy as np

from . import core


def _limpiar_texto(texto: str) -> str:
    if not texto:
        return ""
    texto = str(texto).lower()
    # Reemplazo de caracteres diacríticos
    reemplazos = (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ü", "u"), ("ñ", "n"))
    for a, b in reemplazos:
        texto = texto.replace(a, b)
    texto = re.sub(r"[^\w\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _extraer_ngrams(texto: str, n_range=(3, 5)) -> list[str]:
    """Genera n-gramas de caracteres a nivel de subpalabras y palabras para embeddings locales robustos."""
    texto_limpio = _limpiar_texto(texto)
    tokens = texto_limpio.split()
    ngrams: list[str] = list(tokens)  # palabras completas
    for token in tokens:
        if len(token) >= 3:
            for n in range(n_range[0], min(n_range[1] + 1, len(token) + 1)):
                for i in range(len(token) - n + 1):
                    ngrams.append(token[i:i + n])
    return ngrams


class LocalVectorIndex:
    """Índice vectorial liviano y autónomo basado en representaciones TF-IDF / Subword n-grams.

    Permite calcular similitud coseno de alta velocidad mediante numpy sin dependencias externas pesadas.
    """

    def __init__(self, vocab_size: int = 5000):
        self.vocab_size = vocab_size
        self.vocab: dict[str, int] = {}
        self.idf: np.ndarray | None = None
        self.doc_vectors: np.ndarray | None = None
        self.doc_ids: list[Any] = []
        self.doc_texts: list[str] = []

    def fit_transform(self, documents: list[tuple[Any, str]]):
        """Entrena el vocabulario y genera la matriz de vectores para los documentos."""
        doc_counters: list[Counter] = []
        df_counter: Counter = Counter()

        for doc_id, text in documents:
            ngrams = _extraer_ngrams(text)
            cnt = Counter(ngrams)
            doc_counters.append(cnt)
            for k in cnt.keys():
                df_counter[k] += 1

        # Seleccionar las características más informativas
        mas_comunes = [word for word, _ in df_counter.most_common(self.vocab_size)]
        self.vocab = {term: idx for idx, term in enumerate(mas_comunes)}
        n_docs = len(documents)
        n_terms = len(self.vocab)

        if n_terms == 0 or n_docs == 0:
            self.idf = np.zeros(0)
            self.doc_vectors = np.zeros((0, 0))
            return

        # Calcular IDF: log(1 + (N / (df + 1))) + 1
        idf_vec = np.zeros(n_terms, dtype=np.float32)
        for term, idx in self.vocab.items():
            df = df_counter[term]
            idf_vec[idx] = math.log((1 + n_docs) / (1 + df)) + 1.0
        self.idf = idf_vec

        # Matriz TF-IDF
        matrix = np.zeros((n_docs, n_terms), dtype=np.float32)
        self.doc_ids = [doc_id for doc_id, _ in documents]
        self.doc_texts = [text for _, text in documents]

        for doc_idx, cnt in enumerate(doc_counters):
            for term, count in cnt.items():
                if term in self.vocab:
                    col_idx = self.vocab[term]
                    tf = 1 + math.log(count) if count > 0 else 0
                    matrix[doc_idx, col_idx] = tf * self.idf[col_idx]

        # Normalización L2 para cálculo instantáneo de similitud coseno
        normas = np.linalg.norm(matrix, axis=1, keepdims=True)
        normas[normas == 0] = 1.0
        self.doc_vectors = matrix / normas

    def query(self, query_text: str, top_k: int = 10) -> list[tuple[Any, str, float]]:
        """Calcula el vector de la consulta y retorna los top_k elementos más similares con su puntaje."""
        if self.doc_vectors is None or len(self.vocab) == 0 or self.doc_vectors.shape[0] == 0:
            return []

        q_ngrams = _extraer_ngrams(query_text)
        cnt = Counter(q_ngrams)
        q_vec = np.zeros(len(self.vocab), dtype=np.float32)

        for term, count in cnt.items():
            if term in self.vocab:
                col_idx = self.vocab[term]
                tf = 1 + math.log(count) if count > 0 else 0
                q_vec[col_idx] = tf * self.idf[col_idx]

        norm_q = np.linalg.norm(q_vec)
        if norm_q == 0:
            return []
        q_vec = q_vec / norm_q

        # Similitud coseno mediante producto punto de vectores normalizados
        scores = np.dot(self.doc_vectors, q_vec)

        # Obtener los mejores top_k índices
        top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in top_indices:
            score = float(scores[idx])
            if score > 0.01:
                results.append((self.doc_ids[idx], self.doc_texts[idx], round(score, 4)))
        return results


def mef_create_search_index(
    table_name: str,
    fields: list[str] | None = None,
) -> str:
    """Crea un índice de búsqueda rápida de texto completo (SQLite FTS5) sobre una tabla local.

    Indexa por defecto columnas textuales relevantes (ej. PRODUCTO_PROYECTO_NOMBRE,
    ACTIVIDAD_ACCION_OBRA_NOMBRE, PLIEGO_NOMBRE, ESPECIFICA_DET_NOMBRE).
    """
    try:
        core._validate_table_name(table_name)
    except ValueError as e:
        return f"Error: {e}"

    with core._db() as conn:
        cur = conn.cursor()
        # Verificar que la tabla existe
        table_exists = cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (table_name,)
        ).fetchone()
        if not table_exists:
            return f"Error: la tabla '{table_name}' no existe en mef_data.db."

        # Detectar columnas si no se especificaron
        cur.execute(f"PRAGMA table_info({core._quote_ident(table_name)})")
        cols_info = cur.fetchall()
        col_names = [r[1] for r in cols_info]

        if not fields:
            candidatos = [
                "PRODUCTO_PROYECTO_NOMBRE", "ACTIVIDAD_ACCION_OBRA_NOMBRE",
                "PLIEGO_NOMBRE", "SECTOR_NOMBRE", "ESPECIFICA_DET_NOMBRE",
                "FUNCION_NOMBRE", "PROGRAMA_PPTO_NOMBRE", "descripcion"
            ]
            fields = [c for c in candidatos if c in col_names]
            if not fields:
                # Tomar las primeras columnas de texto
                fields = [r[1] for r in cols_info if r[2] == "TEXT"][:4]

        if not fields:
            return f"No se encontraron columnas de texto indexables en la tabla '{table_name}'."

        fts_table = f"_fts_{table_name}"
        cols_quoted = ", ".join([core._quote_ident(f) for f in fields])
        
        cur.execute(f"DROP TABLE IF EXISTS {core._quote_ident(fts_table)}")
        cur.execute(f"""
            CREATE VIRTUAL TABLE {core._quote_ident(fts_table)} USING fts5(
                {cols_quoted}
            )
        """)

        # Poblar el índice
        cur.execute(f"""
            INSERT INTO {core._quote_ident(fts_table)}(rowid, {cols_quoted})
            SELECT rowid, {cols_quoted} FROM {core._quote_ident(table_name)}
        """)
        conn.commit()
        total_indexado = cur.execute(f"SELECT count(*) FROM {core._quote_ident(fts_table)}").fetchone()[0]

    return json.dumps({
        "tabla": table_name,
        "tabla_fts": fts_table,
        "columnas_indexadas": fields,
        "filas_indexadas": total_indexado,
        "mensaje": f"Índice FTS5 creado exitosamente con {total_indexado:,} registros."
    }, indent=2, ensure_ascii=False)


def mef_fts_search(
    query: str,
    table_name: str,
    limit: int = 20,
) -> str:
    """Busca en una tabla local usando SQLite FTS5 con ponderación BM25.

    Permite buscar términos como 'hospital huancavelica', 'puente', 'colegio inicial'
    con relevancia clasificada por puntaje BM25. Si el índice no existe, lo genera automáticamente.
    """
    try:
        core._validate_table_name(table_name)
    except ValueError as e:
        return f"Error: {e}"

    fts_table = f"_fts_{table_name}"
    with core._db() as conn:
        cur = conn.cursor()
        existe_fts = cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (fts_table,)
        ).fetchone()

        if not existe_fts:
            # Crear índice FTS5 automáticamente
            mef_create_search_index(table_name)

        # Sanitizar consulta para FTS5
        q_clean = re.sub(r'[^\w\s]', '', query).strip()
        tokens = [t for t in q_clean.split() if len(t) > 1]
        if not tokens:
            return "Error: la consulta de búsqueda está vacía."

        # Expresión FTS5 de prefijo: token1* AND token2*
        match_expr = " AND ".join([f"{t}*" for t in tokens])

        try:
            cur.execute(f"""
                SELECT rowid, rank
                FROM {core._quote_ident(fts_table)}
                WHERE {core._quote_ident(fts_table)} MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (match_expr, limit))
            hits = cur.fetchall()
            if not hits and len(tokens) > 1:
                # Reintento con OR para consultas más amplias
                match_expr_or = " OR ".join([f"{t}*" for t in tokens])
                cur.execute(f"""
                    SELECT rowid, rank
                    FROM {core._quote_ident(fts_table)}
                    WHERE {core._quote_ident(fts_table)} MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """, (match_expr_or, limit))
                hits = cur.fetchall()
        except sqlite3.OperationalError as e:
            return f"Error en búsqueda FTS5: {e}"

        if not hits:
            return json.dumps({
                "consulta": query,
                "tabla": table_name,
                "total_encontrados": 0,
                "coincidencias": []
            }, indent=2, ensure_ascii=False)

        rowids = [h[0] for h in hits]
        placeholders = ",".join(["?"] * len(rowids))
        cur.execute(f"SELECT rowid AS _mef_rowid, * FROM {core._quote_ident(table_name)} WHERE rowid IN ({placeholders})", rowids)
        cols = [d[0] for d in cur.description]
        filas = cur.fetchall()

    # Mapear resultados con puntaje BM25
    rank_map = {h[0]: round(abs(h[1]), 4) for h in hits}
    resultado = []
    for fila in filas:
        row_dict = dict(zip(cols, fila))
        row_id = row_dict.pop("_mef_rowid", None)
        row_dict["_relevancia_bm25"] = rank_map.get(row_id, 0.0)
        resultado.append(row_dict)

    # Ordenar por relevancia BM25
    resultado.sort(key=lambda x: x.get("_relevancia_bm25", 0.0))

    return json.dumps({
        "consulta": query,
        "tabla": table_name,
        "total_encontrados": len(resultado),
        "coincidencias": resultado
    }, indent=2, ensure_ascii=False)


def mef_vector_search(
    query: str,
    table_name: str,
    field: str = "",
    top_k: int = 10,
) -> str:
    """Realiza una búsqueda semántica y de similitud vectorial en una columna de mef_data.db.

    Calcula representaciones vectoriales densas con similitud coseno (vía numpy), lo que permite
    encontrar proyectos, obras o entidades aun cuando no haya coincidencia textual exacta
    (por ejemplo, variaciones morfológicas, conceptos, abreviaturas o errores tipográficos).
    """
    try:
        core._validate_table_name(table_name)
    except ValueError as e:
        return f"Error: {e}"

    with core._db(read_only=True) as conn:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({core._quote_ident(table_name)})")
        cols_info = cur.fetchall()
        col_names = [r[1] for r in cols_info]

        if not field:
            candidatos = [
                "PRODUCTO_PROYECTO_NOMBRE", "ACTIVIDAD_ACCION_OBRA_NOMBRE",
                "PLIEGO_NOMBRE", "ESPECIFICA_DET_NOMBRE", "descripcion"
            ]
            field = next((c for c in candidatos if c in col_names), None)
            if not field:
                field = next((r[1] for r in cols_info if r[2] == "TEXT"), None)

        if not field or field not in col_names:
            return f"Error: no se encontró la columna '{field}' en la tabla '{table_name}'."

        # Cargar valores distintos de la columna para vectorizar sin duplicar memoria
        cur.execute(f"""
            SELECT rowid, {core._quote_ident(field)}
            FROM {core._quote_ident(table_name)}
            WHERE {core._quote_ident(field)} IS NOT NULL AND {core._quote_ident(field)} != ''
            LIMIT 50000
        """)
        registros = cur.fetchall()

    if not registros:
        return f"La tabla '{table_name}' no contiene datos en la columna '{field}'."

    index = LocalVectorIndex(vocab_size=6000)
    index.fit_transform(registros)

    matches = index.query(query, top_k=top_k)
    if not matches:
        return json.dumps({
            "consulta": query,
            "tabla": table_name,
            "campo": field,
            "total_coincidencias": 0,
            "coincidencias": []
        }, indent=2, ensure_ascii=False)

    row_ids = [m[0] for m in matches]
    scores_dict = {m[0]: m[2] for m in matches}

    with core._db(read_only=True) as conn:
        cur = conn.cursor()
        placeholders = ",".join(["?"] * len(row_ids))
        cur.execute(f"SELECT rowid AS _mef_rowid, * FROM {core._quote_ident(table_name)} WHERE rowid IN ({placeholders})", row_ids)
        cols = [d[0] for d in cur.description]
        filas = cur.fetchall()

    resultado = []
    for fila in filas:
        row_dict = dict(zip(cols, fila))
        row_id = row_dict.pop("_mef_rowid", None)
        row_dict["_similitud_vectorial"] = scores_dict.get(row_id, 0.0)
        resultado.append(row_dict)

    resultado.sort(key=lambda x: x.get("_similitud_vectorial", 0.0), reverse=True)

    return json.dumps({
        "consulta": query,
        "tabla": table_name,
        "campo_vectorizado": field,
        "total_coincidencias": len(resultado),
        "coincidencias": resultado
    }, indent=2, ensure_ascii=False)
