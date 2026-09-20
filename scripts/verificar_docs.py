"""Verifica links locais no HTML gerado, sem acessar rede ou importar o motor."""

import argparse
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class PaginaHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = set()
        self.links = []

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        identificador = atributos.get("id") or (atributos.get("name") if tag == "a" else None)
        if identificador:
            self.ids.add(identificador)
        for atributo in ("href", "src"):
            if atributos.get(atributo):
                self.links.append(atributos[atributo])


def verificar_site(diretorio: Path) -> list[str]:
    raiz = diretorio.resolve()
    paginas = {}
    erros = set()
    if not (raiz / "index.html").is_file():
        return ["index.html ausente: execute o build primeiro"]
    for arquivo in raiz.rglob("*.html"):
        pagina = PaginaHTML()
        pagina.feed(arquivo.read_text(encoding="utf-8"))
        paginas[arquivo.resolve()] = pagina
    for arquivo, pagina in paginas.items():
        for link in pagina.links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                continue
            caminho = unquote(url.path)
            destino = (
                raiz / caminho.lstrip("/") if caminho.startswith("/")
                else arquivo.parent / caminho if caminho else arquivo
            ).resolve()
            origem = arquivo.relative_to(raiz).as_posix()
            if not destino.is_relative_to(raiz):
                erros.add(f"{origem}: caminho fora do site: {link}")
                continue
            if destino.is_dir():
                destino = destino / "index.html"
            if not destino.is_file():
                erros.add(f"{origem}: destino ausente: {link}")
            elif url.fragment and destino in paginas:
                if unquote(url.fragment) not in paginas[destino].ids:
                    erros.add(f"{origem}: ancora ausente: {link}")
    return sorted(erros)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", nargs="?", type=Path, default=Path("docs/site"))
    args = parser.parse_args()
    erros = verificar_site(args.site)
    if erros:
        for erro in erros:
            print(erro)
        return 1
    paginas = len(list(args.site.rglob("*.html")))
    print(f"OK: {paginas} arquivos HTML; destinos e ancoras locais validos. URLs externas nao verificadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())