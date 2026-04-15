from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
import models

async def get_or_create_user(db: AsyncSession, instagram_id: str):
    """Busca o usuário pelo ID do Instagram. Se não existir, cria um novo."""
    
    # Procura o usuário
    stmt = select(models.Usuario).where(models.Usuario.instagram_id == instagram_id)
    result = await db.execute(stmt)
    usuario = result.scalars().first()
    
    # Se não encontrar, cadastra no banco
    if not usuario:
        usuario = models.Usuario(instagram_id=instagram_id)
        db.add(usuario)
        await db.commit()
        await db.refresh(usuario)
        print(f"🆕 Novo cliente cadastrado no banco: {instagram_id}")
        
    return usuario

async def save_message(db: AsyncSession, usuario_id: int, remetente: str, conteudo: str):
    """Salva uma nova mensagem (seja do cliente ou da IA) no histórico."""
    
    nova_mensagem = models.Mensagem(
        usuario_id=usuario_id,
        remetente=remetente,  # Será "user" ou "ai"
        conteudo=conteudo
    )
    db.add(nova_mensagem)
    await db.commit()
    await db.refresh(nova_mensagem)
    return nova_mensagem

async def get_historico_mensagens(db: AsyncSession, usuario_id: int, limite: int = 10):
    """Pega as últimas 'X' mensagens para dar contexto à IA."""
    
    # Pega de trás pra frente (as mais recentes) limitando a 10 para não gastar muitos tokens
    stmt = select(models.Mensagem)\
        .where(models.Mensagem.usuario_id == usuario_id)\
        .order_by(models.Mensagem.id.desc())\
        .limit(limite)
        
    result = await db.execute(stmt)
    mensagens = result.scalars().all()
    
    # Inverte a lista para a IA ler na ordem cronológica correta (da mais antiga pra mais nova)
    return list(reversed(mensagens))