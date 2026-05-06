import * as vscode from 'vscode';
import * as childProcess from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

type ViewerState = {
  status: 'loading' | 'ready' | 'error';
  uri: string;
  fileName: string;
  selectedNodeId?: string;
  graph?: unknown;
  error?: ParserError;
  limits: ParserLimits;
  progress?: ViewerProgress;
  diagnostics?: Record<string, unknown>;
};

type ParserLimits = {
  maxFileBytes: number;
  maxNodes: number;
  maxEdges: number;
  timeoutMs: number;
};

type ParserError = {
  schema: string;
  version: string;
  code: string;
  message: string;
  action: string;
  details?: unknown;
};

type ParserResult = {
  ok: boolean;
  graph?: unknown;
  error?: ParserError;
};

type ViewerProgress = {
  stage: string;
  message: string;
  elapsedMs?: number;
};

type ParserRunResult = {
  graph: unknown;
  python: string;
  elapsedMs: number;
  stdoutBytes: number;
  stderrBytes: number;
};

class PtDocument implements vscode.CustomDocument {
  constructor(public readonly uri: vscode.Uri) {}
  dispose(): void {}
}

export function activate(context: vscode.ExtensionContext): void {
  const provider = new TorchScriptDagProvider(context);
  context.subscriptions.push(
    vscode.window.registerCustomEditorProvider(TorchScriptDagProvider.viewType, provider, {
      webviewOptions: { retainContextWhenHidden: true },
      supportsMultipleEditorsPerDocument: false,
    })
  );
}

export function deactivate(): void {}

class TorchScriptDagProvider implements vscode.CustomReadonlyEditorProvider<PtDocument> {
  static readonly viewType = 'torchscriptDagViewer.ptEditor';
  private readonly states = new Map<string, ViewerState>();
  private readonly disposedPanels = new WeakSet<vscode.WebviewPanel>();
  private readonly output: vscode.OutputChannel;

  constructor(private readonly context: vscode.ExtensionContext) {
    this.output = vscode.window.createOutputChannel('TorchScript DAG Viewer');
    this.context.subscriptions.push(this.output);
  }

  openCustomDocument(uri: vscode.Uri): PtDocument {
    return new PtDocument(uri);
  }

