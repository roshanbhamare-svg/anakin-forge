import os
from dotenv import load_dotenv
from groq import Groq

def list_models():
    load_dotenv()
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    models = client.models.list()
    for m in models.data:
        print(m.id)

if __name__ == "__main__":
    list_models()
