import re
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from app.torneos.models import Torneo, Rama, Categoria, Deporte
from app.torneos.schemas import TorneoCreate, VisibilidadUpdate
from app.equipos.models import Equipo
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
            # validate sets_x_partido - permite 2 sets con punto de oro
            if cat_in.sets_x_partido not in (1, 2, 3, 5):
                raise AppError(400, "SETS_INVALIDO", "sets_x_partido debe ser 1, 2, 3 o 5")
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
                clasificacion=cat_in.clasificacion,
                criterio_clasif=cat_in.criterio_clasif,
                ranking_general_enabled=cat_in.ranking_general_enabled,
                bracket_tipo=cat_in.bracket_tipo,
                diferencia_dos_puntos=cat_in.diferencia_dos_puntos,
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

async def list_torneos(db: AsyncSession, user_id: str, is_super: bool, is_org: bool = False):
    from sqlalchemy import or_
    if is_super or is_org:
        res = await db.execute(select(Torneo).order_by(Torneo.creado_en.desc()))
    else:
        res = await db.execute(select(Torneo).where(or_(Torneo.organizador_id == user_id, Torneo.publico == True)).order_by(Torneo.creado_en.desc()))
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

async def update_torneo(db: AsyncSession, torneo_id: str, data) -> Torneo:
    from app.torneos.schemas import TorneoUpdate
    assert isinstance(data, TorneoUpdate)
    res = await db.execute(select(Torneo).where(Torneo.id == torneo_id))
    torneo = res.scalar_one_or_none()
    if not torneo:
        raise NotFound("TORNEO_NOT_FOUND", "Torneo no existe", {"id": torneo_id})
    upd = data.model_dump(exclude_unset=True)
    # fechas
    fecha_inicio = upd.get("fecha_inicio", torneo.fecha_inicio)
    fecha_fin = upd.get("fecha_fin", torneo.fecha_fin)
    if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
        raise AppError(400, "FECHAS_INVALIDAS", "fecha_fin debe ser >= fecha_inicio")
    if "nombre" in upd and upd["nombre"] is not None:
        torneo.nombre = upd["nombre"].strip()
        # regenerar slug si cambia nombre
        base = slugify(torneo.nombre)
        slug = base
        counter = 1
        while True:
            q = await db.execute(select(Torneo).where(Torneo.slug == slug, Torneo.id != torneo.id))
            if not q.scalar_one_or_none():
                break
            slug = f"{base}-{counter}"
            counter += 1
        torneo.slug = slug
    if "sede" in upd:
        torneo.sede = upd["sede"].strip() if upd["sede"] else None
    if "ciudad" in upd:
        torneo.ciudad = upd["ciudad"].strip() if upd["ciudad"] else None
    if "fecha_inicio" in upd:
        torneo.fecha_inicio = upd["fecha_inicio"]
    if "fecha_fin" in upd:
        torneo.fecha_fin = upd["fecha_fin"]
    if "publico" in upd and upd["publico"] is not None:
        torneo.publico = upd["publico"]
    if "deporte_nombre" in upd and upd["deporte_nombre"]:
        torneo.deporte_id = await get_deporte_id(db, None, upd["deporte_nombre"])
    await db.flush()
    return torneo

async def get_public_by_slug(db: AsyncSession, slug: str):
    res = await db.execute(select(Torneo).where(Torneo.slug == slug, Torneo.publico == True))
    torneo = res.scalar_one_or_none()
    if not torneo:
        raise NotFound("TORNEO_NOT_PUBLIC", "Torneo no es público o no existe", {"slug": slug})
    return torneo

async def _tabla_jueces_ok(db: AsyncSession) -> bool:
    from sqlalchemy import text as _text
    res = await db.execute(_text("SELECT 1 FROM information_schema.tables WHERE table_name='torneo_jueces'"))
    return bool(res.scalar_one_or_none())

async def _torneo_para_jueces(db: AsyncSession, torneo_id: str, user_id: str, is_super: bool, is_org: bool = False):
    res = await db.execute(select(Torneo).where(Torneo.id == torneo_id))
    torneo = res.scalar_one_or_none()
    if not torneo:
        raise NotFound("TORNEO_NOT_FOUND", "Torneo no existe", {"id": torneo_id})
    if torneo.organizador_id != user_id and not is_super and not is_org:
        raise AppError(403, "FORBIDDEN", "No eres organizador de este torneo")
    if not await _tabla_jueces_ok(db):
        raise AppError(409, "MIGRACION_PENDIENTE", "Aplica la migración 015 para gestionar jueces")
    return torneo

ROLES_OFICIALES = ("juez1", "juez2", "anotador", "asistente_anotador",
                   "linea1", "linea2", "linea3", "linea4")
ROLES_ELEGIBLES_OFICIAL = ("juez_anotador", "organizador", "super_admin")


