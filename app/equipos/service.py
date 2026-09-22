import uuid, random, string
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, update, delete, text
from app.equipos.models import Equipo
from app.torneos.models import Categoria, Torneo, Rama
from app.atletas.models import Atleta
from app.shared.errors import AppError, NotFound
from app.equipos.schemas import EquipoCreate

def gen_codigo():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

async def verify_torneo_owner(db: AsyncSession, torneo_id: str, user_id: str, is_super: bool, is_org: bool = False):
    res = await db.execute(select(Torneo).where(Torneo.id == torneo_id))
    torneo = res.scalar_one_or_none()
    if not torneo:
        raise NotFound("TORNEO_NOT_FOUND", "Torneo no existe", {"id": torneo_id})
    if torneo.organizador_id != user_id and not is_super and not is_org:
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

async def create_equipo(db: AsyncSession, torneo_id: str, data: EquipoCreate, user_id: str, is_super: bool, is_org: bool = False) -> Equipo:
    torneo = await verify_torneo_owner(db, torneo_id, user_id, is_super, is_org)
    cat = await verify_categoria_in_torneo(db, data.categoria_id, torneo_id)
    # validar atletas: debe haber 2 titulares
    titulares = [a for a in data.atletas if a.posicion == "titular"]
    if len(titulares) != 2:
        raise AppError(400, "ATLETAS_TITULARES_INVALIDO", "Equipo debe tener exactamente 2 titulares")
    # check duplicado nombre en categoria
    res = await db.execute(select(Equipo).where(Equipo.categoria_id == data.categoria_id, Equipo.nombre == data.nombre))
    if res.scalar_one_or_none():
        raise AppError(409, "EQUIPO_DUPLICADO", "Ya existe equipo con ese nombre en la categoria", {"nombre": data.nombre})
    await validar_jugadores_unicos(db, data.categoria_id, data.atletas)

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

async def aprobar_equipo(db: AsyncSession, equipo_id: str, grupo_id: str = None, seed: int = None, torneo_id: str = None, user_id: str = None, is_super: bool = False, is_org: bool = False):
    res = await db.execute(select(Equipo).where(Equipo.id == equipo_id))
    equipo = res.scalar_one_or_none()
    if not equipo:
        raise NotFound("EQUIPO_NOT_FOUND", "Equipo no existe", {"id": equipo_id})
    # verify owner via torneo
    if torneo_id:
        await verify_torneo_owner(db, torneo_id, user_id, is_super, is_org)
    # verify grupo pertenece a misma categoria
    if grupo_id:
        from app.torneos.models import Grupo
        res2 = await db.execute(select(Grupo).where(Grupo.id == grupo_id, Grupo.categoria_id == equipo.categoria_id))
        if not res2.scalar_one_or_none():
            raise AppError(400, "GRUPO_INVALIDO", "Grupo no pertenece a la categoria del equipo")
        await validar_grupo_lleno(db, equipo.categoria_id, grupo_id, excluir_equipo_id=equipo_id)
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

