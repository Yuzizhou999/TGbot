import os
from typing import List, Optional

from langchain_community.vectorstores import FAISS
from langchain.embeddings.base import Embeddings as LCEmbeddings
from sentence_transformers import SentenceTransformer

from gemini import call_gemini


class SentenceTransformersAdapter(LCEmbeddings):
    """Embeddings adapter wrapping sentence-transformers and implementing LangChain's Embeddings API."""

    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        self.model = SentenceTransformer(model_name)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # returns list of float vectors
        embs = self.model.encode(texts, convert_to_numpy=True)
        return [e.tolist() for e in embs]

    def embed_query(self, text: str) -> List[float]:
        e = self.model.encode([text], convert_to_numpy=True)[0]
        return e.tolist()


class RAGService:
    def __init__(self, persist_path: str = 'data/faiss_index', embedding_model: str = 'all-MiniLM-L6-v2'):
        self.persist_path = persist_path
        self.embedding_model_name = embedding_model
        self.embeddings: Optional[SentenceTransformersAdapter] = None
        self.index = None

    def init(self):
        """Initialize embeddings and load persisted FAISS index if present."""
        # initialize embeddings
        if self.embeddings is None:
            self.embeddings = SentenceTransformersAdapter(self.embedding_model_name)

        # load persisted index if any
        if os.path.exists(self.persist_path) and os.listdir(self.persist_path):
            self.index = FAISS.load_local(self.persist_path, self.embeddings, allow_dangerous_deserialization=True)

    def ingest_texts(self, texts: List[str], metadatas: Optional[List[dict]] = None):
        """Ingest a list of texts into the FAISS index and persist it."""
        if not texts:
            return

        if self.embeddings is None:
            self.init()

        if metadatas is None:
            metadatas = [{'source': f'doc_{i}'} for i in range(len(texts))]

        if self.index is None:
            # create new index
            self.index = FAISS.from_texts(texts, self.embeddings, metadatas=metadatas)
        else:
            # add to existing
            self.index.add_texts(texts, metadatas=metadatas)

        os.makedirs(self.persist_path, exist_ok=True)
        self.index.save_local(self.persist_path)

    def similarity_search(self, query: str, k: int = 4):
        if self.index is None:
            raise RuntimeError('Index not initialized. Call ingest_texts or init first.')
        return self.index.similarity_search(query, k=k)

    async def generate_answer(self, question: str, docs, system_instruction: Optional[str] = None) -> str:
        """Build a prompt including retrieved docs and call Gemini to generate an answer."""
        ctx_parts = []
        for i, d in enumerate(docs):
            page = getattr(d, 'page_content', None) or (d.get('text') if isinstance(d, dict) else str(d))
            meta = getattr(d, 'metadata', None) or (d.get('metadata') if isinstance(d, dict) else {})
            src = meta.get('source', f'doc_{i}') if meta else f'doc_{i}'
            ctx_parts.append(f"[Source: {src}]\n{page}")

        context = "\n\n".join(ctx_parts)
        prompt = (
            "你是一个专门回答桌游规则与玩法的助理。参考下面的材料来回答问题，尽量给出清晰步骤与要点，并在回答末尾列出引用来源。\n\n"
            f"材料:\n{context}\n\n问题: {question}\n\n请用中文回答。"
        )

        return await call_gemini(prompt, system_instruction=system_instruction)


def load_sample_texts(sample_dir: str = 'sample_docs') -> List[str]:
    out: List[str] = []
    if not os.path.exists(sample_dir):
        return out
    for fn in os.listdir(sample_dir):
        fp = os.path.join(sample_dir, fn)
        if os.path.isfile(fp):
            try:
                with open(fp, 'r', encoding='utf-8') as f:
                    out.append(f.read())
            except Exception:
                continue
    return out


if __name__ == '__main__':
    import argparse
    import asyncio

    parser = argparse.ArgumentParser()
    parser.add_argument('cmd', choices=['ingest', 'query'])
    parser.add_argument('--persist', default='data/faiss_index')
    parser.add_argument('--texts_dir', default='sample_docs')
    parser.add_argument('--question', default='')
    args = parser.parse_args()

    svc = RAGService(persist_path=args.persist)
    if args.cmd == 'ingest':
        texts = load_sample_texts(args.texts_dir)
        if not texts:
            print('No sample texts found')
        else:
            svc.ingest_texts(texts)
            print('Ingested', len(texts))
    else:
        if not args.question:
            print('Please supply --question')
        else:
            svc.init()
            docs = svc.similarity_search(args.question, k=4)
            ans = asyncio.run(svc.generate_answer(args.question, docs))
            print(ans)
