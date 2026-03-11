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
        self.docs = docs or self.load_sample_docs()

    def load_sample_docs(self) -> List[Dict[str, Any]]:
        """Lädt ein paar Beispiel-Dokumente aus dem `data/` Ordner falls vorhanden.

        Falls keine Dateien gefunden werden, werden zwei statische Dokumente zurückgegeben.
        """
        docs = []
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        # Falls ein data-Verzeichnis im Repo liegt, versuche einfache .txt Dateien zu lesen
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

        Ersetzt später durch Vektor-basiertes Retrieval (Marvin).
        """
        q = query.lower()
        scored = []
        for doc in self.docs:
            text = doc.get("text", "").lower()
            # score = Anzahl der gemeinsamen Wörter (grob)
            score = sum(1 for token in set(q.split()) if token in text)
            scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [doc for score, doc in scored if score > 0]
        # Fallback: wenn keine Treffer, gib die ersten top_k docs zurück
        if not results:
            results = [doc for _, doc in scored[:top_k]]
        return results[:top_k]


class RAG:
    """Kleine RAG-Abstraktion.

    - retriever: Objekt mit retrieve(query, top_k) -> List[docs]
    - llm: Optionales LLM-Objekt; falls None, wird eine einfache Heuristik genutzt.
    """

    def __init__(self, retriever: Optional[Any] = None, llm: Optional[Any] = None):
        self.retriever = retriever or InMemoryRetriever()
        self.llm = llm

    def connect_marvin(self, connection_info: Dict[str, Any]) -> None:
        """Platzhalter: hier würde man die Verbindung zu Marvins DB/Vektorstore bauen.

        Beispiel: connection_info könnte API-Keys / Endpunkte enthalten. Implementiere
        hier den Austausch, der ein Objekt liefert, das `retrieve(query, top_k)` unterstützt.
        """
        raise NotImplementedError("Implement connection to Marvin's vector DB here")

    def retrieve(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        return self.retriever.retrieve(query, top_k=top_k)

    def generate_answer(self, query: str, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generiert die finale Antwort. Wenn `self.llm` vorhanden ist, leite an die LLM-Chain weiter.

        Rückgabeformat:
            {"content": str(markdown), "source_quote": str, "pdf_url": str}
        """
        if self.llm:
            # TODO: Tobias: hier eure LLM-Chain anrufen, z.B. llm.run(query, docs)
            try:
                return self.llm.generate(query=query, docs=docs)
            except Exception:
                pass

        # Fallback-Heuristik: baue eine einfache Antwort aus den Docs
        content_lines = [f"**Diagnose (gesammelt aus {len(docs)} Quelle/n):**\n"]
        # Einfache nummerierte Handlungsschritte basierend auf Keywords
        content_lines.append("1. Stromversorgung prüfen und Sicherungen kontrollieren.")
        content_lines.append("2. Kühlsystem (Lüfter/Filter) inspizieren und reinigen.")
        content_lines.append("3. Gerät neu starten und Funktionstest durchführen.")
        content_lines.append("4. Falls weiterhin Fehler auftreten: Logs sichern und Support kontaktieren.")

        # Ergänze kurze Sätze aus den relevanten Dokumenten
        for i, d in enumerate(docs[:3], start=1):
            excerpt = d.get("text", "").strip()
            if len(excerpt) > MAX_EXCERPT_LENGTH:
                excerpt = excerpt[:EXCERPT_TRUNCATE_LENGTH].rstrip() + "..."
            content_lines.append(f"\n**Quelle {i}** ({d.get('source','')})\n> {excerpt}")

        content = "\n\n".join(content_lines)

        # Wähle das erste Doc als primäre Quelle
        primary = docs[0] if docs else {}
        source_quote = primary.get("text", "")
        pdf_url = primary.get("pdf_url", "")

        return {"content": content, "source_quote": source_quote, "pdf_url": pdf_url}

    def answer(self, query: str, top_k: int = 3) -> Dict[str, Any]:
        docs = self.retrieve(query, top_k=top_k)
        return self.generate_answer(query, docs)


if __name__ == "__main__":
    # Kleiner Smoke-Test
    rag = RAG()
    print(rag.answer("Gerät schaltet sich ab"))


class SimpleLLM:
    """Ein sehr einfacher LLM-Stub für Entwicklung und Tests (Tobias).

    - Implementiert `generate(query, docs)` und gibt das erwartete dict-Format
      zurück: {content, source_quote, pdf_url}.
    - Tobias: Ersetze diese Klasse später durch eure echte LLM-Chain-Integration.
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
        # Basis-Antwort
        lines = [f"**RAG-Antwort (LLM Stub: {self.name}) für:** {query}\n"]
        lines.append("1. Stromversorgung prüfen (Sicherungen, Anschlüsse).")
        lines.append("2. Kühlsystem prüfen: Lüfter und Filter reinigen.")
        lines.append("3. Gerät neu starten und Funktionstest ausführen.")
        lines.append("4. Wenn Problem bestehen bleibt: Logs sammeln und Support informieren.")

        # Ergänze Auszüge aus Dokumenten
        for i, d in enumerate(docs[:3], start=1):
            excerpt = d.get("text", "").strip()
            if len(excerpt) > MAX_EXCERPT_LENGTH:
                excerpt = excerpt[:EXCERPT_TRUNCATE_LENGTH].rstrip() + "..."
            lines.append(f"\n**Quelle {i}** ({d.get('source','')})\n> {excerpt}")

        content = "\n\n".join(lines)

        primary = docs[0] if docs else {}
        return {"content": content, "source_quote": primary.get("text", ""), "pdf_url": primary.get("pdf_url", "")}


