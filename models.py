from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database import Base

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    instagram_id = Column(String, unique=True, index=True) # O ID que a Meta nos manda
    criado_em = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relação: Um usuário pode ter várias mensagens
    mensagens = relationship("Mensagem", back_populates="usuario", cascade="all, delete-orphan")

class Mensagem(Base):
    __tablename__ = "mensagens"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    remetente = Column(String) # Vamos salvar como "user" ou "ai"
    conteudo = Column(Text)
    criado_em = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relação: Essa mensagem pertence a um usuário
    usuario = relationship("Usuario", back_populates="mensagens")