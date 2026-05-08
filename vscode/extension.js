const vscode = require('vscode');
const cp = require('child_process');
const path = require('path');
const fs = require('fs');

// LSP client lives in node_modules; the require is wrapped so the
// extension still loads (TextMate + toolbar features intact) even
// when vscode-languageclient hasn't been installed yet. The error
// surfaces in the output channel when activate() tries to start
// the client.
let lc = null;
try {
  lc = require('vscode-languageclient/node');
} catch (err) {
  lc = null;
}

// A file is a "scadwright file" if it imports the scadwright package.
const SCADWRIGHT_RE = /^\s*(?:from\s+scadwright(?:\.|\s+import\b)|import\s+scadwright\b)/m;

let lspClient = null;

function isscadwrightDoc(doc) {
  if (!doc || doc.languageId !== 'python') return false;
  return SCADWRIGHT_RE.test(doc.getText());
}

async function refreshContext() {
  const ed = vscode.window.activeTextEditor;
  const flag = ed ? isscadwrightDoc(ed.document) : false;
  await vscode.commands.executeCommand('setContext', 'scadwright.isscadwrightFile', !!flag);
}

function cfg() {
  return vscode.workspace.getConfiguration('scadwright');
}

function activescadwrightPath() {
  const ed = vscode.window.activeTextEditor;
  if (!ed) {
    vscode.window.showErrorMessage('scadwright: no active editor.');
    return null;
  }
  const doc = ed.document;
  if (!doc.fileName.endsWith('.py')) {
    vscode.window.showErrorMessage('scadwright: active file is not a Python script.');
    return null;
  }
  return { editor: ed, py: doc.fileName };
}

async function maybeSave(editor) {
  if (cfg().get('saveBeforeBuild') && editor.document.isDirty) {
    await editor.document.save();
  }
}

function buildscadwrightArgs(subcommand, pyPath, extra = []) {
  const conf = cfg();
  const variant = (conf.get('variant') || '').trim();
  const openscad = (conf.get('openscadCommand') || '').trim();
  const args = [subcommand, pyPath];
  if (variant) args.push(`--variant=${variant}`);
  if (openscad && openscad !== 'openscad') args.push(`--openscad=${openscad}`);
  return args.concat(extra);
}

function runscadwright(subcommand, pyPath, channel, extraArgs = []) {
  return new Promise((resolve, reject) => {
    const cmd = discoverScadwrightCommand();
    const args = buildscadwrightArgs(subcommand, pyPath, extraArgs);
    channel.appendLine(`$ ${cmd} ${args.join(' ')}`);
    const p = cp.spawn(cmd, args, { cwd: path.dirname(pyPath) });
    p.stdout.on('data', (d) => channel.append(d.toString()));
    p.stderr.on('data', (d) => channel.append(d.toString()));
    p.on('error', (err) => reject(new Error(`failed to launch ${cmd}: ${err.message}`)));
    p.on('close', (code) => {
      if (code === 0) return resolve();
      channel.show(true);
      reject(new Error(`scadwright ${subcommand} exited with code ${code}`));
    });
  });
}

async function previewCommand(channel) {
  const sel = activescadwrightPath();
  if (!sel) return;
  await maybeSave(sel.editor);
  try {
    await runscadwright('preview', sel.py, channel);
  } catch (e) {
    vscode.window.showErrorMessage(`scadwright preview failed: ${e.message}`);
  }
}

async function renderCommand(channel) {
  const sel = activescadwrightPath();
  if (!sel) return;
  await maybeSave(sel.editor);
  channel.show(true);
  try {
    await runscadwright('render', sel.py, channel);
    vscode.window.showInformationMessage(`scadwright: rendered ${path.basename(sel.py.replace(/\.py$/, '.stl'))}`);
  } catch (e) {
    vscode.window.showErrorMessage(`scadwright render failed: ${e.message}`);
  }
}

function killCommand(channel) {
  const isWin = process.platform === 'win32';
  const cmd = isWin ? 'taskkill' : 'pkill';
  const args = isWin ? ['/F', '/IM', 'openscad.exe'] : ['-f', 'openscad'];
  channel.appendLine(`$ ${cmd} ${args.join(' ')}`);
  cp.execFile(cmd, args, (err, stdout, stderr) => {
    if (err && err.code !== 1) {
      // pkill exit 1 = no processes matched; treat as success-with-nothing-killed
      vscode.window.showWarningMessage(`scadwright: kill returned ${err.message.trim()}`);
    } else {
      vscode.window.showInformationMessage('scadwright: killed running OpenSCAD instances.');
    }
    if (stdout) channel.append(stdout);
    if (stderr) channel.append(stderr);
  });
}

// =============================================================================
// Language-server client
// =============================================================================

