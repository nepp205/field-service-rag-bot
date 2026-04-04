import sys
import os

# Add the DB directory to the path so we can import rag
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rag import get_context

def retrieve_context(query: str) -> str:
    """
    Retrieve context from the vector database for a given query.
    
    Args:
        query (str): The search query
        
    Returns:
        str: The context retrieved from the vector database
    """
    context = get_context(query)
    return context


if __name__ == "__main__":
    # Example usage
    query = "Wie wechsle ich die Heizung in meiner Siemens Waschmaschine?"
    context = retrieve_context(query)
    print(context)
