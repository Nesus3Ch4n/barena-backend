import uuid, random, string
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, update
from app.equipos.models import Equipo
from app.torneos.models import Categoria, Torneo, Rama
from app.atletas.models import Atleta
from app.shared.errors import AppError, NotFound
from app.equipos.schemas import EquipoCreate

def gen_codigo():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

async def verify_torneo_owner(db: AsyncSession, torneo_id: str, user_id: str, is_super: bool):
    res = await db.execute(select(Torneo).where(Torneo.id == torneo_id))
    torneo = res.scalar_one_or_none()
    if not torneo:
        raise NotFound("TORNEO_NOT_FOUND", "Torneo no existe", {"id": torneo_id})
    if torneo.organizador_id != user_id and not is_super:
        raise AppError(403, "FORBIDDEN", "No eres organizador de este torneo")
    return torneo

async def verify_categoria_in_torneo(db: AsyncSession, categoria_id: str, torneo_id: str):
    # categoria -> rama -> torneo
    res = await db.execute(select(Categoria).where(Categoria.id == categoria_id))
    cat = res.scalar_one_or_none()
    if not cat:
        raise NotFound("CATEGORIA_NOT_FOUND", "Categoria no existe", {"id": categoria_id})
    res2 = await db.execute(select(Rama).where(Rama.id == cat.rama_id, Rama.torneo_id == torneo_id))
    rama = res2.scalar_one_or_none()
    if not rama:
        raise AppError(400, "CATEGORIA_NO_PERTENECE", "Categoria no pertenece a este torneo")
    return cat

async def create_equipo(db: AsyncSession, torneo_id: str, data: EquipoCreate, user_id: str, is_super: bool) -> Equipo:
    torneo = await verify_torneo_owner(db, torneo_id, user_id, is_super)
    cat = await verify_categoria_in_torneo(db, data.categoria_id, torneo_id)
    # validar atletas: debe haber 2 titulares
    titulares = [a for a in data.atletas if a.posicion == "titular"]
    if len(titulares) != 2:
        raise AppError(400, "ATLETAS_TITULARES_INVALIDO", "Equipo debe tener exactamente 2 titulares")
    # check duplicado nombre en categoria
    res = await db.execute(select(Equipo).where(Equipo.categoria_id == data.categoria_id, Equipo.nombre == data.nombre))
    if res.scalar_one_or_none():
        raise AppError(409, "EQUIPO_DUPLICADO", "Ya existe equipo con ese nombre en la categoria", {"nombre": data.nombre})

    equipo = Equipo(categoria_id=data.categoria_id, nombre=data.nombre, ciudad=data.ciudad, foto_url=data.foto_url, estado="pendiente")
    db.add(equipo)
    await db.flush()

    for atleta_in in data.atletas:
        codigo = gen_codigo()
        # ensure unique codigo
        for _ in range(3):
            res = await db.execute(select(Atleta).where(Atleta.codigo_reclamo == codigo))
            if not res.scalar_one_or_none():
                break
            codigo = gen_codigo()
        atleta = Atleta(equipo_id=equipo.id, nombre_completo=atleta_in.nombre_completo, posicion=atleta_in.posicion, doc_identidad=atleta_in.doc_identidad, codigo_reclamo=codigo)
        db.add(atleta)
    await db.flush()
    return equipo

async def list_equipos(db: AsyncSession, torneo_id: str, categoria_id: str = None, grupo_id: str = None, estado: str = None):
    # necesita verificar torneo existe pero no owner check for reading (public logic?)
    query = select(Equipo).join(Categoria, Equipo.categoria_id == Categoria.id).join(Rama, Categoria.rama_id == Rama.id).where(Rama.torneo_id == torneo_id)
    if categoria_id:
        query = query.where(Equipo.categoria_id == categoria_id)
    if grupo_id:
        query = query.where(Equipo.grupo_id == grupo_id)
    if estado:
        query = query.where(Equipo.estado == estado)
    res = await db.execute(query)
    return res.scalars().all()

async def aprobar_equipo(db: AsyncSession, equipo_id: str, grupo_id: str = None, seed: int = None, torneo_id: str = None, user_id: str = None, is_super: bool = False):
    res = await db.execute(select(Equipo).where(Equipo.id == equipo_id))
    equipo = res.scalar_one_or_none()
    if not equipo:
        raise NotFound("EQUIPO_NOT_FOUND", "Equipo no existe", {"id": equipo_id})
    # verify owner via torneo
    if torneo_id:
        await verify_torneo_owner(db, torneo_id, user_id, is_super)
    # verify grupo pertenece a misma categoria
    if grupo_id:
        from app.torneos.models import Grupo
        res2 = await db.execute(select(Grupo).where(Grupo.id == grupo_id, Grupo.categoria_id == equipo.categoria_id))
        if not res2.scalar_one_or_none():
            raise AppError(400, "GRUPO_INVALIDO", "Grupo no pertenece a la categoria del equipo")
        equipo.grupo_id = grupo_id
    if seed is not None:
        equipo.seed = seed
    equipo.estado = "aprobado"
    await db.flush()
    return equipo

async def rechazar_equipo(db: AsyncSession, equipo_id: str):
    res = await db.execute(select(Equipo).where(Equipo.id == equipo_id))
    equipo = res.scalar_one_or_none()
    if not equipo:
        raise NotFound("EQUIPO_NOT_FOUND", "Equipo no existe", {"id": equipo_id})
    equipo.estado = "eliminado"
    await db.flush()
    return equipo

async def get_equipo_atletas(db: AsyncSession, equipo_id: str):
    res = await db.execute(select(Atleta).where(Atleta.equipo_id == equipo_id))
    return res.scalars().all()