def _validar_rol_oficial(rol: str | None) -> None:
    if rol is not None and rol not in ROLES_OFICIALES:
        raise AppError(400, "ROL_INVALIDO", f"Rol de oficial inválido: {rol}", {"valid": list(ROLES_OFICIALES)})


async def listar_jueces(db: AsyncSession, torneo_id: str, user_id: str, is_super: bool = False, is_org: bool = False):
    from app.torneos.models import TorneoJuez
    from app.auth.models import User, Profile
    from app.auth.service import get_roles_for_user
    await _torneo_para_jueces(db, torneo_id, user_id, is_super, is_org)
    res = await db.execute(select(TorneoJuez).where(TorneoJuez.torneo_id == torneo_id).order_by(TorneoJuez.creado_en))
    out = []
    for tj in res.scalars().all():
        res2 = await db.execute(select(User).where(User.id == tj.user_id))
        u = res2.scalar_one_or_none()
        if not u:
            continue
        res3 = await db.execute(select(Profile).where(Profile.id == tj.user_id))
        p = res3.scalar_one_or_none()
        out.append({"user_id": tj.user_id, "email": u.email,
                    "nombre_completo": p.nombre_completo if p else None,
                    "rol": getattr(tj, "rol", None),
                    "roles": await get_roles_for_user(db, tj.user_id)})
    return out

async def vincular_juez(db: AsyncSession, torneo_id: str, email: str, user_id: str, is_super: bool, is_org: bool = False, rol: str | None = None):
    from app.torneos.models import TorneoJuez
    from app.auth.models import User
    from app.auth.service import get_roles_for_user
    await _torneo_para_jueces(db, torneo_id, user_id, is_super, is_org)
    res = await db.execute(select(User).where(User.email == email.strip().lower()))
    u = res.scalar_one_or_none()
    if not u:
        raise NotFound("USER_NOT_FOUND", "No existe usuario con ese correo", {"email": email})
    roles = await get_roles_for_user(db, u.id)
    if "juez_anotador" not in roles:
        raise AppError(400, "NO_ES_JUEZ", "El usuario no tiene rol de juez", {"email": email})
    res2 = await db.execute(select(TorneoJuez).where(TorneoJuez.torneo_id == torneo_id, TorneoJuez.user_id == u.id))
    if not res2.scalar_one_or_none():
        db.add(TorneoJuez(torneo_id=torneo_id, user_id=u.id))
        await db.flush()
    if rol is not None:
        await _aplicar_rol(db, torneo_id, u.id, rol)
    return {"user_id": u.id, "email": u.email, "vinculado": True}

async def _aplicar_rol(db: AsyncSession, torneo_id: str, target_user_id: str, rol: str | None):
    """Asigna (o limpia con None) el rol de oficial. Valida ocupación única por rol."""
    from app.torneos.models import TorneoJuez
    _validar_rol_oficial(rol)
    res = await db.execute(select(TorneoJuez).where(TorneoJuez.torneo_id == torneo_id, TorneoJuez.user_id == target_user_id))
    tj = res.scalar_one_or_none()
    if not tj:
        raise NotFound("JUEZ_NO_VINCULADO", "Ese juez no está vinculado", {"user_id": target_user_id})
    if rol is not None:
        res2 = await db.execute(select(TorneoJuez).where(
            TorneoJuez.torneo_id == torneo_id, TorneoJuez.rol == rol,
            TorneoJuez.user_id != target_user_id))
        occ = res2.scalar_one_or_none()
        if occ:
            raise AppError(409, "ROL_OCUPADO", f"El rol {rol} ya está asignado a otro juez",
                           {"rol": rol, "user_id": occ.user_id})
    tj.rol = rol
    await db.flush()
    return tj

async def asignar_rol_juez(db: AsyncSession, torneo_id: str, target_id: str, rol: str | None, user_id: str, is_super: bool, is_org: bool = False):
    """Selecciona un perfil existente como oficial del torneo (lo vincula si hace falta).
    rol=None quita el rol y deja la vinculación legacy intacta."""
    from app.torneos.models import TorneoJuez
    from app.auth.models import User
    from app.auth.service import get_roles_for_user
    await _torneo_para_jueces(db, torneo_id, user_id, is_super, is_org)
    res = await db.execute(select(User).where(User.id == target_id))
    u = res.scalar_one_or_none()
    if not u:
        raise NotFound("USER_NOT_FOUND", "Usuario no existe", {"id": target_id})
    roles = await get_roles_for_user(db, u.id)
    if not any(r in roles for r in ROLES_ELEGIBLES_OFICIAL):
        raise AppError(400, "NO_ES_JUEZ", "El usuario no tiene perfil de juez/organizador", {"id": target_id})
    res2 = await db.execute(select(TorneoJuez).where(TorneoJuez.torneo_id == torneo_id, TorneoJuez.user_id == u.id))
    if not res2.scalar_one_or_none():
        db.add(TorneoJuez(torneo_id=torneo_id, user_id=u.id))
        await db.flush()
    await _aplicar_rol(db, torneo_id, u.id, rol)
    return {"user_id": u.id, "email": u.email, "rol": rol, "vinculado": True}

