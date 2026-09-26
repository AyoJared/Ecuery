import os
from dotenv import load_dotenv
from google import genai
from parser import parse_query

load_dotenv()



client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"]
)


question = input("Ask an environmental question: ")

result = parse_query(client, question)

print(result)