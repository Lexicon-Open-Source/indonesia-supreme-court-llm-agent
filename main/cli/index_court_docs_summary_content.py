import typer
from utility.runtime import coroutine_wrapper
from sqlmodel import Field, SQLModel, select
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from settings import get_settings, SUPREME_COURT_CASE_COLLECTION
from sqlalchemy.sql.operators import is_not
from langchain_qdrant import QdrantVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams
from langchain_core.documents import Document

app = typer.Typer()


class Cases(SQLModel, table=True):
    id: str = Field(primary_key=True)
    source: str
    decision_number: str
    summary: str | None
    summary_en: str | None
    summary_formatted: str | None
    summary_formatted_en: str | None


async def get_paged_docs(session, offset: int, limit: int) -> list:
    paged_result_iterator = await session.exec(
        select(Cases)
        .where(is_not(Cases.summary_formatted_en, None))
        .where(Cases.source == "Indonesia Supreme Court")
        .offset(offset)
        .limit(limit)
    )

    paged_results = [result for result in paged_result_iterator]
    return paged_results


@app.command()
@coroutine_wrapper
async def main():
    offset = 0
    limit = 5
    indexed_count = 0

    case_db_engine = create_async_engine(
        f"postgresql+asyncpg://{get_settings().db_user}:{get_settings().db_pass}@{get_settings().db_addr}/lexicon_bo",
        future=True,
    )

    # Set up the session outside the loop
    async_case_db_session = sessionmaker(bind=case_db_engine, class_=AsyncSession)

    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100,
        separators=["\n\n", "\n", ".", "?", "!", " ", ""],
    )

    try:
        # Set up Qdrant client and collection
        client = QdrantClient(path=get_settings().qdrant_filepath)
        try:
            if client.collection_exists(SUPREME_COURT_CASE_COLLECTION):
                print(
                    f"found existing `{SUPREME_COURT_CASE_COLLECTION}` collection, clearing old index"
                )
                client.delete_collection(SUPREME_COURT_CASE_COLLECTION)

            client.create_collection(
                collection_name=SUPREME_COURT_CASE_COLLECTION,
                vectors_config=VectorParams(size=3072, distance=Distance.COSINE),
            )
        finally:
            client.close()

        vector_store = QdrantVectorStore.from_existing_collection(
            embedding=embeddings,
            collection_name=SUPREME_COURT_CASE_COLLECTION,
            path=get_settings().qdrant_filepath,
        )

        # Database session context manager
        async with async_case_db_session() as session:
            while True:
                print(f"iterating cases database with limit {limit} and offset {offset}")
                paged_results = await get_paged_docs(
                    session=session, offset=offset, limit=limit
                )

                if not paged_results:
                    print("finished iteration")
                    break

                for case in paged_results:
                    splitted_docs = text_splitter.split_text(case.summary_formatted)

                    vector_store_docs = [
                        Document(
                            page_content=text_split,
                            metadata={
                                "decision_number": case.decision_number,
                                "full_summary": case.summary_formatted,
                            },
                        )
                        for text_split in splitted_docs
                    ]

                    await vector_store.aadd_documents(documents=vector_store_docs)

                offset += limit
                indexed_count += len(paged_results)

                print(f"indexed docs vector:{indexed_count}")
    finally:
        # Ensure the DB engine is disposed properly
        await case_db_engine.dispose()


if __name__ == "__main__":
    app()
