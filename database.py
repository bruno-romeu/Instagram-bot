import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Cria o "motor" do banco de dados (echo=True faz ele printar o SQL no terminal para debug)
engine = create_async_engine(DATABASE_URL, echo=False)

# Cria a fábrica de sessões (cada vez que o bot responder uma DM, ele abre e fecha uma sessão)
AsyncSessionLocal = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

# Classe base que usaremos para criar as nossas tabelas
Base = declarative_base()

# Função que o FastAPI vai usar para "pegar" o banco de dados em cada requisição
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session