async def update_equipo(db: AsyncSession, equipo_id: str, data, user_id: str, is_super: bool, is_org: bool = False):
    from app.equipos.schemas import EquipoUpdate
    assert isinstance(data, EquipoUpdate)
    res = await db.execute(select(Equipo).where(Equipo.id == equipo_id))
    equipo = res.scalar_one_or_none()
    if not equipo:
        raise NotFound("EQUIPO_NOT_FOUND", "Equipo no existe", {"id": equipo_id})
    # verify owner via categoria -> rama -> torneo
    from app.torneos.models import Categoria, Rama, Torneo
    res2 = await db.execute(select(Rama.torneo_id).join(Categoria, Categoria.id == equipo.categoria_id).where(Categoria.id == equipo.categoria_id))
    # actually need to get torneo_id via join
    res3 = await db.execute(select(Categoria).where(Categoria.id == equipo.categoria_id))
    cat = res3.scalar_one_or_none()
    if not cat:
        raise NotFound("CATEGORIA_NOT_FOUND", "Categoria no existe")
    res4 = await db.execute(select(Rama).where(Rama.id == cat.rama_id))
    rama = res4.scalar_one_or_none()
    if not rama:
        raise NotFound("RAMA_NOT_FOUND", "Rama no existe")
    await verify_torneo_owner(db, rama.torneo_id, user_id, is_super, is_org)
    grupo_anterior = equipo.grupo_id
    upd = data.model_dump(exclude_unset=True)
    if "nombre" in upd and upd["nombre"] is not None:
        # check duplicate in same categoria if nombre changes
        if upd["nombre"] != equipo.nombre:
            res_dup = await db.execute(select(Equipo).where(Equipo.categoria_id == (upd.get("categoria_id") or equipo.categoria_id), Equipo.nombre == upd["nombre"], Equipo.id != equipo_id))
            if res_dup.scalar_one_or_none():
                raise AppError(409, "EQUIPO_DUPLICADO", "Ya existe equipo con ese nombre en la categoria")
        equipo.nombre = upd["nombre"].strip()
    if "ciudad" in upd:
        equipo.ciudad = upd["ciudad"].strip() if upd["ciudad"] else None
    if "categoria_id" in upd and upd["categoria_id"]:
        await verify_categoria_in_torneo(db, upd["categoria_id"], rama.torneo_id)
        equipo.categoria_id = upd["categoria_id"]
        # si cambia categoria, reset grupo
        equipo.grupo_id = None
    if "grupo_id" in upd:
        nuevo_grupo = upd["grupo_id"]
        if nuevo_grupo:
            from app.torneos.models import Grupo
            resg = await db.execute(select(Grupo).where(Grupo.id == nuevo_grupo, Grupo.categoria_id == equipo.categoria_id))
            if not resg.scalar_one_or_none():
                raise AppError(400, "GRUPO_INVALIDO", "Grupo no pertenece a la categoria")
            if nuevo_grupo != equipo.grupo_id:
                conteo = await contar_partidos_equipo(db, equipo_id)
                if conteo["jugados"] > 0 and not upd.get("forzar"):
                    raise AppError(409, "EQUIPO_CON_PARTIDOS", "Esta dupla ya tiene partidos registrados. Cambiar de grupo puede afectar la programación y las estadísticas", {"partidos_jugados": conteo["jugados"], "partidos_total": conteo["total"], "requiere_forzar": True})
            await validar_grupo_lleno(db, equipo.categoria_id, nuevo_grupo, excluir_equipo_id=equipo_id)
        equipo.grupo_id = nuevo_grupo
        if grupo_anterior != nuevo_grupo:
            await recalc_rankings_equipo(db, equipo.categoria_id, [grupo_anterior, nuevo_grupo])
    if "seed" in upd:
        equipo.seed = upd["seed"]
    if "foto_url" in upd:
        equipo.foto_url = upd["foto_url"]
    if "atletas" in upd and upd["atletas"] is not None:
        await validar_jugadores_unicos(db, equipo.categoria_id, upd["atletas"], excluir_equipo_id=equipo_id)
        # actualización in-place: conserva id/user_id/codigo_reclamo
        await _reemplazar_atletas_in_place(db, equipo_id, upd["atletas"])
    await db.flush()
    return equipo

def _norm_nombre(s: str) -> str:
    return (s or "").strip().lower()

async def recalc_rankings_equipo(db: AsyncSession, categoria_id: str, grupo_ids=None) -> None:
    """Recalcula rankings tras cambios administrativos (las triggers solo cubren partidos/sets)."""
    grupos = [g for g in (grupo_ids or []) if g]
    for gid in dict.fromkeys(grupos):
        await db.execute(text("SELECT fn_recalc_rankings_grupo(:gid)"), {"gid": gid})
    await db.execute(text("SELECT fn_recalc_rankings_general(:cid)"), {"cid": categoria_id})
    await db.flush()

async def contar_partidos_equipo(db: AsyncSession, equipo_id: str) -> dict:
    """Devuelve {total, jugados} para una dupla. Jugados = estado distinto de pendiente."""
    from app.partidos.models import Partido
    from sqlalchemy import or_
    res = await db.execute(select(Partido).where(or_(Partido.equipo_local_id == equipo_id, Partido.equipo_visit_id == equipo_id)))
    todos = res.scalars().all()
    jugados = sum(1 for p in todos if p.estado != "pendiente")
    return {"total": len(todos), "jugados": jugados}

async def validar_jugadores_unicos(db: AsyncSession, categoria_id: str, atletas, excluir_equipo_id: str = None):
    """Rechaza nombres vacíos/duplicados dentro del payload y contra otras duplas de la categoría."""
    from app.equipos.schemas import AtletaIn
    nombres = [_norm_nombre(a.nombre_completo if isinstance(a, AtletaIn) else a.get("nombre_completo", "")) for a in atletas]
    if any(not n for n in nombres):
        raise AppError(400, "ATLETA_NOMBRE_VACIO", "Nombre de jugador vacío")
    if len(set(nombres)) != len(nombres):
        raise AppError(400, "ATLETA_DUPLICADO", "Jugador duplicado dentro de la dupla")
    q = select(Atleta.nombre_completo).join(Equipo, Atleta.equipo_id == Equipo.id).where(Equipo.categoria_id == categoria_id)
    if excluir_equipo_id:
        q = q.where(Equipo.id != excluir_equipo_id)
    res = await db.execute(q)
    existentes = {_norm_nombre(n) for n in res.scalars().all()}
    choque = set(nombres) & existentes
    if choque:
        raise AppError(409, "JUGADOR_YA_REGISTRADO", "Jugador ya registrado en otra dupla de la categoria", {"jugadores": sorted(choque)})

