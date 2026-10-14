"""
Helper para usar Ollama local (OpenAI-compatible) em qualquer script Python.

Uso:
    from inspectra.llm.client import chat, embed

    resp = chat("gemma4:latest", "Resuma este dossiê", parent_model="ze")
    print(resp)
"""
import json
import urllib.request
import urllib.error
from typing import List, Dict, Optional

OLLAMA_URL = "http://127.0.0.1:11434"


def listar_modelos() -> List[Dict]:
    with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=10) as r:
        return json.loads(r.read())["models"]


def chat(
    model: str,
    prompt: str,
    *,
    system: Optional[str] = None,
    parent_model: Optional[str] = None,
    temperatura: float = 0.7,
    num_ctx: Optional[int] = None,
    stream: bool = False,
    tools: Optional[List[Dict]] = None,
    history: Optional[List[Dict]] = None,
) -> Dict:
    """Chat simples. Retorna dict da mensagem do Ollama (com .content, .tool_calls)."""
    if history is None:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
    else:
        msgs = list(history)
        if system and (not msgs or msgs[0].get("role") != "system"):
            msgs = [{"role": "system", "content": system}] + msgs
        if prompt:
            msgs.append({"role": "user", "content": prompt})

    body = {"model": model, "messages": msgs, "stream": False}
    opts = {}
    if temperatura is not None:
        opts["temperature"] = temperatura
    if num_ctx is not None:
        opts["num_ctx"] = num_ctx
    if opts:
        body["options"] = opts
    if tools:
        body["tools"] = tools

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read())
    return data["message"]


def chat_text(model: str, prompt: str, **kwargs) -> str:
    """Atalho que retorna apenas o texto da resposta."""
    msg = chat(model, prompt, **kwargs)
    return msg.get("content", "")


def embed(texto: str, model: str = "nomic-embed-text:latest") -> List[float]:
    body = {"model": model, "prompt": texto}
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/embeddings",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["embedding"]


def info_modelo(model: str) -> Dict:
    """Tamanho, família, contexto, etc."""
    for m in listar_modelos():
        if m["name"] == model or m["name"].split(":")[0] == model:
            return m["details"]
    return {}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Modelos disponíveis:")
        for m in listar_modelos():
            d = m["details"]
            print(f"  {m['name']:30s} {d.get('parameter_size','?'):>5}  ctx={d.get('context_length','?')}")
        sys.exit(0)
    modelo = sys.argv[1]
    prompt = sys.argv[2] if len(sys.argv) > 2 else "Diga 'ok' em portugues."
    print(f"[{modelo}] {prompt}\n---")
    print(chat(modelo, prompt))