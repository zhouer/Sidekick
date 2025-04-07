import * as vscode from 'vscode';
import { getWebviewContent } from './getWebviewContent';
import { startWebSocketServer, stopWebSocketServer } from './websocketServer';

let sidekickPanel: vscode.WebviewPanel | undefined;

export function createOrShowSidekickPanel(extensionUri: vscode.Uri, context: vscode.ExtensionContext) { // Pass context
    const column = vscode.window.activeTextEditor
        ? vscode.window.activeTextEditor.viewColumn
        : undefined;

    if (sidekickPanel) {
        sidekickPanel.reveal(column);
        return;
    }

    // Define the exact path to the dist directory
    const webappDistPath = vscode.Uri.joinPath(extensionUri, 'dist');
    console.log("Webapp Dist Path for localResourceRoots:", webappDistPath.toString()); // Log the path

    sidekickPanel = vscode.window.createWebviewPanel(
        'sidekickPanel',
        'Sidekick',
        vscode.ViewColumn.Beside,
        {
            enableScripts: true,
            // CRITICAL: Only include the directory containing the assets
            localResourceRoots: [webappDistPath] // Ensure this is the only entry unless absolutely necessary
        }
    );

    // Set HTML content
    sidekickPanel.webview.html = getWebviewContent(sidekickPanel.webview, extensionUri);

    // Start WebSocket Server
    startWebSocketServer().catch(err => {
        vscode.window.showErrorMessage(`Failed to start Sidekick server: ${err.message}`);
    });

    // Handle Dispose
    sidekickPanel.onDidDispose(
        () => {
            sidekickPanel = undefined;
            stopWebSocketServer();
        },
        null,
        context.subscriptions // Use context for disposable management
    );
}