  async resolveCustomEditor(document: PtDocument, webviewPanel: vscode.WebviewPanel): Promise<void> {
    webviewPanel.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, 'media')],
    };
    webviewPanel.webview.html = this.htmlFor(webviewPanel.webview);
    webviewPanel.onDidDispose(() => {
      this.disposedPanels.add(webviewPanel);
    });

    const uriKey = document.uri.toString();
    webviewPanel.webview.onDidReceiveMessage(
      async (message: unknown) => {
        if (!isRecord(message) || typeof message.action !== 'string') {
          return;
        }
        if (!['loadState', 'selectNode', 'requestReparse'].includes(message.action)) {
          return;
        }
        if (message.action === 'loadState') {
          await this.postState(webviewPanel, document);
          return;
        }
        if (message.action === 'selectNode') {
          const current = this.states.get(uriKey);
          if (current && (typeof message.nodeId === 'string' || message.nodeId === undefined || message.nodeId === null)) {
            current.selectedNodeId = message.nodeId || undefined;
          }
          return;
        }
        if (message.action === 'requestReparse') {
          await this.loadGraph(document, webviewPanel);
        }
      },
      undefined,
      this.context.subscriptions
    );

    await this.loadGraph(document, webviewPanel);
  }

  private async postState(webviewPanel: vscode.WebviewPanel, document: PtDocument): Promise<void> {
    const state = this.states.get(document.uri.toString()) ?? this.loadingState(document.uri);
    this.safePostState(webviewPanel, state);
  }

  private async loadGraph(document: PtDocument, webviewPanel: vscode.WebviewPanel): Promise<void> {
    const uriKey = document.uri.toString();
    const startedAt = Date.now();
    const updateLoading = (stage: string, message: string, diagnostics?: Record<string, unknown>): void => {
      const state = this.loadingState(document.uri, {
        stage,
        message,
        elapsedMs: Date.now() - startedAt,
      }, diagnostics);
      this.states.set(uriKey, state);
      this.log(`${path.basename(document.uri.fsPath || document.uri.path)} | ${stage} | ${message}`);
      this.safePostState(webviewPanel, state);
    };

    updateLoading('start', 'Opening TorchScript viewer.');

    if (!vscode.workspace.isTrusted) {
      const state = this.errorState(document.uri, {
        schema: 'torchscript.viewer.error',
        version: '1.0',
        code: 'WORKSPACE_NOT_TRUSTED',
        message: 'TorchScript parsing is disabled in Restricted Mode.',
        action: 'Trust this workspace only if you trust the .pt file source, then reopen the file.',
      });
      this.states.set(uriKey, state);
      this.safePostState(webviewPanel, state);
      return;
    }

    if (document.uri.scheme !== 'file') {
      const state = this.errorState(document.uri, {
        schema: 'torchscript.viewer.error',
        version: '1.0',
        code: 'UNSUPPORTED_URI',
        message: 'Only local file-system .pt files are supported by this MVP.',
        action: 'Open a local trusted TorchScript .pt file.',
        details: document.uri.toString(),
      });
      this.states.set(uriKey, state);
      this.safePostState(webviewPanel, state);
      return;
    }

    const limits = this.limits();
    try {
      updateLoading('file-check', 'Checking file size and configured limits.');
      const stat = await fs.promises.stat(document.uri.fsPath);
      if (stat.size > limits.maxFileBytes) {
        throw viewerError(
          'FILE_TOO_LARGE',
          `File is ${stat.size} bytes, exceeding the configured ${limits.maxFileBytes} byte limit.`,
          'Increase torchscriptDagViewer.maxFileBytes only for trusted files, or open a smaller model.',
          { sizeBytes: stat.size, maxFileBytes: limits.maxFileBytes }
        );
      }
      const parserResult = await this.runParser(
        document.uri.fsPath,
        limits,
        (stage, message, diagnostics) => {
          updateLoading(stage, message, diagnostics);
        }
      );
      updateLoading('render', 'Parser finished. Sending graph to Webview.', {
        python: parserResult.python,
        parseElapsedMs: parserResult.elapsedMs,
        stdoutBytes: parserResult.stdoutBytes,
      });
      const state: ViewerState = {
        status: 'ready',
        uri: document.uri.toString(),
        fileName: path.basename(document.uri.fsPath),
        graph: parserResult.graph,
        limits,
        progress: {
          stage: 'ready',
          message: `Parsed with ${parserResult.python} in ${formatMs(parserResult.elapsedMs)}.`,
          elapsedMs: Date.now() - startedAt,
        },
        diagnostics: {
          python: parserResult.python,
          parseElapsedMs: parserResult.elapsedMs,
          stdoutBytes: parserResult.stdoutBytes,
          stderrBytes: parserResult.stderrBytes,
          fileSizeBytes: stat.size,
        },
      };
      this.states.set(uriKey, state);
      this.safePostState(webviewPanel, state);
    } catch (error) {
      const state = this.errorState(document.uri, normalizeError(error), limits);
      this.states.set(uriKey, state);
      this.safePostState(webviewPanel, state);
    }
  }

  private async runParser(
    modelPath: string,
    limits: ParserLimits,
    onProgress: (stage: string, message: string, diagnostics?: Record<string, unknown>) => void
  ): Promise<ParserRunResult> {
    const configured = vscode.workspace.getConfiguration('torchscriptDagViewer').get<string>('pythonPath', '').trim();
    const candidates = configured ? [configured] : ['python3', 'python'];
    const parserPath = path.join(this.context.extensionPath, 'python', 'parse_torchscript.py');
    const errors: ParserError[] = [];

    for (const python of candidates) {
      try {
        const startedAt = Date.now();
        onProgress('python', `Starting parser with ${python}.`, { python, parserPath });
        this.log(`Spawning parser: ${python} ${parserPath} ${modelPath}`);
        const result = await runPython(python, [
          parserPath,
          modelPath,
          '--max-nodes',
          String(limits.maxNodes),
          '--max-edges',
          String(limits.maxEdges),
          '--max-file-bytes',
          String(limits.maxFileBytes),
        ], limits.timeoutMs, this.context.extensionPath);
        const elapsedMs = Date.now() - startedAt;
        this.log(`Parser completed: ${python} elapsed=${formatMs(elapsedMs)} stdout=${result.stdout.length} stderr=${result.stderr.length}`);
        onProgress('python', `Parser finished with ${python} in ${formatMs(elapsedMs)}.`, {
          python,
          elapsedMs,
          stdoutBytes: result.stdout.length,
          stderrBytes: result.stderr.length,
        });

        let parsed: ParserResult;
        try {
          parsed = JSON.parse(result.stdout) as ParserResult;
        } catch (parseError) {
          throw viewerError(
            'PARSER_INVALID_OUTPUT',
            'The parser did not return valid JSON.',
            'Check that the configured Python interpreter can run the bundled parser.',
            { stdout: result.stdout.slice(0, 4000), stderr: result.stderr.slice(0, 4000), parseError: String(parseError) }
          );
        }

        if (!parsed.ok) {
          throw parsed.error ?? viewerError('PARSER_FAILED', 'The parser returned an unknown error.', 'Try reparsing or inspect the Python environment.');
        }
        return {
          graph: parsed.graph,
          python,
          elapsedMs,
          stdoutBytes: result.stdout.length,
          stderrBytes: result.stderr.length,
        };
      } catch (error) {
        const normalized = normalizeError(error);
        errors.push(normalized);
        this.log(`Parser candidate failed: ${python} | ${normalized.code} | ${normalized.message}`);
        if (configured || normalized.code !== 'PYTHON_NOT_FOUND') {
          throw normalized;
        }
      }
    }

    throw viewerError(
      'PYTHON_NOT_FOUND',
      'No usable Python interpreter was found.',
      'Set torchscriptDagViewer.pythonPath to a Python interpreter with PyTorch installed.',
      errors
    );
  }

  private safePostState(webviewPanel: vscode.WebviewPanel, state: ViewerState): void {
    if (this.disposedPanels.has(webviewPanel)) {
      this.log(`Skip postMessage after Webview dispose: ${state.status} ${state.progress?.stage ?? ''}`);
      return;
    }
    webviewPanel.webview.postMessage({ action: 'state', state }).then(
      (delivered) => {
        if (!delivered) {
          this.log(`postMessage not delivered yet: ${state.status} ${state.progress?.stage ?? ''}`);
        }
      },
      (error) => {
        this.log(`postMessage failed: ${String(error)}`);
      }
    );
  }

  private log(message: string): void {
    this.output.appendLine(`[${new Date().toISOString()}] ${message}`);
  }

  private htmlFor(webview: vscode.Webview): string {
    const scriptUri = webview.asWebviewUri(vscode.Uri.joinPath(this.context.extensionUri, 'media', 'viewer.js'));
    const styleUri = webview.asWebviewUri(vscode.Uri.joinPath(this.context.extensionUri, 'media', 'viewer.css'));
    const nonce = createNonce();
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}'; img-src ${webview.cspSource} data:;">
  <link href="${styleUri}" rel="stylesheet">
  <title>TorchScript DAG Viewer</title>