async def buscar_usuarios_jueces(db: AsyncSession, q: str):
    """Busca perfiles existentes elegibles como oficial (por nombre, email o prefijo de ID)."""
    from sqlalchemy import or_, String, cast
    from app.auth.models import User, Profile
    from app.auth.service import get_roles_for_user
    q = (q or "").strip()
    if len(q) < 2:
        raise AppError(400, "QUERY_CORTA", "Escribe al menos 2 caracteres para buscar")
    like = f"%{q}%"
    res = await db.execute(
        select(User, Profile)
        .join(Profile, Profile.id == User.id)
        .join(user_roles, user_roles.c.user_id == User.id)
        .where(user_roles.c.role_id.in_(ROLES_ELEGIBLES_OFICIAL))
        .where(or_(Profile.nombre_completo.ilike(like), User.email.ilike(like),
                   cast(User.id, String).ilike(f"{q}%")))
        .distinct().limit(20))
    out = []
    for u, p in res.all():
        out.append({"user_id": u.id, "email": u.email,
                    "nombre_completo": p.nombre_completo if p else None,
                    "roles": await get_roles_for_user(db, u.id)})
    return out

async def desvincular_juez(db: AsyncSession, torneo_id: str, target_id: str, user_id: str, is_super: bool, is_org: bool = False):
    from app.torneos.models import TorneoJuez
    await _torneo_para_jueces(db, torneo_id, user_id, is_super, is_org)
    res = await db.execute(select(TorneoJuez).where(TorneoJuez.torneo_id == torneo_id, TorneoJuez.user_id == target_id))
    tj = res.scalar_one_or_none()
    if not tj:
        raise NotFound("JUEZ_NO_VINCULADO", "Ese juez no está vinculado", {"user_id": target_id})
    await db.delete(tj)
    await db.flush()
    return {"user_id": target_id, "vinculado": False}

async def delete_torneo(db: AsyncSession, torneo_id: str):
    res = await db.execute(select(Torneo).where(Torneo.id == torneo_id))
    torneo = res.scalar_one_or_none()
    if not torneo:
        raise NotFound("TORNEO_NOT_FOUND", "Torneo no existe", {"id": torneo_id})
    await db.delete(torneo)
    await db.flush()

async def list_torneos_publicos(db: AsyncSession):
    res = await db.execute(select(Torneo).where(Torneo.publico == True).order_by(Torneo.creado_en.desc()))
    torneos = res.scalars().all()
    ids = [t.id for t in torneos]
    if not ids:
        return []
    ramas = (await db.execute(
        select(Rama.torneo_id, Rama.tipo, Categoria.nombre)
        .join(Categoria, Categoria.rama_id == Rama.id)
        .where(Rama.torneo_id.in_(ids), Rama.activa == True)
    )).all()
    equipos = (await db.execute(
        select(Rama.torneo_id, func.count(Equipo.id))
        .join(Categoria, Categoria.rama_id == Rama.id)
        .join(Equipo, Equipo.categoria_id == Categoria.id)
        .where(Rama.torneo_id.in_(ids), Equipo.estado == "aprobado")
        .group_by(Rama.torneo_id)
    )).all()
    cats_by_torneo = {}
    for torneo_id, tipo, nombre in ramas:
        cats_by_torneo.setdefault(torneo_id, []).append({"tipo": tipo, "nombre": nombre})
    equipos_by_torneo = {tid: count for tid, count in equipos}
    return [{
        "id": t.id, "nombre": t.nombre, "slug": t.slug,
        "ciudad": t.ciudad, "sede": t.sede,
        "fecha_inicio": str(t.fecha_inicio) if t.fecha_inicio else None,
        "fecha_fin": str(t.fecha_fin) if t.fecha_fin else None,
        "estado": t.estado, "publico": t.publico,
        "categorias": cats_by_torneo.get(t.id, []),
        "equipos": equipos_by_torneo.get(t.id, 0),
    } for t in torneos]

