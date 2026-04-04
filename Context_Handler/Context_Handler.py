import sys
import os

# Add the DB directory to the path so we can import rag
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rag import get_context

def retrieve_context(query: str, model: str = None) -> str:
    """
    Retrieve context from the vector database for a given query.
    
    Args:
        query (str): The search query
        model (str, optional): The model name to filter PDFs. Only PDFs containing this model name will be searched.
        
    Returns:
        str: The context retrieved from the vector database
    """
    context = get_context(query=query, model=model)
    return context


if __name__ == "__main__":
    # Example usage
    query = "Wie wechsle ich die Heizung in meiner Siemens Waschmaschine?"
    model = "W1"  # Optional: Filtern nach Modellname
    context = retrieve_context(query=query, model=model)
    print(context)
