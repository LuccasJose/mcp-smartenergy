const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { test } = require('node:test');
const { codigoDeSaida } = require('../scripts/build_docs.cjs');

const resumo = '2 pages built\n  0 errors\n  0 warnings\n';

test('aceita somente build com resumo limpo', () => {
  assert.equal(codigoDeSaida({ status: 0, stdout: resumo, stderr: '' }), 0);
});

for (const [nome, resultado] of [
  ['aviso stdout com codigo zero', { status: 0, stdout: `WARNING: frontmatter invalido\n${resumo}` }],
  ['erro stderr com codigo zero', { status: 0, stdout: resumo, stderr: 'ERROR: falha de template' }],
  ['diagnostico colorido', { status: 0, stdout: `\x1b[33mWARNING:\x1b[0m aviso\n${resumo}` }],
  ['contagem de avisos', { status: 0, stdout: '2 pages built\n0 errors\n4 warnings\n' }],
  ['contagem de erros', { status: 0, stdout: '1 page built\n1 error\n0 warnings\n' }],
  ['saida ausente', { status: 0, stdout: '' }],
  ['erro do processo', { status: null, error: new Error('spawn falhou') }],
  ['processo interrompido', { status: null, signal: 'SIGTERM' }],
]) {
  test(`rejeita ${nome}`, () => {
    assert.equal(codigoDeSaida(resultado), 1);
  });
}

test('preserva codigo de falha do Retype', () => {
  assert.equal(codigoDeSaida({ status: 2, stdout: resumo }), 2);
});

for (const [nome, markdown, codigo] of [
  ['pagina valida', '# Pagina valida\nConteudo sintetico.\n', 0],
  ['frontmatter invalido', '---\nlabel: [\n---\n# Pagina invalida\n', 1],
  ['template invalido', '# Pagina invalida\n{{ if }}\n', 1],
]) {
  test(`Retype real: ${nome}`, { timeout: 45000 }, () => {
    const diretorio = fs.mkdtempSync(path.join(os.tmpdir(), 'smartenergy-docs-test-'));
    try {
      fs.writeFileSync(path.join(diretorio, 'retype.json'), JSON.stringify({
        input: '.', output: 'site', url: 'https://example.com', cname: false,
      }));
      fs.writeFileSync(path.join(diretorio, 'index.md'), '# Inicio sintetico\nPagina de controle.\n');
      fs.writeFileSync(path.join(diretorio, 'pagina.md'), markdown);
      const resultado = spawnSync(process.execPath, [
        path.resolve(__dirname, '../scripts/build_docs.cjs'), diretorio,
      ], { encoding: 'utf8', timeout: 40000 });
      assert.ifError(resultado.error);
      assert.equal(resultado.status, codigo, resultado.stdout + resultado.stderr);
      assert.ok(fs.existsSync(path.join(diretorio, 'site/index.html')));
      if (codigo !== 0) {
        assert.match(resultado.stdout + resultado.stderr, /WARNING:/);
        assert.match(resultado.stderr, /Build documental rejeitado/);
      }
    } finally {
      fs.rmSync(diretorio, { recursive: true, force: true });
    }
  });
}