# ---------- Ramas ----------
async def create_rama(db: AsyncSession, torneo_id: str, data) -> Rama:
    from app.torneos.schemas import RamaIn
    assert isinstance(data, RamaIn)
    res = await db.execute(select(Torneo).where(Torneo.id == torneo_id))
    if not res.scalar_one_or_none():
        raise NotFound("TORNEO_NOT_FOUND", "Torneo no existe", {"id": torneo_id})
    rama = Rama(torneo_id=torneo_id, tipo=data.tipo, nombre_custom=data.nombre_custom, activa=data.activa)
    db.add(rama)
    await db.flush()
    cats = []
    for cat_in in data.categorias:
        if cat_in.sets_x_partido not in (1, 2, 3, 5):
            raise AppError(400, "SETS_INVALIDO", "sets_x_partido debe ser 1, 2, 3 o 5")
        if cat_in.puntos_x_set not in (15, 21, 25):
            raise AppError(400, "PUNTOS_INVALIDO", "puntos_x_set debe ser 15,21,25")
        cat = Categoria(rama_id=rama.id, nombre=cat_in.nombre, formato=cat_in.formato, cuadro_perdedores=cat_in.cuadro_perdedores, equipos_x_grupo=cat_in.equipos_x_grupo, sets_x_partido=cat_in.sets_x_partido, puntos_x_set=cat_in.puntos_x_set, avance_x_grupo=cat_in.avance_x_grupo, criterio_clasif=cat_in.criterio_clasif, clasificacion=cat_in.clasificacion, ranking_general_enabled=cat_in.ranking_general_enabled, bracket_tipo=cat_in.bracket_tipo, diferencia_dos_puntos=cat_in.diferencia_dos_puntos)
        db.add(cat)
        await db.flush()
        cats.append(cat)
    await db.flush()
    return rama

async def update_rama(db: AsyncSession, rama_id: str, data) -> Rama:
    from app.torneos.schemas import RamaUpdate
    assert isinstance(data, RamaUpdate)
    res = await db.execute(select(Rama).where(Rama.id == rama_id))
    rama = res.scalar_one_or_none()
    if not rama:
        raise NotFound("RAMA_NOT_FOUND", "Rama no existe", {"id": rama_id})
    upd = data.model_dump(exclude_unset=True)
    if "tipo" in upd and upd["tipo"] is not None:
        rama.tipo = upd["tipo"]
    if "nombre_custom" in upd:
        rama.nombre_custom = upd["nombre_custom"].strip() if upd["nombre_custom"] else None
    if "activa" in upd and upd["activa"] is not None:
        rama.activa = upd["activa"]
    await db.flush()
    return rama

async def delete_rama(db: AsyncSession, rama_id: str):
    res = await db.execute(select(Rama).where(Rama.id == rama_id))
    rama = res.scalar_one_or_none()
    if not rama:
        raise NotFound("RAMA_NOT_FOUND", "Rama no existe", {"id": rama_id})
    # check if has categorias with equipos (no rechazados/eliminados)
    from sqlalchemy import text
    cnt = await db.execute(text("SELECT count(*) FROM categorias c JOIN equipos e ON e.categoria_id=c.id WHERE c.rama_id=:rid AND e.estado != 'eliminado'"), {"rid": rama_id})
    n = cnt.scalar()
    if n and n > 0:
        raise AppError(400, "RAMA_HAS_EQUIPOS", "No se puede eliminar rama con equipos inscritos")
    await db.delete(rama)
    await db.flush()

# ---------- Categorias ----------
async def create_categoria(db: AsyncSession, rama_id: str, data) -> Categoria:
    from app.torneos.schemas import CategoriaIn
    assert isinstance(data, CategoriaIn)
    res = await db.execute(select(Rama).where(Rama.id == rama_id))
    if not res.scalar_one_or_none():
        raise NotFound("RAMA_NOT_FOUND", "Rama no existe", {"id": rama_id})
    if data.sets_x_partido not in (1, 2, 3, 5):
        raise AppError(400, "SETS_INVALIDO", "sets_x_partido debe ser 1, 2, 3 o 5")
    if data.puntos_x_set not in (15, 21, 25):
        raise AppError(400, "PUNTOS_INVALIDO", "puntos_x_set debe ser 15,21,25")
    cat = Categoria(rama_id=rama_id, nombre=data.nombre, formato=data.formato, cuadro_perdedores=data.cuadro_perdedores, equipos_x_grupo=data.equipos_x_grupo, sets_x_partido=data.sets_x_partido, puntos_x_set=data.puntos_x_set, avance_x_grupo=data.avance_x_grupo, clasificacion=data.clasificacion, criterio_clasif=data.criterio_clasif, ranking_general_enabled=data.ranking_general_enabled, bracket_tipo=data.bracket_tipo, diferencia_dos_puntos=data.diferencia_dos_puntos)
    db.add(cat)
    await db.flush()
    return cat

async def update_categoria(db: AsyncSession, categoria_id: str, data) -> Categoria:
    from app.torneos.schemas import CategoriaUpdate
    assert isinstance(data, CategoriaUpdate)
    res = await db.execute(select(Categoria).where(Categoria.id == categoria_id))
    cat = res.scalar_one_or_none()
    if not cat:
        raise NotFound("CATEGORIA_NOT_FOUND", "Categoría no existe", {"id": categoria_id})
    upd = data.model_dump(exclude_unset=True)
    reglas = upd.pop("reglas_partido", None)
    for k, v in upd.items():
        if v is not None:
            if k == "nombre" and isinstance(v, str):
                setattr(cat, k, v.strip())
            else:
                setattr(cat, k, v)
    await db.flush()
    if reglas is not None:
        from sqlalchemy import text as _text
        ex = await db.execute(_text("SELECT 1 FROM information_schema.columns WHERE table_name='categorias' AND column_name='reglas_partido'"))
        if not ex.scalar_one_or_none():
            raise AppError(409, "MIGRACION_PENDIENTE", "Aplica la migración 014 para guardar reglas de partido")
        import json as _json
        await db.execute(_text("UPDATE categorias SET reglas_partido = CAST(:r AS JSONB) WHERE id = CAST(:cid AS UUID)"), {"r": _json.dumps(reglas), "cid": categoria_id})
        await db.flush()
    return cat

