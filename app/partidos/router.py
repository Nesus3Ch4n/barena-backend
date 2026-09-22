from uuid import UUID
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.shared.database import get_db
from app.shared.security import get_current_user, require_roles
from app.shared.errors import AppError, NotFound, Forbidden
from app.partidos.models import Partido
from app.partidos.schemas import GenerarFixtureIn, AvanzarIn, IniciarIn, GrupoUpdate, PartidoCreate, PartidoUpdate, ProgramarIn, ResultadoIn, LiveEventoIn
from app.partidos.service import actualizar_grupo, crear_partido_manual, actualizar_partido, eliminar_grupo, eliminar_partido, generar_fixture, generar_bracket_desde_ranking, programar_partido, registrar_resultado, list_partidos, get_partido, live_snapshot, live_evento, live_undo, iniciar_partido, finalizar_partido, borrar_partidos_fase_grupos, borrar_partidos_bracket, sincronizar_categoria

router = APIRouter(prefix="/partidos", tags=["partidos"])
torneo_partidos_router = APIRouter(prefix="/torneos/{torneo_id}/partidos", tags=["partidos"])
categoria_fixture_router = APIRouter(prefix="/categorias/{categoria_id}", tags=["partidos"])

async def _verify_categoria_owner(db: AsyncSession, categoria_id: str, user_id: str, is_super: bool, is_org: bool = False):
    if is_super or is_org:
        return
    from app.torneos.models import Categoria, Rama, Torneo
    res = await db.execute(select(Categoria).where(Categoria.id == categoria_id))
    cat = res.scalar_one_or_none()
    if not cat:
        raise NotFound("CATEGORIA_NOT_FOUND", "Categoria no existe")
    res2 = await db.execute(select(Rama.torneo_id).where(Rama.id == cat.rama_id))
    torneo_id = res2.scalar_one_or_none()
    if not torneo_id:
        raise NotFound("TORNEO_NOT_FOUND", "Torneo no encontrado")
    res3 = await db.execute(select(Torneo).where(Torneo.id == torneo_id))
    torneo = res3.scalar_one_or_none()
    if torneo and torneo.organizador_id != user_id:
        raise Forbidden("No eres organizador de este torneo")

