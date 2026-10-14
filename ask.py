import ollama

response = ollama.chat(
    model="llama3.2",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Sources:\n{context}\n\nQuestion: {question}"},
    ],
)
print("\nANSWER:\n" + response["message"]["content"])