async def delete_categoria(db: AsyncSession, categoria_id: str):
    res = await db.execute(select(Categoria).where(Categoria.id == categoria_id))
    cat = res.scalar_one_or_none()
    if not cat:
        raise NotFound("CATEGORIA_NOT_FOUND", "Categoría no existe", {"id": categoria_id})
    from sqlalchemy import text
    # check equipos (no rechazados/eliminados)
    cnt = await db.execute(text("SELECT count(*) FROM equipos WHERE categoria_id=:cid AND estado != 'eliminado'"), {"cid": categoria_id})
    n = cnt.scalar()
    if n and n > 0:
        raise AppError(400, "CATEGORIA_HAS_EQUIPOS", "No se puede eliminar categoría con equipos inscritos")
    # check partidos
    cnt2 = await db.execute(text("SELECT count(*) FROM partidos WHERE categoria_id=:cid"), {"cid": categoria_id})
    n2 = cnt2.scalar()
    if n2 and n2 > 0:
        raise AppError(400, "CATEGORIA_HAS_PARTIDOS", "No se puede eliminar categoría con partidos generados")
    await db.delete(cat)
    await db.flush()


# ============================================================
# Tablero de Control del organizador (agregados de solo lectura)
# ============================================================

TIPOS_AMONESTACION = ("tarjeta_amarilla", "tarjeta_roja", "sancion", "descalificacion")
TIPO_AMONESTACION_LABEL = {
    "tarjeta_amarilla": "T. Amarilla",
    "tarjeta_roja": "T. Roja",
    "sancion": "Sanción",
    "descalificacion": "Descalificación",
}


async def _categorias_torneo(db: AsyncSession, torneo_id: str):
    """Pares (rama, categoria) del torneo, ordenados por rama y nombre."""
    from app.torneos.models import Rama, Categoria
    res = await db.execute(select(Rama).where(Rama.torneo_id == torneo_id).order_by(Rama.tipo))
    out = []
    for rama in res.scalars().all():
        res = await db.execute(select(Categoria).where(Categoria.rama_id == rama.id).order_by(Categoria.nombre))
        for cat in res.scalars().all():
            out.append((rama, cat))
    return out


def _rama_vacia(tipo: str) -> dict:
    return {"tipo": tipo, "categorias": 0, "pendiente": 0, "aprobado": 0, "otros": 0,
            "total_equipos": 0, "capacidad": 0, "p_pendiente": 0, "p_en_juego": 0,
            "p_finalizado": 0, "amarillas": 0, "rojas": 0, "sanciones": 0, "descalificaciones": 0}