@categoria_fixture_router.get("/grupos", response_model=dict)
async def listar_grupos_categoria(categoria_id: str, request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _verify_categoria_owner(db, categoria_id, user.id, "super_admin" in getattr(request.state, "roles", []), "organizador" in getattr(request.state, "roles", []))
    from app.torneos.models import Grupo
    res = await db.execute(select(Grupo).where(Grupo.categoria_id == categoria_id).order_by(Grupo.orden))
    grupos = res.scalars().all()
    return {"success": True, "data": [{"id": g.id, "nombre": g.nombre, "orden": g.orden} for g in grupos], "error": None}

@categoria_fixture_router.post("/generar-fixture", response_model=dict)
async def generar(categoria_id: str, body: GenerarFixtureIn = None, request: Request = None, user=Depends(require_roles("organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    await _verify_categoria_owner(db, categoria_id, user.id, "super_admin" in getattr(request.state, "roles", []), "organizador" in getattr(request.state, "roles", []))
    partidos = await generar_fixture(db, categoria_id, body.bracket_tipo if body else None, body.crear_grupos if body else True, body.sincronizar_grupos if body else False)
    return {"success": True, "data": {"generados": len(partidos), "partidos": [{"id": p.id, "grupo_id": p.grupo_id, "local": p.equipo_local_id, "visit": p.equipo_visit_id, "bracket_tipo": p.bracket_tipo} for p in partidos]}, "error": None}

@categoria_fixture_router.patch("/grupos/{grupo_id}", response_model=dict)
async def actualizar_grupo_endpoint(categoria_id: str, grupo_id: str, body: GrupoUpdate, request: Request, user=Depends(require_roles("organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    await _verify_categoria_owner(db, categoria_id, user.id, "super_admin" in getattr(request.state, "roles", []), "organizador" in getattr(request.state, "roles", []))
    grupo = await actualizar_grupo(db, grupo_id, body.model_dump(exclude_unset=True))
    return {"success": True, "data": {"id": grupo.id, "nombre": grupo.nombre, "orden": grupo.orden}, "error": None}

@categoria_fixture_router.delete("/grupos/{grupo_id}", response_model=dict)
async def eliminar_grupo_endpoint(categoria_id: str, grupo_id: str, request: Request, user=Depends(require_roles("organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    await _verify_categoria_owner(db, categoria_id, user.id, "super_admin" in getattr(request.state, "roles", []), "organizador" in getattr(request.state, "roles", []))
    await eliminar_grupo(db, grupo_id)
    return {"success": True, "data": {"deleted": True}, "error": None}

@categoria_fixture_router.post("/avanzar-bracket", response_model=dict)
async def avanzar_bracket(categoria_id: str, body: AvanzarIn = None, request: Request = None, user=Depends(require_roles("organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    await _verify_categoria_owner(db, categoria_id, user.id, "super_admin" in getattr(request.state, "roles", []), "organizador" in getattr(request.state, "roles", []))
    partidos, pendientes_previos = await generar_bracket_desde_ranking(db, categoria_id, (body.confirmar if body else False), (body.emparejamiento if body else None))
    return {"success": True, "data": {"generados": len(partidos), "ya_existia": pendientes_previos > 0, "partidos": [{"id": p.id, "fase": p.fase, "llave": p.llave, "local": p.equipo_local_id, "visit": p.equipo_visit_id, "bracket_tipo": p.bracket_tipo} for p in partidos]}, "error": None}

@categoria_fixture_router.delete("/partidos/grupos", response_model=dict)
async def borrar_fase_grupos(categoria_id: str, request: Request, user=Depends(require_roles("organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    await _verify_categoria_owner(db, categoria_id, user.id, "super_admin" in getattr(request.state, "roles", []), "organizador" in getattr(request.state, "roles", []))
    borrados = await borrar_partidos_fase_grupos(db, categoria_id)
    return {"success": True, "data": {"borrados": borrados}, "error": None}

@categoria_fixture_router.delete("/partidos/bracket", response_model=dict)
async def borrar_bracket(categoria_id: str, request: Request, user=Depends(require_roles("organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    await _verify_categoria_owner(db, categoria_id, user.id, "super_admin" in getattr(request.state, "roles", []), "organizador" in getattr(request.state, "roles", []))
    borrados = await borrar_partidos_bracket(db, categoria_id)
    return {"success": True, "data": {"borrados": borrados}, "error": None}

@categoria_fixture_router.get("/bracket-estado", response_model=dict)
async def bracket_estado(categoria_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import text as _text
    res = await db.execute(select(Partido).where(Partido.categoria_id == categoria_id, Partido.fase != "grupos"))
    elim = list(res.scalars().all())
    pend = sum(1 for p in elim if p.estado == "pendiente")
    hechas = sum(1 for p in elim if p.estado != "pendiente")
    snap = None
    try:
        r2 = await db.execute(_text("SELECT creada_en, criterio, clasificados, emparejamiento, filas FROM clasificacion_congelada WHERE categoria_id = :cid ORDER BY creada_en DESC LIMIT 1"), {"cid": categoria_id})
        row = r2.mappings().first()
        if row:
            snap = {"creada_en": row["creada_en"].isoformat() if row["creada_en"] else None, "criterio": row["criterio"], "clasificados": row["clasificados"], "emparejamiento": row["emparejamiento"], "filas": row["filas"]}
    except Exception:
        snap = None
    return {"success": True, "data": {"pendientes": pend, "con_resultado": hechas, "congelada": snap}, "error": None}

@categoria_fixture_router.post("/_migracion013", response_model=dict)
async def _migracion013_tmp(categoria_id: str, request: Request, user=Depends(require_roles("organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    # TEMPORAL-ELIMINAR: aplica migracion 013 (DDL fijo, sin inputs)
    from sqlalchemy import text as _text
    await db.execute(_text("ALTER TABLE categorias ADD COLUMN IF NOT EXISTS clasificados INTEGER"))
    await db.execute(_text("ALTER TABLE categorias ADD COLUMN IF NOT EXISTS criterio_emparejamiento TEXT DEFAULT 'directo'"))
    await db.execute(_text("""CREATE TABLE IF NOT EXISTS clasificacion_congelada (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(), categoria_id UUID NOT NULL REFERENCES categorias(id) ON DELETE CASCADE,
        creada_en TIMESTAMPTZ NOT NULL DEFAULT now(), criterio TEXT NOT NULL DEFAULT 'PG>CS>CP>JL',
        clasificados INT NULL, emparejamiento TEXT NOT NULL DEFAULT 'directo',
        filas JSONB NOT NULL DEFAULT '[]'::jsonb, bracket JSONB NOT NULL DEFAULT '[]'::jsonb)"""))
    await db.execute(_text("CREATE INDEX IF NOT EXISTS ix_clasif_congelada_cat ON clasificacion_congelada (categoria_id, creada_en DESC)"))
    await db.execute(_text("UPDATE categorias SET clasificados = 8 WHERE id IN ('548dd40e-5655-4b5f-82b3-bc28b2a495bd','9da62157-11a8-4755-83a9-8d5a0395dacc')"))
    await db.flush()
    cols = list((await db.execute(_text("SELECT column_name FROM information_schema.columns WHERE table_name='categorias' AND column_name IN ('clasificados','criterio_emparejamiento') ORDER BY column_name"))).scalars().all())
    tbl = (await db.execute(_text("SELECT to_regclass('public.clasificacion_congelada')"))).scalar()
    cats = [dict(r) for r in (await db.execute(_text("SELECT nombre, clasificados, criterio_emparejamiento FROM categorias WHERE id IN ('548dd40e-5655-4b5f-82b3-bc28b2a495bd','9da62157-11a8-4755-83a9-8d5a0395dacc')"))).mappings().all()]
    return {"success": True, "data": {"columnas": cols, "tabla": str(tbl), "categorias": cats}, "error": None}

@categoria_fixture_router.post("/sincronizar", response_model=dict)
async def sincronizar(categoria_id: str, request: Request, user=Depends(require_roles("organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    await _verify_categoria_owner(db, categoria_id, user.id, "super_admin" in getattr(request.state, "roles", []), "organizador" in getattr(request.state, "roles", []))
    resumen = await sincronizar_categoria(db, categoria_id)
    return {"success": True, "data": resumen, "error": None}

@torneo_partidos_router.get("", response_model=dict)
async def listar(torneo_id: str, categoria_id: str = None, grupo_id: str = None, fase: str = None, bracket_tipo: str = None, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    partidos = await list_partidos(db, torneo_id, categoria_id, grupo_id, fase, bracket_tipo)
    if not partidos:
        return {"success": True, "data": [], "error": None}
    from collections import defaultdict
    from app.partidos.models import SetPartido
    ids = [p.id for p in partidos]
    res = await db.execute(select(SetPartido).where(SetPartido.partido_id.in_(ids)).order_by(SetPartido.partido_id, SetPartido.numero_set))
    sets_por_partido = defaultdict(list)
    for s in res.scalars().all():
        sets_por_partido[s.partido_id].append({"numero_set": s.numero_set, "pts_local": s.pts_local, "pts_visitante": s.pts_visitante, "ganador_id": s.ganador_id})
    data = [{"id": p.id, "categoria_id": p.categoria_id, "grupo_id": p.grupo_id, "fase": p.fase, "llave": p.llave or 0, "local": p.equipo_local_id, "visit": p.equipo_visit_id, "cancha": p.cancha, "fecha_hora": p.fecha_hora.isoformat() if p.fecha_hora else None, "estado": p.estado, "ganador_id": p.ganador_id, "bracket_tipo": p.bracket_tipo, "orden_en_round": p.orden_en_round, "partido_siguiente_id": p.partido_siguiente_id, "sets": sets_por_partido.get(p.id, [])} for p in partidos]
    return {"success": True, "data": data, "error": None}

@router.patch("/{partido_id}/programar", response_model=dict)
async def programar(partido_id: str, body: ProgramarIn, request: Request, user=Depends(require_roles("organizador", "juez_anotador", "super_admin")), db: AsyncSession = Depends(get_db)):
    is_org = "organizador" in getattr(request.state, "roles", []) or "super_admin" in getattr(request.state, "roles", [])
    partido = await programar_partido(db, partido_id, body.cancha, body.fecha_hora, is_organizador=is_org)
    return {"success": True, "data": {"id": partido.id, "cancha": partido.cancha, "fecha_hora": partido.fecha_hora.isoformat() if partido.fecha_hora else None}, "error": None}

@router.post("/{partido_id}/resultado", response_model=dict)
async def resultado(partido_id: str, body: ResultadoIn, request: Request, user=Depends(require_roles("juez_anotador", "organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    sets = [{"numero_set": s.numero_set, "pts_local": s.pts_local, "pts_visitante": s.pts_visitante, "duracion_min": s.duracion_min} for s in body.sets]
    is_org = "organizador" in getattr(request.state, "roles", []) or "super_admin" in getattr(request.state, "roles", [])
    tarjetas = {
        "tarjetas_amarillas_local": body.tarjetas_amarillas_local,
        "tarjetas_rojas_local": body.tarjetas_rojas_local,
        "tarjetas_amarillas_visit": body.tarjetas_amarillas_visit,
        "tarjetas_rojas_visit": body.tarjetas_rojas_visit,
    }
    partido = await registrar_resultado(db, partido_id, sets, is_organizador=is_org, tarjetas=tarjetas)
    bracket_generado = False
    if partido.fase == "grupos":
        res_e = await db.execute(select(Partido.id).where(Partido.categoria_id == partido.categoria_id, Partido.fase != "grupos").limit(1))
        bracket_generado = res_e.scalar_one_or_none() is not None
    return {"success": True, "data": {"id": partido.id, "estado": partido.estado, "ganador_id": partido.ganador_id, "bracket_generado": bracket_generado}, "error": None}

@router.get("/{partido_id}", response_model=dict)
async def detalle(partido_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    partido, sets = await get_partido(db, partido_id)
    return {"success": True, "data": {"partido": {"id": partido.id, "estado": partido.estado, "ganador_id": partido.ganador_id, "local": partido.equipo_local_id, "visit": partido.equipo_visit_id, "cancha": partido.cancha, "tarjetas_amarillas_local": partido.tarjetas_amarillas_local, "tarjetas_rojas_local": partido.tarjetas_rojas_local, "tarjetas_amarillas_visit": partido.tarjetas_amarillas_visit, "tarjetas_rojas_visit": partido.tarjetas_rojas_visit}, "sets": [{"numero_set": s.numero_set, "pts_local": s.pts_local, "pts_visitante": s.pts_visitante, "ganador_id": s.ganador_id} for s in sets]}, "error": None}

@router.get("/{partido_id}/qr", response_model=dict)
async def qr(partido_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {"success": True, "data": {"qr_url": f"/juez/partido/{partido_id}", "partido_id": partido_id}, "error": None}

LIVE_ROLES = ["juez_anotador", "organizador", "super_admin"]

@router.get("/{partido_id}/live", response_model=dict)
async def live_get(partido_id: str, user=Depends(require_roles(*LIVE_ROLES)), db: AsyncSession = Depends(get_db)):
    return {"success": True, "data": await live_snapshot(db, partido_id), "error": None}

@router.get("/{partido_id}/live/public", response_model=dict)
async def live_public(partido_id: str, db: AsyncSession = Depends(get_db)):
    return {"success": True, "data": await live_snapshot(db, partido_id), "error": None}

@router.post("/{partido_id}/live", response_model=dict)
async def live_post(partido_id: str, body: LiveEventoIn, user=Depends(require_roles(*LIVE_ROLES)), db: AsyncSession = Depends(get_db)):
    return {"success": True, "data": await live_evento(db, partido_id, body), "error": None}

@router.post("/{partido_id}/live/undo", response_model=dict)
async def live_undo_endpoint(partido_id: str, user=Depends(require_roles(*LIVE_ROLES)), db: AsyncSession = Depends(get_db)):
    return {"success": True, "data": await live_undo(db, partido_id), "error": None}

@router.post("/{partido_id}/iniciar", response_model=dict)
async def iniciar(partido_id: str, body: IniciarIn, user=Depends(require_roles(*LIVE_ROLES)), db: AsyncSession = Depends(get_db)):
    return {"success": True, "data": await iniciar_partido(db, partido_id, body.sorteo_ganador_id, body.saque_equipo_id, body.saque_atleta_id, user.id, body.orden_local, body.orden_visitante), "error": None}

@router.post("/{partido_id}/finalizar", response_model=dict)
async def finalizar(partido_id: str, user=Depends(require_roles(*LIVE_ROLES)), db: AsyncSession = Depends(get_db)):
    return {"success": True, "data": await finalizar_partido(db, partido_id), "error": None}

@router.patch("/{partido_id}", response_model=dict)
async def actualizar(partido_id: str, body: PartidoUpdate, request: Request, user=Depends(require_roles("organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    await _verify_categoria_owner(db, (await db.execute(select(Partido.categoria_id).where(Partido.id == partido_id))).scalar_one_or_none() or "", user.id, "super_admin" in getattr(request.state, "roles", []), "organizador" in getattr(request.state, "roles", []))
    is_org = "organizador" in getattr(request.state, "roles", []) or "super_admin" in getattr(request.state, "roles", [])
    partido = await actualizar_partido(db, partido_id, body.model_dump(exclude_unset=True), is_organizador=is_org)
    return {"success": True, "data": {"id": partido.id, "grupo_id": partido.grupo_id, "fase": partido.fase, "bracket_tipo": partido.bracket_tipo}, "error": None}

@router.delete("/{partido_id}", response_model=dict)
async def eliminar(partido_id: str, request: Request, user=Depends(require_roles("organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    # verify owner via partido -> categoria
    res = await db.execute(select(Partido.categoria_id).where(Partido.id == partido_id))
    cat_id = res.scalar_one_or_none()
    if cat_id:
        await _verify_categoria_owner(db, cat_id, user.id, "super_admin" in getattr(request.state, "roles", []), "organizador" in getattr(request.state, "roles", []))
    is_org = "organizador" in getattr(request.state, "roles", []) or "super_admin" in getattr(request.state, "roles", [])
    await eliminar_partido(db, partido_id, is_organizador=is_org)
    return {"success": True, "data": {"deleted": True}, "error": None}

@categoria_fixture_router.post("/partidos", status_code=201, response_model=dict)
async def crear_manual(categoria_id: str, body: PartidoCreate, request: Request, user=Depends(require_roles("organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    await _verify_categoria_owner(db, categoria_id, user.id, "super_admin" in getattr(request.state, "roles", []), "organizador" in getattr(request.state, "roles", []))
    partido = await crear_partido_manual(db, body.model_dump())
    return {"success": True, "data": {"id": partido.id, "local": partido.equipo_local_id, "visit": partido.equipo_visit_id}, "error": None}
