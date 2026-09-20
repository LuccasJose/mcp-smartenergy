const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { stripVTControlCharacters } = require('node:util');

function codigoDeSaida(resultado) {
  if (resultado.error || resultado.signal || !Number.isInteger(resultado.status)) {
    return 1;
  }
  if (resultado.status !== 0) {
    return resultado.status;
  }
  const saida = stripVTControlCharacters(`${resultado.stdout || ''}\n${resultado.stderr || ''}`);
  const diagnostico = /^\s*(?:WARNING|ERROR)\s*:/im.test(saida);
  const contagem = /^\s*[1-9]\d*\s+(?:errors?|warnings?)\b/im.test(saida);
  const resumoLimpo = /^\s*0\s+errors?\s*$/im.test(saida)
    && /^\s*0\s+warnings?\s*$/im.test(saida);
  return diagnostico || contagem || !resumoLimpo ? 1 : 0;
}

function executarBuild(diretorio) {
  const cli = path.resolve(__dirname, '../docs/node_modules/retypeapp/retype.js');
  const resultado = spawnSync(process.execPath, [cli, 'build', diretorio], {
    encoding: 'utf8',
    timeout: 120000,
    maxBuffer: 16 * 1024 * 1024,
  });
  process.stdout.write(resultado.stdout || '');
  process.stderr.write(resultado.stderr || '');
  if (resultado.error) {
    console.error(resultado.error.message);
  }
  const codigo = codigoDeSaida(resultado);
  if (codigo !== 0) {
    console.error('Build documental rejeitado: o Retype deve concluir sem erros ou avisos e emitir o resumo esperado.');
  }
  return codigo;
}

if (require.main === module) {
  const diretorio = path.resolve(process.argv[2] || path.join(__dirname, '../docs'));
  process.exitCode = executarBuild(diretorio);
}

module.exports = { codigoDeSaida };