async def get_tablero(db: AsyncSession, torneo_id: str, user_id: str, is_super: bool, is_org: bool = False) -> dict:
    """Agregados por rama para el Tablero de Control. Solo lectura, sin migraciones.

    Capacidad = suma por categoría CON grupos generados de (nº grupos × equipos_x_grupo);
    las categorías sin fixture se reportan aparte en `sin_fixture` (capacidad 0).
    """
    from app.equipos.models import Equipo
    from app.partidos.models import Partido, PartidoEvento
    from app.torneos.models import Grupo
    torneo = await _torneo_para_jueces(db, torneo_id, user_id, is_super, is_org)
    ramas: dict = {}
    sin_fixture = []
    for rama, cat in await _categorias_torneo(db, torneo_id):
        r = ramas.setdefault(rama.tipo, _rama_vacia(rama.tipo))
        r["categorias"] += 1
        res = await db.execute(select(Equipo).where(Equipo.categoria_id == cat.id, Equipo.estado != "eliminado"))
        equipos = list(res.scalars().all())
        for eq in equipos:
            if eq.estado == "pendiente":
                r["pendiente"] += 1
            elif eq.estado == "aprobado":
                r["aprobado"] += 1
            else:
                r["otros"] += 1
        r["total_equipos"] += len(equipos)
        res = await db.execute(select(Grupo).where(Grupo.categoria_id == cat.id))
        n_grupos = len(list(res.scalars().all()))
        r["capacidad"] += n_grupos * (cat.equipos_x_grupo or 0)
        if not n_grupos:
            sin_fixture.append({"categoria_id": cat.id, "nombre": cat.nombre,
                                "rama_tipo": rama.tipo, "equipos": len(equipos)})
        res = await db.execute(select(Partido).where(Partido.categoria_id == cat.id))
        partidos = list(res.scalars().all())
        for p in partidos:
            if p.estado == "pendiente":
                r["p_pendiente"] += 1
            elif p.estado == "en_juego":
                r["p_en_juego"] += 1
            elif p.estado == "finalizado":
                r["p_finalizado"] += 1
        if partidos:
            res = await db.execute(select(PartidoEvento).where(
                PartidoEvento.partido_id.in_([p.id for p in partidos]),
                PartidoEvento.tipo.in_(TIPOS_AMONESTACION),
                PartidoEvento.revocado == False))
            for e in res.scalars().all():
                if e.tipo == "tarjeta_amarilla":
                    r["amarillas"] += 1
                elif e.tipo == "tarjeta_roja":
                    r["rojas"] += 1
                elif e.tipo == "sancion":
                    r["sanciones"] += 1
                elif e.tipo == "descalificacion":
                    r["descalificaciones"] += 1
    lista = list(ramas.values())
    for r in lista:
        cap = r["capacidad"]
        r["ocupacion_pct"] = round(100 * r["aprobado"] / cap) if cap > 0 else 0
        r["disponibles"] = max(0, cap - r["aprobado"]) if cap > 0 else 0
        r["sanciones_total"] = r["amarillas"] + r["rojas"] + r["sanciones"] + r["descalificaciones"]
    total = {"categorias": 0, "pendiente": 0, "aprobado": 0, "otros": 0, "total_equipos": 0,
             "capacidad": 0, "p_pendiente": 0, "p_en_juego": 0, "p_finalizado": 0,
             "amarillas": 0, "rojas": 0, "sanciones": 0, "descalificaciones": 0}
    for r in lista:
        for k in total:
            total[k] += r[k]
    cap = total["capacidad"]
    total["ocupacion_pct"] = round(100 * total["aprobado"] / cap) if cap > 0 else 0
    total["disponibles"] = max(0, cap - total["aprobado"]) if cap > 0 else 0
    total["sanciones_total"] = total["amarillas"] + total["rojas"] + total["sanciones"] + total["descalificaciones"]
    return {"torneo": {"id": torneo.id, "nombre": torneo.nombre},
            "ramas": lista, "total": total, "sin_fixture": sin_fixture}


def _set_contexto_torneo(evs_ordenados, seq_objetivo: int):
    """Set actual y marcador al momento del evento (misma lógica que estadísticas)."""
    ult_set, n_set, sl, sv = 0, 1, 0, 0
    for e in evs_ordenados:
        if e.seq > seq_objetivo:
            break
        if e.tipo == "set_ganado":
            ult_set, n_set = e.seq, n_set + 1
    for e in evs_ordenados:
        if e.tipo == "punto" and e.seq > ult_set and e.seq <= seq_objetivo:
            if e.lado == "local":
                sl += 1
            else:
                sv += 1
    return n_set, f"{sl}-{sv}"