async def validar_grupo_lleno(db: AsyncSession, categoria_id: str, grupo_id: str, excluir_equipo_id: str = None):
    """Rechaza asignar a un grupo que ya alcanzó equipos_x_grupo (solo cuenta aprobados)."""
    from app.torneos.models import Grupo
    res = await db.execute(select(Categoria).where(Categoria.id == categoria_id))
    cat = res.scalar_one_or_none()
    if not cat:
        raise NotFound("CATEGORIA_NOT_FOUND", "Categoria no existe")
    limite = getattr(cat, "equipos_x_grupo", None) or 0
    if limite <= 0:
        return
    q = select(Equipo).where(Equipo.categoria_id == categoria_id, Equipo.grupo_id == grupo_id, Equipo.estado == "aprobado")
    if excluir_equipo_id:
        q = q.where(Equipo.id != excluir_equipo_id)
    res = await db.execute(q)
    ocupados = len(res.scalars().all())
    if ocupados >= limite:
        resg = await db.execute(select(Grupo).where(Grupo.id == grupo_id))
        g = resg.scalar_one_or_none()
        raise AppError(409, "GRUPO_LLENO", f"Grupo {g.nombre if g else ''} lleno ({ocupados}/{limite})", {"grupo_id": grupo_id, "ocupados": ocupados, "limite": limite})

async def retirar_equipo(db: AsyncSession, equipo_id: str) -> dict:
    """Baja de dupla: sin partidos → borrado físico; con partidos → estado eliminado
    (el CHECK de BD solo admite pendiente/aprobado/eliminado; eliminado ya está
    excluido de fixture, rankings y listados, así que conserva el historial)."""
    res = await db.execute(select(Equipo).where(Equipo.id == equipo_id))
    equipo = res.scalar_one_or_none()
    if not equipo:
        raise NotFound("EQUIPO_NOT_FOUND", "Equipo no existe", {"id": equipo_id})
    conteo = await contar_partidos_equipo(db, equipo_id)
    cat_id, grp_id = equipo.categoria_id, equipo.grupo_id
    if conteo["total"] == 0:
        await db.execute(delete(Atleta).where(Atleta.equipo_id == equipo_id))
        await db.delete(equipo)
        await db.flush()
        await recalc_rankings_equipo(db, cat_id, [grp_id])
        return {"eliminado_fisico": True, "partidos_jugados": 0, "partidos_total": 0, "nombre": equipo.nombre}
    equipo.estado = "eliminado"
    await db.flush()
    await recalc_rankings_equipo(db, cat_id, [grp_id])
    return {"eliminado_fisico": False, "partidos_jugados": conteo["jugados"], "partidos_total": conteo["total"], "nombre": equipo.nombre}

async def _reemplazar_atletas_in_place(db: AsyncSession, equipo_id: str, atletas) -> None:
    """Actualiza atletas conservando id/user_id/codigo_reclamo cuando coinciden en orden; crea/elimina el resto."""
    from app.equipos.schemas import AtletaIn
    titulares = [a for a in atletas if (a.posicion if isinstance(a, AtletaIn) else a.get("posicion", "titular")) == "titular"]
    if len(titulares) != 2:
        raise AppError(400, "ATLETAS_TITULARES_INVALIDO", "Equipo debe tener exactamente 2 titulares")
    if len(atletas) < 2 or len(atletas) > 3:
        raise AppError(400, "ATLETAS_INVALIDO", "Equipo debe tener 2 o 3 atletas")
    res = await db.execute(select(Atleta).where(Atleta.equipo_id == equipo_id).order_by(Atleta.nombre_completo))
    actuales = list(res.scalars().all())
    for i, a_in in enumerate(atletas):
        nombre = a_in.nombre_completo if isinstance(a_in, AtletaIn) else a_in.get("nombre_completo")
        pos = a_in.posicion if isinstance(a_in, AtletaIn) else a_in.get("posicion", "titular")
        doc = a_in.doc_identidad if isinstance(a_in, AtletaIn) else a_in.get("doc_identidad")
        if i < len(actuales):
            actuales[i].nombre_completo = nombre
            actuales[i].posicion = pos
            if doc is not None:
                actuales[i].doc_identidad = doc
        else:
            codigo = gen_codigo()
            for _ in range(3):
                r = await db.execute(select(Atleta).where(Atleta.codigo_reclamo == codigo))
                if not r.scalar_one_or_none():
                    break
                codigo = gen_codigo()
            db.add(Atleta(equipo_id=equipo_id, nombre_completo=nombre, posicion=pos, doc_identidad=doc, codigo_reclamo=codigo))
    for sobrante in actuales[len(atletas):]:
        await db.delete(sobrante)
    await db.flush()

