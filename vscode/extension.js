const vscode = require('vscode');
const cp = require('child_process');
const path = require('path');

// A file is a "scadwright file" if it imports the scadwright package.
const SCADWRIGHT_RE = /^\s*(?:from\s+scadwright(?:\.|\s+import\b)|import\s+scadwright\b)/m;

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
    const cmd = cfg().get('scadwrightCommand') || 'scadwright';
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

  refreshContext();
}

function deactivate() {}

module.exports = { activate, deactivate };
