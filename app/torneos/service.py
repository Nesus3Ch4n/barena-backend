import re
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from app.torneos.models import Torneo, Rama, Categoria, Deporte
from app.torneos.schemas import TorneoCreate, VisibilidadUpdate
from app.shared.errors import AppError, NotFound
from app.auth.models import user_roles

def slugify(text: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return slug[:100] or str(uuid.uuid4())[:8]

async def ensure_organizador_role(db: AsyncSession, user_id: str):
    res = await db.execute(select(user_roles.c.role_id).where(user_roles.c.user_id == user_id, user_roles.c.role_id == "organizador"))
    if not res.first():
        await db.execute(insert(user_roles).values(user_id=user_id, role_id="organizador"))

async def get_deporte_id(db: AsyncSession, deporte_id: str = None, deporte_nombre: str = "volei_playa") -> str:
    if deporte_id:
        res = await db.execute(select(Deporte).where(Deporte.id == deporte_id))
        dep = res.scalar_one_or_none()
        if not dep:
            raise AppError(400, "DEPORTE_NOT_FOUND", "Deporte no existe", {"deporte_id": deporte_id})
        return dep.id
    # by nombre
    res = await db.execute(select(Deporte).where(Deporte.nombre == deporte_nombre))
    dep = res.scalar_one_or_none()
    if dep:
        return dep.id
    # auto-create if not exists (for freemium)
    dep = Deporte(nombre=deporte_nombre, icono="volleyball")
    db.add(dep)
    await db.flush()
    return dep.id

async def create_torneo(db: AsyncSession, user_id: str, data: TorneoCreate) -> dict:
    import unicodedata
    if data.fecha_inicio and data.fecha_fin and data.fecha_fin < data.fecha_inicio:
        raise AppError(400, "FECHAS_INVALIDAS", "fecha_fin debe ser >= fecha_inicio")
    deporte_id = await get_deporte_id(db, data.deporte_id, data.deporte_nombre or "volei_playa")
    base_slug = slugify(data.nombre)
    slug = base_slug
    # ensure unique slug
    counter = 1
    while True:
        res = await db.execute(select(Torneo).where(Torneo.slug == slug))
        if not res.scalar_one_or_none():
            break
        slug = f"{base_slug}-{counter}"
        counter += 1

    torneo = Torneo(
        nombre=data.nombre,
        slug=slug,
        deporte_id=deporte_id,
        organizador_id=user_id,
        fecha_inicio=data.fecha_inicio,
        fecha_fin=data.fecha_fin,
        sede=data.sede,
        ciudad=data.ciudad,
        publico=data.publico,
        estado="borrador",
    )
    db.add(torneo)
    try:
        await db.flush()
    except IntegrityError:
        import uuid as _uuid
        slug = f"{base_slug}-{_uuid.uuid4().hex[:8]}"
        torneo.slug = slug
        await db.flush()
    await ensure_organizador_role(db, user_id)

    ramas_out = []
    for rama_in in data.ramas:
        rama = Rama(torneo_id=torneo.id, tipo=rama_in.tipo, nombre_custom=rama_in.nombre_custom, activa=rama_in.activa)
        db.add(rama)
        await db.flush()
        cats = []
        for cat_in in rama_in.categorias:
            # validate sets_x_partido
            if cat_in.sets_x_partido not in (1,3,5):
                raise AppError(400, "SETS_INVALIDO", "sets_x_partido debe ser 1,3,5")
            if cat_in.puntos_x_set not in (15,21,25):
                raise AppError(400, "PUNTOS_INVALIDO", "puntos_x_set debe ser 15,21,25")
            cat = Categoria(
                rama_id=rama.id,
                nombre=cat_in.nombre,
                formato=cat_in.formato,
                cuadro_perdedores=cat_in.cuadro_perdedores,
                equipos_x_grupo=cat_in.equipos_x_grupo,
                sets_x_partido=cat_in.sets_x_partido,
                puntos_x_set=cat_in.puntos_x_set,
                avance_x_grupo=cat_in.avance_x_grupo,
                criterio_clasif=cat_in.criterio_clasif,
            )
            db.add(cat)
            await db.flush()
            cats.append(cat)
        ramas_out.append((rama, cats))

    await db.flush()
    return {"torneo": torneo, "ramas": ramas_out}

async def get_torneo_detail(db: AsyncSession, torneo_id: str, current_user_id: str = None, is_public: bool = False) -> dict:
    res = await db.execute(select(Torneo).where(Torneo.id == torneo_id))
    torneo = res.scalar_one_or_none()
    if not torneo:
        raise NotFound("TORNEO_NOT_FOUND", "Torneo no existe", {"id": torneo_id})
    # visibility check: if not public and not owner/super_admin, forbid
    # For GET detail we allow if torneo.publico or owner; raw check done in router

    # fetch ramas
    res = await db.execute(select(Rama).where(Rama.torneo_id == torneo.id))
    ramas = res.scalars().all()
    # fetch categorias per rama
    result = []
    for rama in ramas:
        res2 = await db.execute(select(Categoria).where(Categoria.rama_id == rama.id))
        cats = res2.scalars().all()
        result.append((rama, cats))
    return {"torneo": torneo, "ramas": result}

async def list_torneos(db: AsyncSession, user_id: str, is_super: bool):
    if is_super:
        res = await db.execute(select(Torneo).order_by(Torneo.creado_en.desc()))
    else:
        res = await db.execute(select(Torneo).where(Torneo.organizador_id == user_id).order_by(Torneo.creado_en.desc()))
    return res.scalars().all()

async def update_visibilidad(db: AsyncSession, torneo_id: str, data: VisibilidadUpdate) -> Torneo:
    res = await db.execute(select(Torneo).where(Torneo.id == torneo_id))
    torneo = res.scalar_one_or_none()
    if not torneo:
        raise NotFound("TORNEO_NOT_FOUND", "Torneo no existe", {"id": torneo_id})
    vis = dict(torneo.config_visibilidad or {})
    update = data.model_dump(exclude_unset=True)
    for k, v in update.items():
        if k == "publico":
            torneo.publico = v
        else:
            vis[k] = v
    torneo.config_visibilidad = vis
    await db.flush()
    return torneo

async def get_public_by_slug(db: AsyncSession, slug: str):
    res = await db.execute(select(Torneo).where(Torneo.slug == slug, Torneo.publico == True))
    torneo = res.scalar_one_or_none()
    if not torneo:
        raise NotFound("TORNEO_NOT_PUBLIC", "Torneo no es público o no existe", {"slug": slug})
    return torneo