async def list_amonestaciones_torneo(db: AsyncSession, torneo_id: str, user_id: str, is_super: bool,
                                     is_org: bool = False, tipo: str | None = None,
                                     partido_id: str | None = None, q: str | None = None) -> dict:
    """Bitácora de amonestaciones del torneo para el panel de Control.

    Solo lectura. Excluye eventos revocados. Los contadores son globales del torneo
    (sin filtros); `items` respeta tipo/partido_id/q. Sin migraciones.
    """
    from app.partidos.models import Partido, PartidoEvento
    from app.equipos.models import Equipo
    from app.atletas.models import Atleta
    from app.auth.models import Profile
    await _torneo_para_jueces(db, torneo_id, user_id, is_super, is_org)
    if tipo is not None and tipo not in TIPOS_AMONESTACION:
        raise AppError(400, "TIPO_INVALIDO", f"tipo debe ser uno de {list(TIPOS_AMONESTACION)}")
    pares = await _categorias_torneo(db, torneo_id)
    cat_ids = [c.id for _, c in pares]
    if not cat_ids:
        return {"items": [], "contadores": {"total": 0, "amarillas": 0, "rojas": 0, "sanciones": 0, "descalificaciones": 0}, "total": 0}
    res = await db.execute(select(Partido).where(Partido.categoria_id.in_(cat_ids)))
    partidos = {p.id: p for p in res.scalars().all()}
    if not partidos:
        return {"items": [], "contadores": {"total": 0, "amarillas": 0, "rojas": 0, "sanciones": 0, "descalificaciones": 0}, "total": 0}
    res = await db.execute(select(PartidoEvento).where(
        PartidoEvento.partido_id.in_(list(partidos.keys())),
        PartidoEvento.tipo.in_(TIPOS_AMONESTACION),
        PartidoEvento.revocado == False).order_by(PartidoEvento.creado_at.desc()).limit(1000))
    eventos = list(res.scalars().all())
    contadores = {"total": len(eventos), "amarillas": 0, "rojas": 0, "sanciones": 0, "descalificaciones": 0}
    for e in eventos:
        if e.tipo == "tarjeta_amarilla":
            contadores["amarillas"] += 1
        elif e.tipo == "tarjeta_roja":
            contadores["rojas"] += 1
        elif e.tipo == "sancion":
            contadores["sanciones"] += 1
        elif e.tipo == "descalificacion":
            contadores["descalificaciones"] += 1
    # nombres de equipos / atletas / árbitros
    eids = {x for p in partidos.values() for x in (p.equipo_local_id, p.equipo_visit_id) if x}
    res = await db.execute(select(Equipo).where(Equipo.id.in_(eids))) if eids else None
    noms_eq = {e.id: e.nombre for e in res.scalars().all()} if res is not None else {}
    aids = {e.atleta_id for e in eventos if e.atleta_id}
    res = await db.execute(select(Atleta).where(Atleta.id.in_(aids))) if aids else None
    noms_atl = {a.id: a.nombre_completo for a in res.scalars().all()} if res is not None else {}
    uids = {p.arbitro_id for p in partidos.values() if p.arbitro_id}
    res = await db.execute(select(Profile).where(Profile.id.in_(uids))) if uids else None
    noms_juez = {p.id: p.nombre_completo for p in res.scalars().all()} if res is not None else {}
    # eventos por partido (ordenados) para calcular el set
    por_partido: dict = {}
    if eventos:
        res = await db.execute(select(PartidoEvento).where(
            PartidoEvento.partido_id.in_(list({e.partido_id for e in eventos}))).order_by(
            PartidoEvento.partido_id, PartidoEvento.seq))
        for e in res.scalars().all():
            por_partido.setdefault(e.partido_id, []).append(e)
    items = []
    ql = (q or "").strip().lower()
    for e in eventos:
        if tipo is not None and e.tipo != tipo:
            continue
        if partido_id is not None and e.partido_id != partido_id:
            continue
        p = partidos.get(e.partido_id)
        nom_l = noms_eq.get(p.equipo_local_id, "Por definir") if p else "—"
        nom_v = noms_eq.get(p.equipo_visit_id, "Por definir") if p else "—"
        subtipo = str((e.extra or {}).get("tipo", "")) if e.tipo == "sancion" else ""
        label = TIPO_AMONESTACION_LABEL.get(e.tipo, e.tipo)
        if subtipo:
            label = f"{label} · {subtipo}"
        desc = str((e.extra or {}).get("observacion", "") or "") or (e.razon or "") or label
        nom_atl = noms_atl.get(e.atleta_id, "") if e.atleta_id else ""
        hay = f"{desc} {nom_atl} {nom_l} {nom_v} {label}".lower()
        if ql and ql not in hay:
            continue
        n_set, marcador = _set_contexto_torneo(por_partido.get(e.partido_id, []), e.seq)
        items.append({
            "id": e.id,
            "creada_en": e.creado_at.isoformat() if e.creado_at else None,
            "partido_id": e.partido_id,
            "partido": f"{nom_l} vs {nom_v}" if p else "—",
            "cancha": p.cancha if p else None,
            "tipo": e.tipo,
            "tipo_label": label,
            "atleta": nom_atl or None,
            "set": n_set,
            "marcador": marcador,
            "descripcion": desc,
            "registrado_por": noms_juez.get(p.arbitro_id, "—") if p and p.arbitro_id else "—",
        })
        if len(items) >= 300:
            break
    return {"items": items, "contadores": contadores, "total": len(items)}


async def get_inscripciones(db: AsyncSession, torneo_id: str, user_id: str, is_super: bool, is_org: bool = False) -> dict:
    """Duplas inscritas con atletas y contacto para el módulo Inscripciones. Solo lectura."""
    from app.equipos.models import Equipo
    from app.atletas.models import Atleta
    from app.auth.models import Profile
    from app.torneos.models import Grupo
    await _torneo_para_jueces(db, torneo_id, user_id, is_super, is_org)
    filas = []
    resumen = {"pendiente": 0, "aprobado": 0, "otros": 0, "total": 0}
    for rama, cat in await _categorias_torneo(db, torneo_id):
        res = await db.execute(select(Equipo).where(
            Equipo.categoria_id == cat.id, Equipo.estado != "eliminado").order_by(Equipo.nombre))
        equipos = list(res.scalars().all())
        if not equipos:
            continue
        res = await db.execute(select(Grupo).where(Grupo.categoria_id == cat.id))
        grupos = {g.id: g.nombre for g in res.scalars().all()}
        for eq in equipos:
            res = await db.execute(select(Atleta).where(
                Atleta.equipo_id == eq.id).order_by(Atleta.nombre_completo))
            atls = list(res.scalars().all())
            uids = [a.user_id for a in atls if a.user_id]
            res = await db.execute(select(Profile).where(Profile.id.in_(uids))) if uids else None
            tels = {p.id: p.telefono for p in res.scalars().all()} if res is not None else {}
            atletas = [{"id": a.id, "nombre_completo": a.nombre_completo,
                        "codigo_reclamo": a.codigo_reclamo, "posicion": a.posicion,
                        "tiene_cuenta": bool(a.user_id),
                        "telefono": tels.get(a.user_id)} for a in atls]
            if eq.estado == "pendiente":
                resumen["pendiente"] += 1
            elif eq.estado == "aprobado":
                resumen["aprobado"] += 1
            else:
                resumen["otros"] += 1
            resumen["total"] += 1
            filas.append({"id": eq.id, "nombre": eq.nombre, "categoria_id": cat.id,
                          "categoria": cat.nombre, "rama_tipo": rama.tipo,
                          "grupo": grupos.get(eq.grupo_id), "estado": eq.estado,
                          "seed": eq.seed,
                          "inscrito_en": eq.inscrito_en.isoformat() if eq.inscrito_en else None,
                          "atletas": atletas})
    return {"filas": filas, "resumen": resumen}


