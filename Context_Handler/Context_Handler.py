# gehört zu Context_Handler
# Das Context_Handler directory wurde vollständig von Marvin Palsbröker erstellt
 
from rag import get_context

# Wrapper für rag.py
def retrieve_context(query: str, model: str = None) -> str:
    """
    Retrieve context from the vector database for a given query.
    
    Args:
        query (str): The search query
        model (str, optional): The model name to filter PDFs. Only PDFs containing this model name will be searched.
        
    Returns:
        str: The context retrieved from the vector database
    """
    # Übergibt Suchanfrage und optionalen Modellfilter direkt an das RAG-Modul
    context = get_context(query=query, model=model)
    return context


if __name__ == "__main__":
    # Beispiel und Test
    query = "Mein Geschirrspüler zeigt den Fehler F-404 an was soll ich tun?"
    model = "pfd 401" # Optional: Filtern nach Modellname
    context = retrieve_context(query=query, model=model)
    print(context)
