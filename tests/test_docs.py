"""Verificacoes do validador documental com HTML sintetico, sem Retype ou rede."""

import pytest

from scripts.verificar_docs import verificar_site


def test_site_sem_build_falha(tmp_path):
    assert verificar_site(tmp_path) == ["index.html ausente: execute o build primeiro"]


def test_site_links_recursos_e_ancoras_validos(tmp_path):
    pagina = tmp_path / "guia"
    pagina.mkdir()
    (tmp_path / "index.html").write_text(
        '<a href="guia/index.html#se%C3%A7%C3%A3o">Guia</a>'
        '<a href="/guia/">Raiz</a><script src="app.js?v=1"></script>'
        '<a href="https://example.invalid/">Externo nao consultado</a>', encoding="utf-8",
    )
    (pagina / "index.html").write_text('<h1 id="se\u00e7\u00e3o">Guia</h1>', encoding="utf-8")
    (tmp_path / "app.js").write_text("", encoding="utf-8")
    assert verificar_site(tmp_path) == []


@pytest.mark.parametrize("conteudo, mensagem", [
    ('<a href="ausente.html">Link</a>', "destino ausente"),
    ('<img src="ausente.png">', "destino ausente"),
    ('<a href="#inexistente">Ancora</a>', "ancora ausente"),
    ('<a href="../fora.html">Escapa</a>', "caminho fora do site"),
])
def test_site_rejeita_referencias_quebradas(tmp_path, conteudo, mensagem):
    (tmp_path / "index.html").write_text(conteudo, encoding="utf-8")
    erros = verificar_site(tmp_path)
    assert len(erros) == 1
    assert mensagem in erros[0]