async def get_deportistas(db: AsyncSession, torneo_id: str, user_id: str, is_super: bool, is_org: bool = False) -> dict:
    """Directorio de deportistas del torneo para el módulo Deportistas. Solo lectura."""
    from app.equipos.models import Equipo
    from app.atletas.models import Atleta
    from app.auth.models import Profile
    await _torneo_para_jueces(db, torneo_id, user_id, is_super, is_org)
    filas = []
    for rama, cat in await _categorias_torneo(db, torneo_id):
        res = await db.execute(select(Equipo).where(
            Equipo.categoria_id == cat.id, Equipo.estado != "eliminado").order_by(Equipo.nombre))
        equipos = {e.id: e for e in res.scalars().all()}
        if not equipos:
            continue
        res = await db.execute(select(Atleta).where(
            Atleta.equipo_id.in_(list(equipos.keys()))).order_by(Atleta.nombre_completo))
        atls = list(res.scalars().all())
        uids = [a.user_id for a in atls if a.user_id]
        res = await db.execute(select(Profile).where(Profile.id.in_(uids))) if uids else None
        tels = {p.id: p.telefono for p in res.scalars().all()} if res is not None else {}
        for a in atls:
            eq = equipos.get(a.equipo_id)
            filas.append({"id": a.id, "nombre_completo": a.nombre_completo,
                          "codigo_reclamo": a.codigo_reclamo, "posicion": a.posicion,
                          "equipo_id": a.equipo_id, "equipo_nombre": eq.nombre if eq else "—",
                          "categoria": cat.nombre, "rama_tipo": rama.tipo,
                          "tiene_cuenta": bool(a.user_id),
                          "telefono": tels.get(a.user_id)})
    return {"filas": filas, "total": len(filas)}

async def comunicar(db: AsyncSession, torneo_id: str, user_id: str, is_super: bool, is_org: bool, destino: str, titulo: str, mensaje: str) -> dict:
    """Broadcast de comunicado a atletas/jueces del torneo via notificaciones in-app (tope 200)."""
    from sqlalchemy import text
    from app.notificaciones.router import crear_notificacion
    await _torneo_para_jueces(db, torneo_id, user_id, is_super, is_org)
    if destino not in ("atletas", "jueces", "todos"):
        raise AppError(400, "DESTINO_INVALIDO", "destino debe ser atletas, jueces o todos")
    uids: set[str] = set()
    if destino in ("atletas", "todos"):
        res = await db.execute(text(
            "SELECT DISTINCT a.user_id FROM atletas a JOIN equipos e ON e.id = a.equipo_id "
            "JOIN categorias c ON c.id = e.categoria_id JOIN ramas r ON r.id = c.rama_id "
            "WHERE r.torneo_id = :tid::uuid AND a.user_id IS NOT NULL"
        ).bindparams(tid=str(torneo_id)))
        uids |= {r[0] for r in res.fetchall()}
    if destino in ("jueces", "todos"):
        res = await db.execute(text(
            "SELECT DISTINCT user_id FROM torneo_jueces WHERE torneo_id = :tid::uuid"
        ).bindparams(tid=str(torneo_id)))
        uids |= {r[0] for r in res.fetchall()}
    if destino == "todos":
        uids.discard(user_id)
    uids = {u for u in uids if u}
    total = len(uids)
    if total == 0:
        return {"destino": destino, "enviadas": 0, "titulo": titulo, "mensaje": mensaje}
    for uid in list(uids)[:200]:
        await crear_notificacion(db, uid, "comunicado", titulo, mensaje)
    await db.flush()
    return {"destino": destino, "enviadas": min(total, 200), "titulo": titulo, "mensaje": mensaje}