// Pick the command to invoke ``scadwright`` — used by both the
// LSP startup and the toolbar's preview/render commands so the two
// paths agree on which binary to run. Order:
//   1. If the user explicitly set ``scadwright.scadwrightCommand``
//      (in workspace, user, or folder settings), honor it.
//   2. Else, look for a project venv binary at
//      ``<workspaceRoot>/.venv/bin/scadwright`` (or the Windows
//      equivalent). First match wins across multi-root workspaces.
//   3. Else, fall back to the default ``scadwright`` on PATH.
// This lets a project author check in workspace settings that point
// at a specific binary, while still auto-discovering the typical
// ``.venv`` layout for users who haven't configured anything.
function discoverScadwrightCommand() {
  const conf = vscode.workspace.getConfiguration('scadwright');
  const inspected = conf.inspect('scadwrightCommand');
  const userSet = inspected && (
    inspected.workspaceValue !== undefined ||
    inspected.globalValue !== undefined ||
    inspected.workspaceFolderValue !== undefined
  );
  if (userSet) {
    return conf.get('scadwrightCommand');
  }
  const folders = vscode.workspace.workspaceFolders || [];
  const isWin = process.platform === 'win32';
  for (const folder of folders) {
    const candidate = isWin
      ? path.join(folder.uri.fsPath, '.venv', 'Scripts', 'scadwright.exe')
      : path.join(folder.uri.fsPath, '.venv', 'bin', 'scadwright');
    if (fs.existsSync(candidate)) return candidate;
  }
  return conf.get('scadwrightCommand') || 'scadwright';
}

async function startLanguageServer(channel) {
  const conf = vscode.workspace.getConfiguration('scadwright');
  if (!conf.get('lsp.enable', true)) {
    channel.appendLine('[lsp] disabled by scadwright.lsp.enable=false.');
    return;
  }
  if (lc === null) {
    channel.appendLine(
      '[lsp] vscode-languageclient not installed; LSP disabled. ' +
      'Run `npm install` in the extension directory to enable.',
    );
    return;
  }
  const cmd = discoverScadwrightCommand();
  const serverOptions = {
    command: cmd,
    args: ['lsp'],
    transport: lc.TransportKind.stdio,
  };
  const clientOptions = {
    documentSelector: [{ scheme: 'file', language: 'python' }],
    outputChannel: channel,
    traceOutputChannel: channel,
    // The server can exit for several reasons — pygls missing, an
    // older ``scadwright`` without the ``lsp`` subcommand, an
    // uncaught exception in the server itself, or the user killing
    // the process. Don't try to diagnose; surface a hedged message
    // and stop. The actual stderr is in this channel above the
    // hint. ``DoNotRestart`` keeps us out of a crash loop; the user
    // can reload the window to retry.
    errorHandler: {
      error: () => ({ action: lc.ErrorAction.Shutdown }),
      closed: () => {
        channel.appendLine(
          '[lsp] server exited unexpectedly. Output above may have ' +
          "details. If pygls isn't installed yet, run: " +
          "pip install 'scadwright[lsp]'",
        );
        return { action: lc.CloseAction.DoNotRestart };
      },
    },
  };
  lspClient = new lc.LanguageClient(
    'scadwright-lsp',
    'SCADwright Language Server',
    serverOptions,
    clientOptions,
  );
  try {
    await lspClient.start();
    channel.appendLine(`[lsp] started: ${cmd} lsp`);
  } catch (err) {
    channel.appendLine(`[lsp] failed to start: ${err && err.message}`);
    channel.appendLine(
      "[lsp] if pygls isn't installed yet, run: " +
      "pip install 'scadwright[lsp]'",
    );
    lspClient = null;
  }
}

async function stopLanguageServer() {
  if (lspClient) {
    try { await lspClient.stop(); } catch (err) { /* shutdown best-effort */ }
    lspClient = null;
  }
}

function activate(context) {
  const channel = vscode.window.createOutputChannel('scadwright');

  context.subscriptions.push(
    channel,
    vscode.window.onDidChangeActiveTextEditor(refreshContext),
    vscode.workspace.onDidChangeTextDocument((e) => {
      const ed = vscode.window.activeTextEditor;
      if (ed && e.document === ed.document) refreshContext();
    }),
    vscode.workspace.onDidOpenTextDocument(() => refreshContext()),
    vscode.commands.registerCommand('scadwright.preview', () => previewCommand(channel)),
    vscode.commands.registerCommand('scadwright.render', () => renderCommand(channel)),
    vscode.commands.registerCommand('scadwright.kill', () => killCommand(channel)),
  );

  // Fire-and-forget LSP startup. Failures land in the output channel
  // and a one-time notification (see errorHandler in startLanguageServer);
  // the rest of the extension keeps working in TextMate-only mode.
  startLanguageServer(channel);

  refreshContext();
}

async function deactivate() {
  await stopLanguageServer();
}

module.exports = { activate, deactivate };
