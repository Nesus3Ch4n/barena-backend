import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.rankings.engine import (
    CRITERIOS_DEFAULT,
    _aplicar_partido,
    criterios_de_torneo,
    criterios_label,
    normalizar_criterios,
    ordenar_stats,
    ratio,
)
from app.shared.errors import AppError
from app.torneos.clasificacion import get_clasificacion, guardar_clasificacion


def fila(equipo_id, nombre, pts, sets_f, sets_c, pf, pc):
    return {
        "equipo_id": equipo_id, "equipo_nombre": nombre,
        "grupo_id": None, "grupo_nombre": None,
        "pj": 3, "pg": 2, "pe": 0, "pp": 1, "pts": pts,
        "sets_favor": sets_f, "sets_contra": sets_c,
        "puntos_favor": pf, "puntos_contra": pc,
        "sanciones": 0, "posicion": 0,
    }


class RankingEngineTests(unittest.TestCase):
    def setUp(self):
        # A y B empatan en puntos; A tiene mejor cociente de sets.
        # C tiene menos puntos; D no jugó (divisores en cero).
        self.rows = [
            fila("a", "Alfa", 8, 6, 2, 120, 90),
            fila("b", "Beta", 8, 5, 3, 130, 100),
            fila("c", "Gamma", 6, 4, 4, 110, 110),
            fila("d", "Delta", 0, 0, 0, 0, 0),
        ]

    def test_normalizar_quita_duplicados_y_validos(self):
        self.assertEqual(normalizar_criterios(["sets", "puntos", "sets"]), ["sets", "puntos"])
        self.assertEqual(normalizar_criterios(["inventado"]), CRITERIOS_DEFAULT)
        self.assertEqual(normalizar_criterios([]), CRITERIOS_DEFAULT)

    def test_un_solo_criterio(self):
        out = ordenar_stats([dict(r) for r in self.rows], ["puntos"])
        self.assertEqual([r["equipo_id"] for r in out], ["a", "b", "c", "d"])
        self.assertEqual([r["posicion"] for r in out], [1, 2, 3, 4])

    def test_dos_criterios_prioridad(self):
        # Puntos primero; A y B empatan y decide sets (A 3.0 vs B 1.67).
        out = ordenar_stats([dict(r) for r in self.rows], ["puntos", "sets"])
        self.assertEqual([r["equipo_id"] for r in out], ["a", "b", "c", "d"])

    def test_tres_criterios(self):
        out = ordenar_stats([dict(r) for r in self.rows], ["puntos", "sets", "puntos_partido"])
        self.assertEqual([r["equipo_id"] for r in out], ["a", "b", "c", "d"])

    def test_cambio_de_prioridad(self):
        # Si sets va primero, A (3.0) supera a B (1.67) aunque empaten en puntos.
        out = ordenar_stats([dict(r) for r in self.rows], ["sets", "puntos"])
        self.assertEqual(out[0]["equipo_id"], "a")
        # Si puntos de partido va primero, B (1.30) supera a A (1.33)? A=120/90=1.333, B=130/100=1.30.
        out2 = ordenar_stats([dict(r) for r in self.rows], ["puntos_partido", "puntos"])
        self.assertEqual(out2[0]["equipo_id"], "a")

    def test_cociente_puntos_desempata(self):
        rows = [
            fila("a", "Alfa", 8, 4, 4, 100, 100),
            fila("b", "Beta", 8, 4, 4, 120, 100),
        ]
        out = ordenar_stats(rows, ["puntos", "puntos_partido"])
        self.assertEqual(out[0]["equipo_id"], "b")

    def test_division_por_cero(self):
        self.assertEqual(ratio(0, 0), 0)
        self.assertEqual(ratio(5, 0), float("inf"))
        self.assertEqual(ratio(5, 2), 2.5)
        rows = [fila("a", "Alfa", 0, 0, 0, 0, 0), fila("b", "Beta", 0, 1, 0, 10, 0)]
        out = ordenar_stats(rows, ["sets", "puntos_partido"])
        self.assertEqual(out[0]["equipo_id"], "b")

    def test_determinista(self):
        rows = [fila("b", "Beta", 3, 1, 1, 20, 20), fila("a", "Alfa", 3, 1, 1, 20, 20)]
        out = ordenar_stats(rows, ["puntos", "sets", "puntos_partido"])
        self.assertEqual([r["equipo_id"] for r in out], ["a", "b"])
        # Repetir produce el mismo orden.
        out2 = ordenar_stats([dict(r) for r in rows], ["puntos", "sets", "puntos_partido"])
        self.assertEqual([r["equipo_id"] for r in out], [r["equipo_id"] for r in out2])

    def test_configuracion_por_torneo_aislada(self):
        t1 = SimpleNamespace(id="t1", config_visibilidad={"clasificacion": {"criterios": ["sets", "puntos"]}})
        t2 = SimpleNamespace(id="t2", config_visibilidad={"clasificacion": {"criterios": ["puntos_partido"]}})
        self.assertEqual(criterios_de_torneo(t1), ["sets", "puntos"])
        self.assertEqual(criterios_de_torneo(t2), ["puntos_partido"])

    def test_configuracion_defecto_y_persistencia_lectura(self):
        t = SimpleNamespace(id="t3", config_visibilidad={})
        self.assertEqual(criterios_de_torneo(t), CRITERIOS_DEFAULT)
        cfg = get_clasificacion(t)
        self.assertEqual(cfg["criterios"], CRITERIOS_DEFAULT)
        self.assertEqual(cfg["torneo_id"], "t3")
        self.assertIsNone(cfg["actualizado_en"])

    def test_etiqueta(self):
        self.assertEqual(criterios_label(["puntos", "sets", "puntos_partido"]), "Puntos ganados > Cociente de sets > Cociente de puntos")

    def test_stats_y_resultados_originales(self):
        local = SimpleNamespace(id="local", nombre="Local", grupo_id="g1")
        visit = SimpleNamespace(id="visit", nombre="Visitante", grupo_id="g1")
        filas = {
            "local": {"pj": 0, "pg": 0, "pe": 0, "pp": 0, "pts": 0, "sets_favor": 0, "sets_contra": 0, "puntos_favor": 0, "puntos_contra": 0, "sanciones": 0},
            "visit": {"pj": 0, "pg": 0, "pe": 0, "pp": 0, "pts": 0, "sets_favor": 0, "sets_contra": 0, "puntos_favor": 0, "puntos_contra": 0, "sanciones": 0},
        }
        partido = SimpleNamespace(
            equipo_local_id="local", equipo_visit_id="visit", ganador_id="local",
            tarjetas_amarillas_local=1, tarjetas_rojas_local=0,
            tarjetas_amarillas_visit=0, tarjetas_rojas_visit=0,
        )
        sets = [
            SimpleNamespace(pts_local=21, pts_visitante=15, ganador_id="local"),
            SimpleNamespace(pts_local=18, pts_visitante=21, ganador_id="visit"),
            SimpleNamespace(pts_local=15, pts_visitante=12, ganador_id="local"),
        ]
        _aplicar_partido(filas, partido, sets)

        self.assertEqual(partido.ganador_id, "local")
        self.assertEqual(sets[0].pts_local, 21)
        self.assertEqual(filas["local"]["pg"], 1)
        self.assertEqual(filas["visit"]["pp"], 1)
        self.assertEqual(filas["local"]["pts"], 3)
        self.assertEqual(filas["local"]["sets_favor"], 2)
        self.assertEqual(filas["local"]["sets_contra"], 1)
        self.assertEqual(filas["local"]["puntos_favor"], 54)
        self.assertEqual(filas["local"]["puntos_contra"], 48)
        self.assertEqual(filas["local"]["sanciones"], 1)


