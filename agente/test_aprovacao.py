"""Testes da aprovação humana (issue #20). Rodar: python3 -m unittest -v agente/test_aprovacao.py"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import aprovacao  # noqa: E402

DONO = "1234567890"


class Relogio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class TestPendentes(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.caminho = os.path.join(self.dir.name, "p.json")
        self.relogio = Relogio()
        self.p = aprovacao.Pendentes(self.caminho, DONO, relogio=self.relogio)

    def tearDown(self):
        self.dir.cleanup()

    def test_dono_aprova_uma_vez(self):
        t = self.p.propor("reiniciar-container-ollama", {})
        self.assertEqual(self.p.decidir(t, DONO, "aprovar"), (True, "aprovado", "reiniciar-container-ollama"))

    def test_segundo_clique_nao_executa_de_novo(self):
        t = self.p.propor("reiniciar-container-ollama", {})
        self.p.decidir(t, DONO, "aprovar")
        self.assertEqual(self.p.decidir(t, DONO, "aprovar")[:2], (False, "ja-aprovado"))

    def test_outro_usuario_e_recusado_e_nao_consome_o_token(self):
        t = self.p.propor("reiniciar-container-ollama", {})
        self.assertEqual(self.p.decidir(t, "999", "aprovar")[:2], (False, "usuario-nao-autorizado"))
        self.assertTrue(self.p.decidir(t, DONO, "aprovar")[0])

    def test_expira_em_15_minutos(self):
        t = self.p.propor("reiniciar-container-ollama", {})
        self.relogio.t += aprovacao.VALIDADE_S + 1
        self.assertEqual(self.p.decidir(t, DONO, "aprovar")[:2], (False, "expirado"))
        self.assertEqual(self.p.decidir(t, DONO, "aprovar")[:2], (False, "ja-expirado"))

    def test_ainda_vale_no_limite(self):
        t = self.p.propor("reiniciar-container-ollama", {})
        self.relogio.t += aprovacao.VALIDADE_S - 1
        self.assertTrue(self.p.decidir(t, DONO, "aprovar")[0])

    def test_ignorar_bloqueia_aprovacao_posterior(self):
        t = self.p.propor("reiniciar-container-ollama", {})
        self.assertEqual(self.p.decidir(t, DONO, "ignorar"), (False, "ignorado", "reiniciar-container-ollama"))
        self.assertEqual(self.p.decidir(t, DONO, "aprovar")[:2], (False, "ja-ignorado"))

    def test_token_desconhecido(self):
        self.assertEqual(self.p.decidir("forjado", DONO, "aprovar")[:2], (False, "desconhecido"))

    def test_decisao_invalida_nao_consome(self):
        t = self.p.propor("reiniciar-container-ollama", {})
        self.assertEqual(self.p.decidir(t, DONO, "rm -rf")[:2], (False, "decisao-invalida"))
        self.assertTrue(self.p.decidir(t, DONO, "aprovar")[0])

    def test_acao_fora_do_catalogo_nao_pode_ser_proposta(self):
        with self.assertRaises(ValueError):
            self.p.propor("apagar-tudo", {})

    def test_estado_sobrevive_a_reinicio(self):
        t = self.p.propor("reiniciar-container-ollama", {})
        self.p.decidir(t, DONO, "aprovar")
        novo = aprovacao.Pendentes(self.caminho, DONO, relogio=self.relogio)
        self.assertEqual(novo.decidir(t, DONO, "aprovar")[:2], (False, "ja-aprovado"))

    def test_tokens_sao_unicos_e_imprevisiveis(self):
        tokens = {self.p.propor("reiniciar-container-ollama", {}) for _ in range(200)}
        self.assertEqual(len(tokens), 200)
        self.assertTrue(all(len(t) >= 16 for t in tokens))


class TestVerificacao(unittest.TestCase):
    def test_toda_acao_tem_conferencia_propria(self):
        self.assertEqual(set(aprovacao.VERIFICACAO), set(aprovacao.CATALOGO))

    def test_conferencia_nao_usa_dados_do_alerta(self):
        for acao, spec in aprovacao.VERIFICACAO.items():
            self.assertIn(spec[0], ("http", "servico-srv", "servico-pi"), acao)
            # nenhuma URL completa: host vem da configuração do agente, porta e caminho do catálogo
            self.assertFalse(any(isinstance(x, str) and "://" in x for x in spec), acao)

    def test_conferencia_no_mesmo_lugar_da_acao(self):
        for acao, (onde, _, _) in aprovacao.CATALOGO.items():
            tipo = aprovacao.VERIFICACAO[acao][0]
            self.assertTrue(tipo == "http" or tipo.endswith(onde), acao)


class TestAcaoSugerida(unittest.TestCase):
    def s(self, **labels):
        return aprovacao.acao_sugerida(labels)

    def test_mapeamentos(self):
        self.assertEqual(self.s(alertname="ServicoHttpFora", maquina="srv", servico="ollama"), "reiniciar-container-ollama")
        self.assertEqual(self.s(alertname="ServicoHttpFora", maquina="srv", servico="gateway"), "reiniciar-container-bifrost")
        self.assertEqual(self.s(alertname="ServicoHttpFora", maquina="pi", servico="trade-desk"), "reiniciar-servico-trade-desk")
        self.assertEqual(self.s(alertname="ServicoSystemdParado", maquina="srv", name="crypto-analyst.service"),
                         "reiniciar-servico-crypto-analyst")
        self.assertEqual(self.s(alertname="MetricasGpuParadas", maquina="srv"), "reiniciar-servico-gpu-metricas")

    def test_sem_acao_para_alertas_que_exigem_humano(self):
        for nome in ("MaquinaFora", "DiscoQuaseCheio", "PiPertoDeTravar", "GpuQuente", "GpuSemDriver"):
            self.assertIsNone(self.s(alertname=nome, maquina="srv"), nome)

    def test_servico_fora_do_catalogo_ou_maquina_errada(self):
        self.assertIsNone(self.s(alertname="ServicoSystemdParado", maquina="pi", name="ssh.service"))
        self.assertIsNone(self.s(alertname="ServicoSystemdParado", maquina="srv", name="trade-desk.service"))
        self.assertIsNone(self.s(alertname="ServicoSystemdParado", maquina="pi", name="tailscaled.service"))


if __name__ == "__main__":
    unittest.main()