async def reemplazar_equipo(db: AsyncSession, equipo_id: str, data) -> dict:
    """Reemplazo de dupla. Sin partidos jugados → directo. Con jugados → requiere modo."""
    from app.equipos.schemas import ReemplazoIn
    assert isinstance(data, ReemplazoIn)
    res = await db.execute(select(Equipo).where(Equipo.id == equipo_id))
    equipo = res.scalar_one_or_none()
    if not equipo:
        raise NotFound("EQUIPO_NOT_FOUND", "Equipo no existe", {"id": equipo_id})
    conteo = await contar_partidos_equipo(db, equipo_id)
    await validar_jugadores_unicos(db, equipo.categoria_id, data.atletas, excluir_equipo_id=equipo_id)
    if data.nombre and data.nombre.strip() != equipo.nombre:
        res_dup = await db.execute(select(Equipo).where(Equipo.categoria_id == equipo.categoria_id, Equipo.nombre == data.nombre.strip(), Equipo.id != equipo_id))
        if res_dup.scalar_one_or_none():
            raise AppError(409, "EQUIPO_DUPLICADO", "Ya existe equipo con ese nombre en la categoria")
    if conteo["jugados"] == 0:
        if data.nombre:
            equipo.nombre = data.nombre.strip()
        if data.ciudad is not None:
            equipo.ciudad = data.ciudad.strip() if data.ciudad else None
        await _reemplazar_atletas_in_place(db, equipo_id, data.atletas)
        return {"modo": "directo", "equipo_id": equipo_id, "partidos_jugados": 0, "nombre": equipo.nombre}
    if not data.modo:
        raise AppError(409, "EQUIPO_CON_PARTIDOS", "Esta dupla ya tiene partidos registrados. Indique modo: conservar_historial o nueva_participacion", {"partidos_jugados": conteo["jugados"], "partidos_total": conteo["total"], "requiere_modo": True})
    if data.modo == "conservar_historial":
        if data.nombre:
            equipo.nombre = data.nombre.strip()
        if data.ciudad is not None:
            equipo.ciudad = data.ciudad.strip() if data.ciudad else None
        await _reemplazar_atletas_in_place(db, equipo_id, data.atletas)
        return {"modo": "conservar_historial", "equipo_id": equipo_id, "partidos_jugados": conteo["jugados"], "nombre": equipo.nombre}
    # nueva_participacion: retira la actual y crea una nueva en el mismo grupo/categoria
    equipo.estado = "eliminado"
    await db.flush()
    await recalc_rankings_equipo(db, equipo.categoria_id, [equipo.grupo_id])
    nuevo = Equipo(categoria_id=equipo.categoria_id, grupo_id=equipo.grupo_id, nombre=(data.nombre.strip() if data.nombre else equipo.nombre), ciudad=data.ciudad.strip() if data.ciudad else equipo.ciudad, estado="aprobado", seed=equipo.seed)
    db.add(nuevo)
    await db.flush()
    await validar_grupo_lleno(db, nuevo.categoria_id, nuevo.grupo_id, excluir_equipo_id=None) if nuevo.grupo_id else None
    for a_in in data.atletas:
        codigo = gen_codigo()
        for _ in range(3):
            r = await db.execute(select(Atleta).where(Atleta.codigo_reclamo == codigo))
            if not r.scalar_one_or_none():
                break
            codigo = gen_codigo()
        db.add(Atleta(equipo_id=nuevo.id, nombre_completo=a_in.nombre_completo, posicion=a_in.posicion, doc_identidad=a_in.doc_identidad, codigo_reclamo=codigo))
    await db.flush()
    return {"modo": "nueva_participacion", "equipo_id": nuevo.id, "retirada_id": equipo_id, "partidos_jugados": conteo["jugados"], "nombre": nuevo.nombre}

async def get_equipo_atletas(db: AsyncSession, equipo_id: str):
    res = await db.execute(select(Atleta).where(Atleta.equipo_id == equipo_id))
    return res.scalars().all()