</head>
<body>
  <main id="app" class="app">
    <section class="workspace">
      <header class="toolbar">
        <div class="title">
          <span id="fileName">TorchScript graph</span>
          <span id="statusText">Loading</span>
        </div>
        <div class="tools">
          <button id="zoomOut" title="Zoom out" aria-label="Zoom out">-</button>
          <button id="fit" title="Fit graph" aria-label="Fit graph">Fit</button>
          <button id="zoomIn" title="Zoom in" aria-label="Zoom in">+</button>
          <button id="reparse" title="Reparse file" aria-label="Reparse file">Reparse</button>
        </div>
      </header>
      <div id="viewport" class="viewport">
        <div id="canvas" class="canvas">
          <svg id="edges" class="edges" aria-hidden="true"></svg>
          <div id="nodes" class="nodes"></div>
        </div>
        <div id="emptyState" class="empty-state">Loading graph...</div>
      </div>
    </section>
    <aside id="details" class="details"></aside>
  </main>
  <script nonce="${nonce}" src="${scriptUri}"></script>
</body>
</html>`;
  }

  private loadingState(uri: vscode.Uri, progress?: ViewerProgress, diagnostics?: Record<string, unknown>): ViewerState {
    return {
      status: 'loading',
      uri: uri.toString(),
      fileName: path.basename(uri.fsPath || uri.path),
      limits: this.limits(),
      progress,
      diagnostics,
    };
  }

  private errorState(uri: vscode.Uri, error: ParserError, limits = this.limits()): ViewerState {
    return {
      status: 'error',
      uri: uri.toString(),
      fileName: path.basename(uri.fsPath || uri.path),
      error,
      limits,
    };
  }

  private limits(): ParserLimits {
    const config = vscode.workspace.getConfiguration('torchscriptDagViewer');
    return {
      maxFileBytes: Math.max(1, config.get<number>('maxFileBytes', 104857600)),
      maxNodes: Math.max(1, config.get<number>('maxNodes', 2000)),
      maxEdges: Math.max(1, config.get<number>('maxEdges', 4000)),
      timeoutMs: Math.max(1000, config.get<number>('parseTimeoutMs', 30000)),
    };
  }
}

function runPython(command: string, args: string[], timeoutMs: number, cwd: string): Promise<{ stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = childProcess.spawn(command, args, { cwd, windowsHide: true });
    let stdout = '';
    let stderr = '';
    let settled = false;
    const timer = setTimeout(() => {
      if (!settled) {
        settled = true;
        child.kill();
        reject(viewerError('PARSER_TIMEOUT', `Parser exceeded ${timeoutMs} ms.`, 'Increase torchscriptDagViewer.parseTimeoutMs for trusted files, or inspect a smaller model.'));
      }
    }, timeoutMs);

    child.stdout.on('data', (chunk: Buffer) => {
      stdout += chunk.toString('utf8');
      if (stdout.length > 10_000_000) {
        child.kill();
      }
    });
    child.stderr.on('data', (chunk: Buffer) => {
      stderr += chunk.toString('utf8');
    });
    child.on('error', (error: NodeJS.ErrnoException) => {
      clearTimeout(timer);
      if (!settled) {
        settled = true;
        if (error.code === 'ENOENT') {
          reject(viewerError('PYTHON_NOT_FOUND', `Python interpreter not found: ${command}`, 'Set torchscriptDagViewer.pythonPath to a Python interpreter with PyTorch installed.'));
        } else {
          reject(viewerError('PYTHON_START_FAILED', 'Could not start the Python parser.', 'Check torchscriptDagViewer.pythonPath and filesystem permissions.', String(error)));
        }
      }
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (settled) {
        return;
      }
      settled = true;
      if (code !== 0) {
        reject(viewerError('PARSER_PROCESS_FAILED', `Parser exited with code ${code}.`, 'Check the selected Python environment and try again.', { stdout: stdout.slice(0, 4000), stderr: stderr.slice(0, 4000) }));
        return;
      }
      resolve({ stdout, stderr });
    });
  });
}

function viewerError(code: string, message: string, action: string, details?: unknown): ParserError {
  return {
    schema: 'torchscript.viewer.error',
    version: '1.0',
    code,
    message,
    action,
    details,
  };
}

function normalizeError(error: unknown): ParserError {
  if (isRecord(error) && typeof error.code === 'string' && typeof error.message === 'string' && typeof error.action === 'string') {
    return error as ParserError;
  }
  return viewerError('UNKNOWN_ERROR', 'An unexpected error occurred.', 'Try reparsing the file or check the developer console.', String(error));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function createNonce(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let text = '';
  for (let i = 0; i < 32; i += 1) {
    text += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return text;
}

function formatMs(ms: number): string {
  if (ms < 1000) {
    return `${ms} ms`;
  }
  return `${(ms / 1000).toFixed(1)} s`;
}
