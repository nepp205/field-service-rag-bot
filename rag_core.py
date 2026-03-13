"""Minimaler RAG-Scaffold für das Projekt.

Ziel: Eine kleine, testbare Schicht bereitstellen, die später an Marvins
Dokumenten-/Vektor-Datenbank und an die echte LLM-Chain (Tobias) angeschlossen
werden kann.

Benutzung (vereinfachtes Beispiel):
    from rag_core import RAG, InMemoryRetriever
    rag = RAG(retriever=InMemoryRetriever())
    answer = rag.answer("Mein Gerät schaltet ab")

Die aktuelle Implementierung ist dependency-frei und nutzt eine einfache
Textsuche als Retriever; die Antworten werden aus den Top-Dokumenten
zusammengesetzt. Ersetze später den Retriever durch einen Vector-Store-Connector
(z.B. FAISS, Pinecone, Milvus) und implementiere `llm`-Integration in
`RAG.generate_answer`.
"""

from typing import List, Dict, Optional, Any
import os


class InMemoryRetriever:
    """Sehr einfacher Retriever für Tests.

    Hält eine Liste von Dokumenten (dict mit keys: 'id','text','source','pdf_url')
    und liefert die Dokumente mit den meisten Keyword-Treffern zurück.
    """

    def __init__(self, docs: Optional[List[Dict[str, Any]]] = None):
        # Use provided docs or fall back to loading sample documents
        self.docs = docs or self.load_sample_docs()

    def load_sample_docs(self) -> List[Dict[str, Any]]:
        """Lädt ein paar Beispiel-Dokumente aus dem `data/` Ordner falls vorhanden.

        Falls keine Dateien gefunden werden, werden zwei statische Dokus zurückgegeben.
        """
        docs = []
        data_dir = os.path.join(os.path.dirname(__file__), "data")

        # If a data directory exists, try to read plain-text files from it
        if os.path.isdir(data_dir):
            for fn in os.listdir(data_dir):
                if fn.lower().endswith(".txt"):
                    path = os.path.join(data_dir, fn)
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            text = f.read()
                        docs.append({"id": fn, "text": text, "source": fn, "pdf_url": ""})
                    except Exception:
                        continue

        # Fallback: built-in sample documents when no data directory is present
        if not docs:
            docs = [
                {
                    "id": "manual_xyz",
                    "text": "E-404 tritt bei Überhitzung auf. Kühler reinigen und Filter prüfen.",
                    "source": "Handbuch XYZ - S.12",
                    "pdf_url": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
                },
                {
                    "id": "service_notes",
                    "text": "Beim Kontrolltest: Stromversorgung prüfen, Lüfterausfall als Ursache prüfen.",
                    "source": "Service-Notes",
                    "pdf_url": "",
                },
            ]

        return docs

    def retrieve(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Sehr rudimentäre Retrieval-Strategie: Keyword-Count.

        Scores every document by counting how many query tokens appear in its
        text, then returns the top_k highest-scoring documents.
        Replace with vector-based retrieval (Marvin) once the DB is ready.
        """
        q = query.lower()
        scored = []
        for doc in self.docs:
            text = doc.get("text", "").lower()
            # Score = total occurrences of each query token in the document text
            score = sum(text.count(token) for token in q.split())
            scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)

        # Only keep documents that matched at least one query token
        results = [doc for score, doc in scored if score > 0]

        # Fallback: if no keyword matches, return the first top_k documents
        if not results:
            results = [doc for _, doc in scored[:top_k]]
        return results[:top_k]


class RAG:
    """Kleine RAG-Abstraktion (Retrieve-Augmented Generation).

    Attributes:
        retriever: Object with a ``retrieve(query, top_k)`` method that
            returns a list of document dicts.  Defaults to InMemoryRetriever.
        llm: Optional LLM object with a ``generate(query, docs)`` method.
            If None, a simple heuristic is used to build the answer.
    """

    def __init__(self, retriever: Optional[Any] = None, llm: Optional[Any] = None):
        self.retriever = retriever or InMemoryRetriever()
        self.llm = llm

    def connect_marvin(self, connection_info: Dict[str, Any]) -> None:
        """Platzhalter: hier würde man die Verbindung zu Marvins DB/Vektorstore bauen.

        Args:
            connection_info: Dict mit API-Keys / Endpunkten o.Ä.
                Implementiere hier den Austausch, der ein Objekt liefert,
                das ``retrieve(query, top_k)`` unterstützt.
        """
        raise NotImplementedError("Implement connection to Marvin's vector DB here")

    def retrieve(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Delegate retrieval to the configured retriever."""
        return self.retriever.retrieve(query, top_k=top_k)

    def generate_answer(self, query: str, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generiert die finale Antwort.

        Wenn ``self.llm`` vorhanden ist, wird an die LLM-Chain weitergeleitet.
        Andernfalls wird eine einfache heuristische Antwort aus den Docs gebaut.

        Returns:
            dict with keys:
                - ``content`` (str, Markdown)
                - ``source_quote`` (str)
                - ``pdf_url`` (str)
        """
        if self.llm:
            # TODO (Tobias): call your LLM chain here, e.g. llm.run(query, docs)
            try:
                return self.llm.generate(query=query, docs=docs)
            except Exception:
                pass

        # --- Heuristic fallback: build a simple answer from the retrieved docs ---
        content_lines = [f"**Diagnose (gesammelt aus {len(docs)} Quelle/n):**\n"]

        # Generic numbered action steps for field-service troubleshooting
        content_lines.append("1. Stromversorgung prüfen und Sicherungen kontrollieren.")
        content_lines.append("2. Kühlsystem (Lüfter/Filter) inspizieren und reinigen.")
        content_lines.append("3. Gerät neu starten und Funktionstest durchführen.")
        content_lines.append("4. Falls weiterhin Fehler auftreten: Logs sichern und Support kontaktieren.")

        # Append short excerpts from the top-ranked documents
        for i, d in enumerate(docs[:3], start=1):
            excerpt = d.get("text", "").strip()
            if len(excerpt) > 200:
                excerpt = excerpt[:197].rstrip() + "..."
            content_lines.append(f"\n**Quelle {i}** ({d.get('source','')})\n> {excerpt}")

        content = "\n\n".join(content_lines)

        # Use the highest-ranked document as the primary source reference
        primary = docs[0] if docs else {}
        source_quote = primary.get("text", "")
        pdf_url = primary.get("pdf_url", "")

        return {"content": content, "source_quote": source_quote, "pdf_url": pdf_url}

    def answer(self, query: str, top_k: int = 3) -> Dict[str, Any]:
        """End-to-end: retrieve relevant docs and generate an answer.

        Args:
            query: The user's question or error description.
            top_k: Maximum number of documents to retrieve.

        Returns:
            Answer dict as returned by :meth:`generate_answer`.
        """
        docs = self.retrieve(query, top_k=top_k)
        return self.generate_answer(query, docs)


class SimpleLLM:
    """Ein sehr einfacher LLM-Stub für Entwicklung und Tests (Tobias).

    Implementiert ``generate(query, docs)`` und gibt das erwartete dict-Format
    zurück: ``{content, source_quote, pdf_url}``.

    Tobias: Ersetze diese Klasse später durch eure echte LLM-Chain-Integration.
    """

    def __init__(self, name: str = "simple-stub"):
        self.name = name

    def generate(self, query: str, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Erzeugt eine strukturierte, lesbare Antwort aus Query + Docs.

        Diese Implementierung simuliert, wie eine LLM-basierte Antwort aussehen könnte:
        - Nummerierte Handlungsschritte (kurz)
        - Kurze, zitierfähige Ausschnitte aus den Top-Dokumenten
        - Rückgabe des primären pdf_url (falls vorhanden)
        """
        # Build response header with model name and original query
        lines = [f"**RAG-Antwort (LLM Stub: {self.name}) für:** {query}\n"]

        # Numbered troubleshooting steps
        lines.append("1. Stromversorgung prüfen (Sicherungen, Anschlüsse).")
        lines.append("2. Kühlsystem prüfen: Lüfter und Filter reinigen.")
        lines.append("3. Gerät neu starten und Funktionstest ausführen.")
        lines.append("4. Wenn Problem bestehen bleibt: Logs sammeln und Support informieren.")

        # Append truncated excerpts from the top documents
        for i, d in enumerate(docs[:3], start=1):
            excerpt = d.get("text", "").strip()
            if len(excerpt) > 200:
                excerpt = excerpt[:197].rstrip() + "..."
            lines.append(f"\n**Quelle {i}** ({d.get('source','')})\n> {excerpt}")

        content = "\n\n".join(lines)

        primary = docs[0] if docs else {}
        return {"content": content, "source_quote": primary.get("text", ""), "pdf_url": primary.get("pdf_url", "")}


if __name__ == "__main__":
    # Smoke test: run a sample query and print the result
    rag = RAG()
    print(rag.answer("Gerät schaltet sich ab"))