class PersistenciaClasificacionTests(unittest.IsolatedAsyncioTestCase):
    class FakeDB:
        def __init__(self):
            self.flushed = False

        async def flush(self):
            self.flushed = True

    async def test_guarda_criterios_fecha_usuario_y_aislamiento(self):
        t1 = SimpleNamespace(id="t1", config_visibilidad={"fixture_visible": True})
        t2 = SimpleNamespace(id="t2", config_visibilidad={})
        db = self.FakeDB()
        with patch("app.torneos.clasificacion.compute_tournament_rankings", new=AsyncMock(return_value=[{}, {}])):
            d1 = await guardar_clasificacion(db, t1, "user-1", ["sets", "puntos"])
            d2 = await guardar_clasificacion(db, t2, "user-2", ["puntos_partido"])

        self.assertTrue(db.flushed)
        self.assertEqual(d1["criterios"], ["sets", "puntos"])
        self.assertEqual(d1["actualizado_por"], "user-1")
        self.assertTrue(d1["actualizado_en"])
        self.assertEqual(d1["equipos_recalculados"], 2)
        self.assertTrue(t1.config_visibilidad["fixture_visible"])
        self.assertEqual(t1.config_visibilidad["clasificacion"]["criterios"], ["sets", "puntos"])
        self.assertEqual(t2.config_visibilidad["clasificacion"]["criterios"], ["puntos_partido"])
        self.assertEqual(criterios_de_torneo(t1), ["sets", "puntos"])
        self.assertEqual(criterios_de_torneo(t2), ["puntos_partido"])

    async def test_rechaza_guardar_sin_criterios(self):
        db = self.FakeDB()
        t = SimpleNamespace(id="t1", config_visibilidad={})
        with self.assertRaises(AppError):
            await guardar_clasificacion(db, t, "user-1", [])
        self.assertFalse(db.flushed)
        self.assertEqual(t.config_visibilidad, {})


if __name__ == "__main__":
    unittest.main()
