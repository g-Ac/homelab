"""Testes das travas do agente (issues #23 e #25). Rodar: python3 -m unittest -v agente/test_sre.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import sre  # noqa: E402

EXP_FALSO = "O que aconteceu: disco com 20% livre.\nProvável causa: nada.\nO que sugiro: A evidência contradiz o alerta; pode ser falso alarme."
EXP_OK = "O que aconteceu: disco em 19,75% livre.\nProvável causa: logs crescendo.\nO que sugiro: limpar o journal."


class TestClasse(unittest.TestCase):
    def test_disponibilidade(self):
        for n in ("ServicoHttpFora", "ServicoSystemdParado", "MaquinaFora", "MetricasGpuParadas", "GpuSemDriver"):
            self.assertEqual(sre.classe_alerta(n), "disponibilidade", n)

    def test_limiar(self):
        for n in ("DiscoQuaseCheio", "DiscoEncolhendo", "DiscoVaiEncherEm24h", "MemoriaBaixa", "PiPertoDeTravar",
                  "CpuQuentePi", "GpuQuente"):
            self.assertEqual(sre.classe_alerta(n), "limiar", n)

    def test_desconhecido_e_tratado_como_limiar(self):
        self.assertEqual(sre.classe_alerta("AlertaNovoQualquer"), "limiar")


class TestTrava(unittest.TestCase):
    def test_limiar_descarta_explicacao_que_desmente_a_regra(self):
        self.assertIsNone(sre.filtrar_explicacao("limiar", EXP_FALSO))
        for frase in ("Parece um alarme falso.", "A evidência CONTRADIZ o alerta.", "nao confirma o alerta"):
            self.assertIsNone(sre.filtrar_explicacao("limiar", f"O que aconteceu: x\n{frase}"), frase)

    def test_limiar_mantem_explicacao_coerente(self):
        self.assertEqual(sre.filtrar_explicacao("limiar", EXP_OK), EXP_OK)

    def test_disponibilidade_pode_dizer_que_contradiz(self):
        self.assertEqual(sre.filtrar_explicacao("disponibilidade", EXP_FALSO), EXP_FALSO)

    def test_explicacao_vazia(self):
        self.assertIsNone(sre.filtrar_explicacao("limiar", None))


if __name__ == "__main__":
    unittest.main()
